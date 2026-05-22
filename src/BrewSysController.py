import os
import time
import pickle
import threading

from BrewSysTools import (
    BrewSysFSM, BrewTempSensor, BrewSysRelay, Brew1WireSwitch,
    state_index_text_disp, state_index_temp_target, state_index_temp_source,
    state_index_time, state_index_hlt_pump, state_index_mlt_pump,
    state_index_heater_override, state_index_hlt_pump_override, state_index_mlt_pump_override,
    time_to_heat_hlt, time_to_heat_mlt, time_wait_user,
    temp_src_hlt, temp_src_mlt_in, temp_src_mlt,
    mash_start, mash_hlt_heating, mash_mlt_heating, mash_mlt_heating_wait,
    mash_step1_rest, mash_pre_step2, mash_step2_rest, mash_pre_step3,
    mash_step3_rest, mash_pre_mash_out,
    mash_step1_str, mash_step2_str, mash_step3_str,
    mash_pre_step2_str, mash_pre_step3_str, mash_pre_mashout_str,
    sched_index_step1, sched_index_step2, sched_index_step3,
    sched_index_hlt_preheat, sched_index_mlt_preheat, sched_index_mlt_preheat_wait,
    sched_index_wait, sched_index_pre_mashout, sched_index_mashout,
    sched_index_sparge_wait, sched_index_sparge, sched_index_sparge2_preheat,
    sched_index_sparge2_wait, sched_index_sparge2, sched_index_pre_step2, sched_index_pre_step3,
)

HLT_SENSOR_PATH = '/sys/bus/w1/devices/28-021601a96aff/w1_slave'
MLT_IN_SENSOR_PATH = '/sys/bus/w1/devices/28-0316a49acfff/w1_slave'
MLT_SENSOR_PATH = '/sys/bus/w1/devices/28-031565df43ff/w1_slave'
WIRE1_SWITCH_PATH = '/sys/bus/w1/devices/3a-000000211dad/output'
PERSIST_FILE = 'BrewSysFSM.persist'


