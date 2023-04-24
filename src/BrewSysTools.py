import os
import time
import smbus2
import signal
import sys
import pickle

from subprocess import call

#os.system('modprobe w1-gpio')
#os.system('modprobe w1-therm')

# tags
time_to_heat_hlt =  -1
time_to_heat_mlt =  -2
time_wait=          -3
temp_na=            -1
temp_src_na=         0
temp_src_hlt=        1
temp_src_mt_in=      2
temp_src_mt=         3

# The following variables could be added to a configuration screen
hlt_temp_overshoot = 5.0		# Amount to overshoot HLT temp during a step preheat
max_hlt_temp_target_overshoot = 2.0	 # Maximum temp difference between HLT and target to allow in some states,
                                     # must not be used in conjunction with hlt_temp_overshoot
mashout_period = 20

state_index_text_disp=0
state_index_temp_target=1
state_index_temp_source=2
state_index_time=3
state_index_hlt_pump=4
state_index_mt_pump=5

mash_start_str=                 'Press To Start Mash'
mash_pre_check_str=	            'System Check - Press When Ready'
mash_hlt_preheat_str=           'Pre-Heating HLT'
mash_mt_preheat_str=            'Pre-Heating MLT'
mash_mt_preheat_wait_str=       'Pre-Heating Complete - Press To Continue'
mash_contrinue_str=             'Add Grains - Press To Continue'
mash_doughin_str=               'Dough In'
mash_acidrest_str=              'Acid Rest'
mash_pre_protrest_str=          'Preheat To Protein Rest'
mash_protrest_str=              'Protein Rest'
mash_pre_sacrest_str=           'Preheat To Starch Conversion'
mash_sacrest_str=               'Starch Conversion'
mash_pre_mashout_str=           'Preheat To Mash Out'
mash_mashout_str=               'Mash Out'
mash_sparge_wait_str=           'Reconfigure For Sparging Then Drain MLT - Press To Continue'
mash_sparge_str=                'Sparging First Batch - Press When MLT Is Full'
mash_sparge2_refill_wait_str=   'Refill HLT With Hot Water - Press To Continue'
mash_sparge2_preheat_str=       'Preheating HLT for Second Batch Sparge'
mash_sparge2_wait_str=          'Preheat Complete, Drain MLT - Press To Begin Second Sparge'
mash_sparge2_str=               'Sparging Second Batch - Press When MLT Is Full'
mash_step1_str=                 'Mash Step 1 - Rest'
mash_step2_str=                 'Mash Step 2 - Rest'
mash_step3_str=                 'Mash Step 3 - Rest'
mash_pre_step2_str=             'Preheating to Step 2 Temperature'
mash_pre_step3_str=             'Preheating to Step 3 Temperature'

# mash state                #State Display Text         #Target Temp        #Temp Source	#Time in State  	#HLT Pump On    #MT Pump On
mash_start =                [mash_start_str,                temp_na,        temp_src_na,    time_wait,          False,          False       ]
mash_pre_check =            [mash_pre_check_str,            temp_na,        temp_src_na,    time_wait,          True,           True        ]
mash_hlt_heating =          [mash_hlt_preheat_str,          70.0,           temp_src_hlt,   time_to_heat_hlt,   True,           False       ]
mash_mt_heating =           [mash_mt_preheat_str,           70.0,           temp_src_mt,    time_to_heat_mlt,   True,           True        ]
mash_mt_heating_wait =      [mash_mt_preheat_wait_str,      70.0,           temp_src_mt,    time_wait,          True,           True        ]
mash_wait =                 [mash_contrinue_str,            70.0,           temp_src_hlt,   time_wait,          True,           False       ]
mash_step1_rest =           [mash_step1_str,                66.0,           temp_src_mt_in, 60,                 True,           True        ]
mash_pre_step2 =            [mash_pre_step2_str,            0.0,            temp_src_hlt,   time_to_heat_hlt,   True,           False       ]
mash_step2_rest =           [mash_step2_str,                0.0,            temp_src_mt_in, 0,                  True,           True        ]
mash_pre_step3 =            [mash_pre_step3_str,            0.0,            temp_src_hlt,   time_to_heat_hlt,   True,           False       ]
mash_step3_rest =           [mash_step3_str,                0.0,            temp_src_mt_in,	0,                  True,           True        ]
mash_pre_mash_out =         [mash_pre_mashout_str,          82.0,           temp_src_hlt,   time_to_heat_hlt,   True,           False       ]
mash_mash_out =	            [mash_mashout_str,              76.0,           temp_src_mt_in, mashout_period,     True,           True        ]
mash_sparge_wait =          [mash_sparge_wait_str,          76.0,           temp_src_hlt,   time_wait,          True,           False       ]
mash_sparge =               [mash_sparge_str,               76.0,           temp_src_hlt,   time_wait,          False,          True        ]
mash_sparge2_refill_wait =  [mash_sparge2_refill_wait_str,  temp_na,        temp_src_hlt,   time_wait,          False,          False       ]
mash_sparge2_preheat =	    [mash_sparge2_preheat_str,      76.0,           temp_src_hlt,   time_to_heat_hlt,   True,           False       ]
mash_sparge2_wait =	        [mash_sparge2_wait_str,         76.0,           temp_src_hlt,   time_wait,          True,           False       ]
mash_sparge2 =              [mash_sparge2_str,              76.0,           temp_src_hlt,   time_wait,          False,          True        ]

