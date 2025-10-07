# status_provider.py
# Provides BrewSys status data for the Flask web UI


import random
import time
import os
import threading

import sys
import os
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if src_path not in sys.path:
    sys.path.insert(0, src_path)
try:
    from BrewSysTools import BrewSysRelay, Brew1WireSwitch
except ImportError as e:
    print(f"ERROR: Could not import BrewSysRelay or Brew1WireSwitch from BrewSysTools.py: {e}")
    BrewSysRelay = None
    Brew1WireSwitch = None

class BrewSysStatusProvider:
    # 1-wire device files (from BrewSysApp.py)
    HLT_TEMP_SENSOR = '/sys/bus/w1/devices/28-021601a96aff/w1_slave'
    MLT_IN_TEMP_SENSOR = '/sys/bus/w1/devices/28-0316a49acfff/w1_slave'
    MLT_TEMP_SENSOR = '/sys/bus/w1/devices/28-031565df43ff/w1_slave'


    def __init__(self, sim_mode=True):
        self._last_hlt_heater = False
        self._last_hlt_pump = False
        self._last_mt_pump = False
        self._hardware_error = None
        self.sim_mode = sim_mode
        if not sim_mode:
            if not self._hardware_available():
                self._hardware_error = 'Missing one or more 1-wire sensor files.'
                print('ERROR: Missing one or more 1-wire sensor files.')
                self.sim_mode = True
            else:
                try:
                    self._relay = BrewSysRelay() if BrewSysRelay else None
                    self._switch = Brew1WireSwitch('/sys/bus/w1/devices/3a-000000211dad/output') if Brew1WireSwitch else None
                    if not self._relay:
                        print('ERROR: BrewSysRelay class not available or failed to initialize.')
                    if not self._switch:
                        print('ERROR: Brew1WireSwitch class not available or failed to initialize.')
                    if not self._relay or not self._switch:
                        self._hardware_error = 'Relay or Switch class not available.'
                        self.sim_mode = True
                except Exception as e:
                    self._hardware_error = f'Exception during relay/switch init: {e}'
                    print(f'ERROR: Exception during relay/switch init: {e}')
                    self.sim_mode = True
        else:
            self._hardware_error = 'Simulation mode forced by parameter.'
        self.hlt_temp = 68.0
        self.mt_in_temp = 66.5
        self.mt_out_temp = 65.2
        self.current_state = 'Heating'
        self.time_left = 900  # seconds

        # Simulated or tracked hardware state
        self._sim_hlt_heater = True
        self._sim_hlt_pump = False
        self._sim_mt_pump = True

        # FSM state indices (should match BrewSysApp.py)
        self.state_index_text_disp = 0
        self.state_index_temp_target = 1
        self.state_index_temp_source = 2
        self.state_index_time = 3
        self.state_index_hlt_pump = 4
        self.state_index_mlt_pump = 5
        self.state_index_heater_override = 6
        self.state_index_hlt_pump_override = 7
        self.state_index_mlt_pump_override = 8

        # Simulate FSM state for demo
        self.fsm_state = [
            'Heating', 70.0, 1, 600, True, True, True, True, True
        ]

        # Start background thread for temp updates
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._background_update, daemon=True)
        self._thread.start()

    def _background_update(self):
        while not self._stop_event.is_set():
            if self.sim_mode:
                self.hlt_temp, self.mt_in_temp, self.mt_out_temp = self._simulate_temperature(
                    self.hlt_temp, self.mt_in_temp, self.mt_out_temp, self._sim_hlt_heater)
                self.time_left = max(0, self.time_left - 5)
            # In real mode, you would read sensors here
            time.sleep(5)

    def _simulate_temperature(self, hltTemp, mltInTemp, mltTemp, heaterOn):
        # Updated simulation logic from BrewSysApp.py
        simTempLag = getattr(self, 'simTempLag', 0)
        if heaterOn:
            simTempLag = 3
        elif simTempLag > 0:
            simTempLag -= 1
        heating = heaterOn or simTempLag > 0
        # Example FSM state for simulation
        fsm_state = self.fsm_state
        mash_hlt_heating = 'Heating'  # Placeholder
        mash_mlt_heating = 'MLT Heating'  # Placeholder
        if fsm_state[self.state_index_text_disp] == mash_hlt_heating:
            if heating:
                hltTemp += 0.5
            else:
                hltTemp -= 0.1
        elif fsm_state[self.state_index_text_disp] == mash_mlt_heating:
            if heating:
                hltTemp += 0.1
                mltTemp += 0.5
            else:
                hltTemp -= 0.1
            mltInTemp = mltTemp + (hltTemp - mltTemp) / 2
        else:
            if heating:
                hltTemp += 0.5
                mltTemp += 0.5
            else:
                hltTemp -= 0.1
                mltTemp -= 0.05
            mltInTemp = hltTemp
            mltTemp = hltTemp
        self.simTempLag = simTempLag
        return hltTemp, mltInTemp, mltTemp

        # Hardware relay/switch objects (if available)
        self._relay = None
        self._switch = None
        self._last_hlt_pump = False
        self._last_mt_pump = False
        self._last_hlt_heater = False
        if not self.sim_mode and BrewSysRelay and Brew1WireSwitch:
            try:
                self._relay = BrewSysRelay()
                self._switch = Brew1WireSwitch('/sys/bus/w1/devices/3a-000000211dad/output')
            except Exception:
                self._relay = None
                self._switch = None

    def _hardware_available(self):
        # Check if all sensor files exist
        return all(os.path.exists(f) for f in [
            self.HLT_TEMP_SENSOR,
            self.MLT_IN_TEMP_SENSOR,
            self.MLT_TEMP_SENSOR
        ])

    def _read_temp_sensor(self, path):
        try:
            with open(path, 'r') as f:
                lines = f.readlines()
            # Typical 1-wire output: second line contains 't=XXXXX' (temp in millidegrees C)
            if lines[0].strip().endswith('YES'):
                temp_str = lines[1].split('t=')[-1]
                return float(temp_str) / 1000.0
        except Exception:
            pass
        return None


    def _read_hlt_heater_status(self, default):
        # No direct read in Brew1WireSwitch, so return last set value if in hardware mode
        if not self.sim_mode:
            return self._last_hlt_heater
        return default

    def _read_pump_status(self, pump_num, default):
        # No direct read in BrewSysRelay, so return last set value if in hardware mode
        if not self.sim_mode:
            if pump_num == 1:
                return self._last_hlt_pump
            elif pump_num == 2:
                return self._last_mt_pump
        return default

    def get_status(self):
        if not self.sim_mode:
            hlt_temp = self._read_temp_sensor(self.HLT_TEMP_SENSOR)
            mt_in_temp = self._read_temp_sensor(self.MLT_IN_TEMP_SENSOR)
            mt_out_temp = self._read_temp_sensor(self.MLT_TEMP_SENSOR)
            # Fallback to previous/simulated if read fails
            self.hlt_temp = hlt_temp if hlt_temp is not None else self.hlt_temp
            self.mt_in_temp = mt_in_temp if mt_in_temp is not None else self.mt_in_temp
            self.mt_out_temp = mt_out_temp if mt_out_temp is not None else self.mt_out_temp

            # Try to read hardware status (no direct read, so return last set value or default)
            hlt_heater = self._read_hlt_heater_status(self._sim_hlt_heater)
            hlt_pump = self._read_pump_status(1, self._sim_hlt_pump)
            mt_pump = self._read_pump_status(2, self._sim_mt_pump)
        else:
            # Simulate changing values for demo
            self.hlt_temp += random.uniform(-0.1, 0.1)
            self.mt_in_temp += random.uniform(-0.1, 0.1)
            self.mt_out_temp += random.uniform(-0.1, 0.1)
            self.time_left = max(0, self.time_left - 5)
            hlt_heater = self._sim_hlt_heater
            hlt_pump = self._sim_hlt_pump
            mt_pump = self._sim_mt_pump

        status = {
            'hlt_temp': round(self.hlt_temp, 1),
            'mt_in_temp': round(self.mt_in_temp, 1),
            'mt_out_temp': round(self.mt_out_temp, 1),
            'current_state': self.fsm_state[self.state_index_text_disp],
            'hlt_heater': 'ON' if hlt_heater else 'OFF',
            'hlt_pump': 'ON' if hlt_pump else 'OFF',
            'mt_pump': 'ON' if mt_pump else 'OFF',
            'time_left': time.strftime('%H:%M:%S', time.gmtime(self.time_left)),
            'can_override_heater': self.fsm_state[self.state_index_heater_override],
            'can_override_hlt_pump': self.fsm_state[self.state_index_hlt_pump_override],
            'can_override_mlt_pump': self.fsm_state[self.state_index_mlt_pump_override],
            'fsm_state': self.fsm_state,
            'sim_mode': self.sim_mode,
        }
        if self.sim_mode and self._hardware_error:
            status['hardware_error'] = self._hardware_error
        return status