class BrewSysController:
    def __init__(self, sim_mode=True):
        self.sim_mode = sim_mode
        self._lock = threading.RLock()

        self.hlt_temp = 50.0
        self.mlt_in_temp = 50.0
        self.mlt_temp = 50.0

        if not self.sim_mode:
            self.hlt_temp_sensor = BrewTempSensor(HLT_SENSOR_PATH, 0)
            self.mlt_in_temp_sensor = BrewTempSensor(MLT_IN_SENSOR_PATH, 0)
            self.mlt_temp_sensor = BrewTempSensor(MLT_SENSOR_PATH, 0)
            self.heater_switch = Brew1WireSwitch(WIRE1_SWITCH_PATH)
            self.onboard_relays = BrewSysRelay()

        self.temp_target_tolerance = 0.5
        self.enable_hlt_heater = False
        self.hlt_heater_override = False
        self.hlt_pump_override = False
        self.mlt_pump_override = False

        self.brew_fsm = BrewSysFSM()
        self._restore_fsm_state()
        self.fsm_state, self.fsm_time_left, self.fsm_change = self.brew_fsm.fsmGetUpdate()
        self._persistence_counter = 0
        self._state = {}
        self._update_state_cache()

        self._running = True
        self._temp_thread = threading.Thread(target=self._temp_loop, daemon=True)
        self._control_thread = threading.Thread(target=self._control_loop, daemon=True)
        self._temp_thread.start()
        self._control_thread.start()

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    # Background threads
    # ------------------------------------------------------------------

    def _temp_loop(self):
        while self._running:
            if not self.sim_mode:
                self.hlt_temp = self.hlt_temp_sensor.readTempCelcius()
                self.mlt_in_temp = self.mlt_in_temp_sensor.readTempCelcius()
                self.mlt_temp = self.mlt_temp_sensor.readTempCelcius()
            else:
                with self._lock:
                    self.hlt_temp, self.mlt_in_temp, self.mlt_temp = self._simulate_temperature(
                        self.hlt_temp, self.mlt_in_temp, self.mlt_temp, self.enable_hlt_heater
                    )
            time.sleep(5)

    def _control_loop(self):
        while self._running:
            with self._lock:
                self._periodic()
            time.sleep(2)

    # ------------------------------------------------------------------
    # Core control tick — must be called with _lock held
    # ------------------------------------------------------------------

    def _periodic(self):
        self._persistence_counter += 1
        self.fsm_state, self.fsm_time_left, self.fsm_change = self.brew_fsm.fsmGetUpdate()

        if self.fsm_state[state_index_time] == time_to_heat_hlt:
            if self.hlt_temp >= self.fsm_state[state_index_temp_target]:
                self.fsm_state, self.fsm_time_left, self.fsm_change = self.brew_fsm.preheatTempReached()

        if self.fsm_state[state_index_time] == time_to_heat_mlt:
            if self.mlt_temp >= self.fsm_state[state_index_temp_target]:
                self.fsm_state, self.fsm_time_left, self.fsm_change = self.brew_fsm.preheatTempReached()

        src = self.fsm_state[state_index_temp_source]
        if src == temp_src_hlt:
            self.enable_hlt_heater = self._temp_control(self.hlt_temp, self.hlt_temp)
        elif src == temp_src_mlt_in:
            self.enable_hlt_heater = self._temp_control(self.mlt_in_temp, self.hlt_temp)
        else:
            self.enable_hlt_heater = self._temp_control(self.mlt_temp, self.hlt_temp)

        self._drive_hlt_pump(self._hlt_pump_on())
        self._drive_mlt_pump(self._mlt_pump_on())
        self._drive_heater(self._heater_on())

        if self.fsm_state != mash_start and self._persistence_counter >= 5:
            self._save_fsm_state()
            self._persistence_counter = 0

        self._update_state_cache()

    # ------------------------------------------------------------------
    # Temperature control
    # ------------------------------------------------------------------

    def _temp_control(self, current_temp, hlt_temp):
        target = self.fsm_state[state_index_temp_target]
        if current_temp <= target - self.temp_target_tolerance:
            enable = True
        elif current_temp >= target:
            enable = False
        else:
            enable = self.enable_hlt_heater

        if self.fsm_state in (mash_mlt_heating, mash_mlt_heating_wait):
            if current_temp <= target - self.temp_target_tolerance:
                enable = hlt_temp <= target + self.brew_fsm.getHltMaxTargetTempOvershoot()

        return enable

    def _simulate_temperature(self, hlt_temp, mlt_in_temp, mlt_temp, heater_on):
        if self.fsm_state == mash_hlt_heating:
            if heater_on:
                hlt_temp += 0.5
            else:
                hlt_temp -= 0.1
        elif self.fsm_state == mash_mlt_heating:
            if heater_on:
                hlt_temp += 0.1
                mlt_temp += 0.5
            else:
                hlt_temp -= 0.1
            mlt_in_temp = mlt_temp + (hlt_temp - mlt_temp) / 2
        else:
            if heater_on:
                hlt_temp += 0.5
                mlt_temp += 0.5
            else:
                hlt_temp -= 0.1
                mlt_temp -= 0.05
            mlt_in_temp = hlt_temp
            mlt_temp = hlt_temp
        return hlt_temp, mlt_in_temp, mlt_temp

    # ------------------------------------------------------------------
    # Override logic
    # ------------------------------------------------------------------

    def _heater_on(self):
        if self.enable_hlt_heater:
            return not self.hlt_heater_override
        return self.hlt_heater_override

    def _hlt_pump_on(self):
        fsm_wants = self.fsm_state[state_index_hlt_pump]
        if fsm_wants:
            return not self.hlt_pump_override
        return self.hlt_pump_override

    def _mlt_pump_on(self):
        fsm_wants = self.fsm_state[state_index_mlt_pump]
        if fsm_wants:
            return not self.mlt_pump_override
        return self.mlt_pump_override

    # ------------------------------------------------------------------
    # Hardware drivers
    # ------------------------------------------------------------------

    def _drive_heater(self, enable):
        if not self.sim_mode:
            if enable:
                self.heater_switch.closeSwitchA()
            else:
                self.heater_switch.openSwitchAll()

    def _drive_hlt_pump(self, enable):
        if not self.sim_mode:
            if enable:
                self.onboard_relays.ON_1()
            else:
                self.onboard_relays.OFF_1()

    def _drive_mlt_pump(self, enable):
        if not self.sim_mode:
            if enable:
                self.onboard_relays.ON_2()
            else:
                self.onboard_relays.OFF_2()

    # ------------------------------------------------------------------
    # State cache
    # ------------------------------------------------------------------

    def _update_state_cache(self):
        s = self.fsm_state
        target = s[state_index_temp_target]
        src = s[state_index_temp_source]

        hlt_target = target if src == temp_src_hlt else 0
        mlt_in_target = target if src == temp_src_mlt_in else 0
        mlt_target = target if src in (temp_src_mlt_in, temp_src_mlt) else 0

        time_left = self.fsm_time_left
        show_timer = time_left > 0 and s[state_index_time] > 0

        self._state = {
            'hlt_temp': round(self.hlt_temp, 1),
            'mlt_in_temp': round(self.mlt_in_temp, 1),
            'mlt_temp': round(self.mlt_temp, 1),
            'hlt_target': hlt_target,
            'mlt_in_target': mlt_in_target,
            'mlt_target': mlt_target,
            'status_text': s[state_index_text_disp],
            'time_left': int(time_left) if show_timer else 0,
            'show_timer': show_timer,
            'heater_on': self._heater_on(),
            'hlt_pump_on': self._hlt_pump_on(),
            'mlt_pump_on': self._mlt_pump_on(),
            'heater_override_allowed': s[state_index_heater_override],
            'hlt_pump_override_allowed': s[state_index_hlt_pump_override],
            'mlt_pump_override_allowed': s[state_index_mlt_pump_override],
            'hlt_heater_override': self.hlt_heater_override,
            'hlt_pump_override': self.hlt_pump_override,
            'mlt_pump_override': self.mlt_pump_override,
            'at_start': s == mash_start,
            'show_sparge_pause': s[state_index_mlt_pump_override] and s != mash_start,
            'mlt_pump_paused': self.mlt_pump_override,
            'step_indicators': self._get_step_indicators(),
            'recipe': self._get_recipe(),
        }

    def _get_step_indicators(self):
        text = self.fsm_state[state_index_text_disp]
        step2_enabled = self.brew_fsm.getStep2StateInfo()[state_index_temp_target] > 0
        step3_enabled = self.brew_fsm.getStep3StateInfo()[state_index_temp_target] > 0

        ind = {'step1': 'grey', 'step2': 'grey', 'step3': 'grey'}

        if text == mash_step1_str:
            ind['step1'] = 'yellow'
        elif text == mash_pre_step2_str:
            ind['step1'] = 'green'
        elif text == mash_step2_str:
            ind['step1'] = 'green'
            ind['step2'] = 'yellow'
        elif text == mash_pre_step3_str:
            ind['step1'] = 'green'
            ind['step2'] = 'green'
        elif text == mash_step3_str:
            ind['step1'] = 'green'
            ind['step2'] = 'green'
            ind['step3'] = 'yellow'
        elif text == mash_pre_mashout_str:
            ind['step1'] = 'green'
            if step2_enabled:
                ind['step2'] = 'green'
            if step3_enabled:
                ind['step3'] = 'green'

        return ind

    def _get_recipe(self):
        step1 = self.brew_fsm.getStep1StateInfo()
        step2 = self.brew_fsm.getStep2StateInfo()
        step3 = self.brew_fsm.getStep3StateInfo()
        return {
            'mash_in_temp': self.brew_fsm.getMashInTemperature(),
            'step1_temp': step1[state_index_temp_target],
            'step1_time': step1[state_index_time],
            'step2_temp': step2[state_index_temp_target],
            'step2_time': step2[state_index_time],
            'step2_enabled': step2[state_index_temp_target] > 0,
            'step3_temp': step3[state_index_temp_target],
            'step3_time': step3[state_index_time],
            'step3_enabled': step3[state_index_temp_target] > 0,
            'mashout_temp': self.brew_fsm.getMashOutTemperature(),
            'mashout_time': self.brew_fsm.getMashOutTime(),
            'sparge_temp': self.brew_fsm.getSpargeTemperature(),
            'hlt_overshoot': self.brew_fsm.getHltTempOvershoot(),
            'hlt_max_overshoot': self.brew_fsm.getHltMaxTargetTempOvershoot(),
            'hlt_calib': self.hlt_temp_sensor.getCalibAdjustment() if not self.sim_mode else 0,
            'mlt_in_calib': self.mlt_in_temp_sensor.getCalibAdjustment() if not self.sim_mode else 0,
            'mlt_calib': self.mlt_temp_sensor.getCalibAdjustment() if not self.sim_mode else 0,
        }

    def get_state(self):
        with self._lock:
            return dict(self._state)

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------

    def proceed(self):
        with self._lock:
            self.fsm_state, self.fsm_time_left, self.fsm_change = self.brew_fsm.userActionReceived()
            if self.fsm_state == mash_start:
                self._clear_fsm_state()
            self._periodic()
            return dict(self._state)

    def abort(self):
        with self._lock:
            self.brew_fsm.abort()
            self.hlt_heater_override = False
            self.hlt_pump_override = False
            self.mlt_pump_override = False
            self._clear_fsm_state()
            self._periodic()
            return dict(self._state)

    def toggle_heater_override(self):
        with self._lock:
            if self.fsm_state[state_index_heater_override]:
                self.hlt_heater_override = not self.hlt_heater_override
            else:
                self.hlt_heater_override = False
            self._periodic()
            return dict(self._state)

    def toggle_hlt_pump_override(self):
        with self._lock:
            if self.fsm_state[state_index_hlt_pump_override]:
                self.hlt_pump_override = not self.hlt_pump_override
            else:
                self.hlt_pump_override = False
            self._periodic()
            return dict(self._state)

    def toggle_mlt_pump_override(self):
        with self._lock:
            if self.fsm_state[state_index_mlt_pump_override]:
                self.mlt_pump_override = not self.mlt_pump_override
            else:
                self.mlt_pump_override = False
            self._periodic()
            return dict(self._state)

    def update_settings(self, settings: dict):
        with self._lock:
            if self.fsm_state != mash_start:
                return False

            if 'hlt_overshoot' in settings:
                self.brew_fsm.setHltTempOvershoot(float(settings['hlt_overshoot']))
            if 'hlt_max_overshoot' in settings:
                self.brew_fsm.setHltMaxTargetTempOvershoot(float(settings['hlt_max_overshoot']))

            if not self.sim_mode:
                if 'hlt_calib' in settings:
                    self.hlt_temp_sensor.setCalibAdjustment(float(settings['hlt_calib']))
                if 'mlt_in_calib' in settings:
                    self.mlt_in_temp_sensor.setCalibAdjustment(float(settings['mlt_in_calib']))
                if 'mlt_calib' in settings:
                    self.mlt_temp_sensor.setCalibAdjustment(float(settings['mlt_calib']))

            if 'mash_in_temp' in settings:
                self.brew_fsm.setMashInTemperature(float(settings['mash_in_temp']))

            step1 = self.brew_fsm.getStep1StateInfo()
            if 'step1_temp' in settings:
                step1[state_index_temp_target] = float(settings['step1_temp'])
            if 'step1_time' in settings:
                step1[state_index_time] = int(settings['step1_time'])
            self.brew_fsm.setStep1StateInfo(step1)

            step2 = self.brew_fsm.getStep2StateInfo()
            if settings.get('step2_enabled', True):
                if 'step2_temp' in settings:
                    step2[state_index_temp_target] = float(settings['step2_temp'])
                if 'step2_time' in settings:
                    step2[state_index_time] = int(settings['step2_time'])
            else:
                step2[state_index_temp_target] = 0.0
                step2[state_index_time] = 0
            self.brew_fsm.setStep2StateInfo(step2)

            step3 = self.brew_fsm.getStep3StateInfo()
            if settings.get('step3_enabled', True):
                if 'step3_temp' in settings:
                    step3[state_index_temp_target] = float(settings['step3_temp'])
                if 'step3_time' in settings:
                    step3[state_index_time] = int(settings['step3_time'])
            else:
                step3[state_index_temp_target] = 0.0
                step3[state_index_time] = 0
            self.brew_fsm.setStep3StateInfo(step3)

            if 'mashout_temp' in settings:
                self.brew_fsm.setMashOutTemperature(float(settings['mashout_temp']))
            if 'mashout_time' in settings:
                self.brew_fsm.setMashOutTime(int(settings['mashout_time']))
            if 'sparge_temp' in settings:
                self.brew_fsm.setSpargeTemperature(float(settings['sparge_temp']))

            self._update_state_cache()
            return True

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _restore_fsm_state(self):
        try:
            with open(PERSIST_FILE, 'rb') as f:
                self.brew_fsm = pickle.load(f)
        except IOError:
            print(f'{PERSIST_FILE} not found, starting fresh')

    def _save_fsm_state(self):
        with open(PERSIST_FILE, 'wb') as f:
            pickle.dump(self.brew_fsm, f)

    def _clear_fsm_state(self):
        try:
            os.remove(PERSIST_FILE)
        except OSError:
            pass