sched_index_start=                  0
sched_index_pre_check=              1
sched_index_hlt_preheat=            2
sched_index_mlt_preheat=            3
sched_index_mlt_preheat_wait=       4
sched_index_wait=                   5
sched_index_step1=                  6
sched_index_pre_step2=              7
sched_index_step2=                  8
sched_index_pre_step3=              9
sched_index_step3=                  10
sched_index_pre_mashout=            11
sched_index_mashout=                12
sched_index_sparge_wait=            13
sched_index_sparge=                 14
sched_index_sparge2_refill_wait=    15
sched_index_sparge2_preheat=        16
sched_index_sparge2_wait=           17
sched_index_sparge2=                18

sched_index_last = sched_index_sparge2

mash_schedule =    [mash_start,
                    mash_pre_check,
                    mash_hlt_heating,
                    mash_mt_heating,
                    mash_mt_heating_wait,
                    mash_wait,
                    mash_step1_rest,
                    mash_pre_step2,
                    mash_step2_rest,
                    mash_pre_step3,
                    mash_step3_rest,
                    mash_pre_mash_out,
                    mash_mash_out,
                    mash_sparge_wait,
                    mash_sparge,
                    mash_sparge2_refill_wait,
                    mash_sparge2_preheat,
                    mash_sparge2_wait,
                    mash_sparge2]


