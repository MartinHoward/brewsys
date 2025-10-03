# status_provider.py
# Provides BrewSys status data for the Flask web UI


import random
import time
import os

import sys
sys.path.append('../src')
try:
    from BrewSysTools import BrewSysRelay, Brew1WireSwitch
except ImportError:
    BrewSysRelay = None
    Brew1WireSwitch = None

class BrewSysStatusProvider:
    # 1-wire device files (from BrewSysApp.py)
    HLT_TEMP_SENSOR = '/sys/bus/w1/devices/28-021601a96aff/w1_slave'
    MLT_IN_TEMP_SENSOR = '/sys/bus/w1/devices/28-03160468a3ff/w1_slave'
    MLT_TEMP_SENSOR = '/sys/bus/w1/devices/28-031565df43ff/w1_slave'

    def __init__(self, sim_mode=True):
        self.sim_mode = sim_mode or not self._hardware_available()
        self.hlt_temp = 68.0
        self.mt_in_temp = 66.5
        self.mt_out_temp = 65.2
        self.current_state = 'Heating'
        self.time_left = 900  # seconds

        # Simulated or tracked hardware state
        self._sim_hlt_heater = True
        self._sim_hlt_pump = False
        self._sim_mt_pump = True

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

        return {
            'hlt_temp': round(self.hlt_temp, 1),
            'mt_in_temp': round(self.mt_in_temp, 1),
            'mt_out_temp': round(self.mt_out_temp, 1),
            'current_state': self.current_state,
            'hlt_heater': 'ON' if hlt_heater else 'OFF',
            'hlt_pump': 'ON' if hlt_pump else 'OFF',
            'mt_pump': 'ON' if mt_pump else 'OFF',
            'time_left': time.strftime('%H:%M:%S', time.gmtime(self.time_left))
        }