class BrewSysFSM:
    def __init__(self):
        self.stateList = mash_schedule
        self.currentStateIndex = 0
        self.currentState = self.stateList[self.currentStateIndex]
        self.timeLeft = 0
        self.timerStart = 0
        self.timeInState = 0
        self.stateHasChanged = False
        self.persistence_counter = 0
        self.hltTempOverShoot = hlt_temp_overshoot
        self.hltMaxTargetTempOvershoot = max_hlt_temp_target_overshoot

    def handleStateChange(self):
        if self.currentStateIndex == sched_index_last:
            # Reached last state - return to initial state
            self.currentStateIndex = sched_index_start
            self.currentState = self.stateList[self.currentStateIndex]
        else:
            self.currentStateIndex +=1
            self.currentState = self.stateList[self.currentStateIndex]
            self.stateHasChanged = True

            # Check if we need to skip this state when target temp is 0
            while (self.currentState[state_index_temp_target] == 0.0) or \
                  (self.currentState[state_index_temp_target] - self.hltTempOverShoot == 0.0):
                self.currentStateIndex +=1
                self.currentState = self.stateList[self.currentStateIndex]

        if self.currentState[state_index_time] > 0:
            # Start the timer
            self.timeInState = self.currentState[state_index_time] * 60  # convert from minutes to seconds
            self.timeLeft = self.timeInState
            self.timerStart = time.mktime(time.gmtime())
        else:
            self.timeLeft = 0

    def abort(self):
        # Reached last state - return to initial state
        self.currentStateIndex = sched_index_start
        self.currentState = self.stateList[self.currentStateIndex]

    def userActionReceived(self):
        # triggered by user U/I action or other means
        # if self.currentState[state_index_time] == time_wait:
        # Proceed to next state
        self.handleStateChange()

        return self.currentState, self.timeLeft, True

    def preheatTempReached(self):
        # to be triggered in a pre-heat state by caller when desired temperature is reached
        # Proceed to next state
        self.handleStateChange()

        return self.currentState, self.timeLeft, True

    def getHltTempOvershoot(self):
        return self.hltTempOverShoot

    def setHltTempOvershoot(self, temp):
        self.hltTempOverShoot = temp

    def getHltMaxTargetTempOvershoot(self):
        return self.hltMaxTargetTempOvershoot

    def setHltMaxTargetTempOvershoot(self, temp):
        self.hltMaxTargetTempOvershoot = temp

    def getStep1StateInfo(self):
        return self.stateList[sched_index_step1]

    def getStep2StateInfo(self):
        return self.stateList[sched_index_step2]

    def getStep3StateInfo(self):
        return self.stateList[sched_index_step3]

    def setStep1StateInfo(self, state):
        self.stateList[sched_index_step1] = state

    def setStep2StateInfo(self, state):
        self.stateList[sched_index_step2] = state

        # Set step 2 preheat to appropriate temperature
        if self.stateList[sched_index_step2][state_index_temp_target] != 0:
            self.stateList[sched_index_pre_step2][state_index_temp_target] = self.stateList[sched_index_step2][state_index_temp_target] + self.hltTempOverShoot

    def setStep3StateInfo(self, state):
        self.stateList[sched_index_step3] = state

        # Set step 3 preheat to appropriate temperature
        if self.stateList[sched_index_step3][state_index_temp_target] != 0:
            self.stateList[sched_index_pre_step3][state_index_temp_target] = self.stateList[sched_index_step3][state_index_temp_target] + self.hltTempOverShoot

    def getMashInTemperature(self):
        return self.stateList[sched_index_hlt_preheat][state_index_temp_target]

    def setMashInTemperature(self, temp):
        self.stateList[sched_index_hlt_preheat][state_index_temp_target] = temp
        self.stateList[sched_index_mlt_preheat][state_index_temp_target] = temp
        self.stateList[sched_index_mlt_preheat_wait][state_index_temp_target] = temp
        self.stateList[sched_index_wait][state_index_temp_target] = temp

    def getMashOutTemperature(self):
        return self.stateList[sched_index_mashout][state_index_temp_target]

    def setMashOutTemperature(self, temp):
        self.stateList[sched_index_pre_mashout][state_index_temp_target] = temp + self.hltTempOverShoot
        self.stateList[sched_index_mashout][state_index_temp_target] = temp

    def getMashOutTime(self):
        return self.stateList[sched_index_mashout][state_index_time]

    def setMashOutTime(self, time_to_set):
        self.stateList[sched_index_mashout][state_index_time] = time_to_set

    def getSpargeTemperature(self):
        return self.stateList[sched_index_sparge][state_index_temp_target]

    def setSpargeTemperature(self, temp):
        self.stateList[sched_index_sparge_wait][state_index_temp_target] = temp
        self.stateList[sched_index_sparge][state_index_temp_target] = temp
        self.stateList[sched_index_sparge2_preheat][state_index_temp_target] = temp
        self.stateList[sched_index_sparge2_wait][state_index_temp_target] = temp
        self.stateList[sched_index_sparge2][state_index_temp_target] = temp

    def fsmGetUpdate(self):
        # Update time counter - if necessary
        if self.currentState[state_index_time] > time_to_heat_hlt:
            self.timeLeft = self.timeInState - (time.mktime(time.gmtime()) - self.timerStart)
            if self.timeLeft <= 0:
                self.handleStateChange()
                self.stateHasChanged = True
            else:
                self.stateHasChanged = False
        else:
            self.stateHasChanged = False

        return self.currentState, self.timeLeft, self.stateHasChanged


class BrewTempSensor:
    def __init__(self, sensor_device, calib_adjustment):
        self.tempSensor = sensor_device
        self.calibAdjust = calib_adjustment
        self.f = 0
        self.lines = 0
        os.system('modprobe w1-gpio')
        os.system('modprobe w1-therm')

    def getCalibAdjustment(self):
        return self.calibAdjust

    def setCalibAdjustment(self, calib_adjustment):
        self.calibAdjust = calib_adjustment

    def readTempRaw(self):
        try:
            self.f = open(self.tempSensor, 'r')
        except IOError:
            print('cannot open ', self.tempSensor)
            return 'empty'
        else:
            self.lines = self.f.readlines()
            self.f.close()
            return self.lines

    def readTempCelcius(self):
        rawTemp = self.readTempRaw()
        if rawTemp != 'empty':
            while rawTemp[0].strip()[-3:] != 'YES':
                time.sleep(0.2)
                rawTemp = temp_raw()

            tempOutput = rawTemp[1].find('t=')
            if tempOutput != -1:
                tempString = self.lines[1].strip()[tempOutput+2:]
            else:
                tempString = "-1"

            temp_c = float(tempString) / 1000.0 + self.calibAdjust
        else:
            temp_c = -99

        return temp_c

    def readTempFarenheit(self):
        temp_f = self.readTempCelcius() * 9.0 / 5.0 + 32.0
        return temp_f


class BrewSysRelay:
    #global bus
    def __init__(self):
        self.bus = smbus2.SMBus(1)       # 0 = /dev/i2c-0 (port I2C0), 1 = /dev/i2c-1 (port I2C1)
        self.DEVICE_ADDRESS = 0x20      # 7 bit address (will be left shifted to add the read write bit)
        self.DEVICE_REG_MODE1 = 0x06
        self.DEVICE_REG_DATA = 0xff
        self.bus.write_byte_data(self.DEVICE_ADDRESS, self.DEVICE_REG_MODE1, self.DEVICE_REG_DATA)

    def ON_1(self):
        self.DEVICE_REG_DATA &= ~(0x1<<0)
        self.bus.write_byte_data(self.DEVICE_ADDRESS, self.DEVICE_REG_MODE1, self.DEVICE_REG_DATA)

    def ON_2(self):
        self.DEVICE_REG_DATA &= ~(0x1<<1)
        self.bus.write_byte_data(self.DEVICE_ADDRESS, self.DEVICE_REG_MODE1, self.DEVICE_REG_DATA)

    def ON_3(self):
        self.DEVICE_REG_DATA &= ~(0x1<<2)
        self.bus.write_byte_data(self.DEVICE_ADDRESS, self.DEVICE_REG_MODE1, self.DEVICE_REG_DATA)

    def ON_4(self):
        self.DEVICE_REG_DATA &= ~(0x1<<3)
        self.bus.write_byte_data(self.DEVICE_ADDRESS, self.DEVICE_REG_MODE1, self.DEVICE_REG_DATA)

    def OFF_1(self):
        self.DEVICE_REG_DATA |= (0x1<<0)
        self.bus.write_byte_data(self.DEVICE_ADDRESS, self.DEVICE_REG_MODE1, self.DEVICE_REG_DATA)

    def OFF_2(self):
        self.DEVICE_REG_DATA |= (0x1<<1)
        self.bus.write_byte_data(self.DEVICE_ADDRESS, self.DEVICE_REG_MODE1, self.DEVICE_REG_DATA)

    def OFF_3(self):
        self.DEVICE_REG_DATA |= (0x1<<2)
        self.bus.write_byte_data(self.DEVICE_ADDRESS, self.DEVICE_REG_MODE1, self.DEVICE_REG_DATA)

    def OFF_4(self):
        self.DEVICE_REG_DATA |= (0x1<<3)
        self.bus.write_byte_data(self.DEVICE_ADDRESS, self.DEVICE_REG_MODE1, self.DEVICE_REG_DATA)


class Brew1WireSwitch:
    def __init__(self, switch_device):
        self.switchDevice = switch_device
        os.system('sudo modprobe w1-gpio')
        os.system('sudo modprobe w1-ds2413')
        time.sleep(1)
        call(["sudo", "chmod", "777", switch_device])

    def closeSwitchA(self):
        try:
            self.f = open(self.switchDevice, 'wb')
        except IOError:
            print('cannot open ', self.switchDevice)
            return 'empty'
        else:
            self.f.write(str(2))
            self.f.close()

    def closeSwitchB(self):
        try:
            self.f = open(self.switchDevice, 'wb')
        except IOError:
            print('cannot open ', self.switchDevice)
            return 'empty'
        else:
            self.f.write(str(2))
            self.f.close()

    def openSwitchAll(self):
        try:
            self.f = open(self.switchDevice, 'wb')
        except IOError:
            print('cannot open ', self.switchDevice)
            return 'empty'
        else:
            self.f.write(str(3))
            self.f.close()


