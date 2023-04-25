#!/usr/bin/python

#from __future__ import division
import smbus2
import signal
import sys
import PyQt5.QtWidgets as QtWidgets
import pickle
from PyQt5 import QtCore
from BrewSysMain import Ui_brewSysMain
from BrewSysTools import *

# 1-wire device files
hlt_temp_sensor = '/sys/bus/w1/devices/28-021601a96aff/w1_slave'
mlt_in_temp_sensor = '/sys/bus/w1/devices/28-03160468a3ff/w1_slave'
mlt_temp_sensor = '/sys/bus/w1/devices/28-031565df43ff/w1_slave'
wire1_switch = '/sys/bus/w1/devices/3a-000000211dad/output'

class BrewSysApp(QtWidgets.QMainWindow, Ui_brewSysMain):
    def __init__(self, sim_mode):
        QtWidgets.QMainWindow.__init__(self)
        Ui_brewSysMain.__init__(self)
        self.setupUi(self)
        self.timer1 = QtCore.QTimer()
        self.simMode = sim_mode

        # set up temp sensors
        if not self.simMode:
            self.hltTempSensor = BrewTempSensor(hlt_temp_sensor, 0)
            self.mltInTempSensor = BrewTempSensor(mlt_in_temp_sensor, 0)
            self.mltTempSensor = BrewTempSensor(mlt_temp_sensor, 0)
        else:
            self.hltTemp = 50.0
            self.mltInTemp = 50.0
            self.mltTemp = 50.0

        if not self.simMode:
            # set up 1wire switch and relays
            self.heaterSwitch = Brew1WireSwitch(wire1_switch)
            self.onboardRelays = BrewSysRelay()

        # initialize other variables
        self.tempTargetTolerance = 0.5
        self.tempDisplayTolerance = 0.5
        self.enableHltHeater = False
        self.hltHeaterOverride = False
        self.hltPumpOverride = False
        self.mltPumpOverride = False
        self.simTempLag = 0

        # initialize state machine with mash recipe variables
        self.brewFSM = BrewSysFSM()
        self.restoreBrewFsmState()
        self.brewFSMState, self.fsmStateTimeLeft, self.fsmChange = self.brewFSM.fsmGetUpdate()
        self.handleFsmStateChange(self.brewFSMState)
        self.proceedButton.setText(self.brewFSMState[0])
        self.setHltPumpStatusDisplay(self.brewFSMState[4])
        self.setMtPumpStatusDisplay(self.brewFSMState[5])
        self.persistence_counter = 0

        self.timer1.timeout.connect(lambda: self.periodic())
        self.proceedButton.clicked.connect(lambda: self.userProceed())
        self.stepMashApplyButton.clicked.connect(lambda: self.updateStepMashSettings())
        self.hltHeaterToggleButton.clicked.connect(lambda: self.overrideHltHeater())
        self.hltPumpToggleButton.clicked.connect(lambda: self.overrideHltPump())
        self.mltPumpToggleButton.clicked.connect(lambda: self.overrideMltPump())
        self.pauseSpargeButton.clicked.connect(lambda: self.handleSpargePauseButtonPress())
        self.step2EnableCheckBox.clicked.connect(lambda: self.handleStep2CheckBox())
        self.step3EnableCheckBox.clicked.connect(lambda: self.handleStep3CheckBox())
        self.timer1.start(5000)

        # initialize mash step controls
        self.updateStepMashControls()

    def updateStepMashControls(self):
        # First update the step 1 controls
        stepStateInfo = self.brewFSM.getStep1StateInfo()
        self.step1TempSpinBox.setValue(stepStateInfo[state_index_temp_target])
        self.step1TimeSpinBox.setValue(stepStateInfo[state_index_time])
        self.mashInTempSpinBox.setValue(self.brewFSM.getMashInTemperature())

        # Update step 2 controls
        stepStateInfo = self.brewFSM.getStep2StateInfo()
        self.step2TempSpinBox.setValue(stepStateInfo[state_index_temp_target])
        self.step2TimeSpinBox.setValue(stepStateInfo[state_index_time])

        # Update step 3 controls
        stepStateInfo = self.brewFSM.getStep3StateInfo()
        self.step3TempSpinBox.setValue(stepStateInfo[state_index_temp_target])
        self.step3TimeSpinBox.setValue(stepStateInfo[state_index_time])

        # Update mashout/sparge controls
        self.mashoutTempSpinBox.setValue(self.brewFSM.getMashOutTemperature())
        self.mashoutTimeSpinBox.setValue(self.brewFSM.getMashOutTime())
        self.spargeTempSpinBox.setValue(self.brewFSM.getSpargeTemperature())

        # Update general settings controls
        self.hltOvertempSpinBox.setValue(self.brewFSM.getHltTempOvershoot())
        self.hltMaxOvershootSpinBox.setValue(self.brewFSM.getHltMaxTargetTempOvershoot())

        if not self.simMode:
            self.hltTempCalibSpinBox.setValue(self.hltTempSensor.getCalibAdjustment())
            self.mltInTempCalibSpinBox.setValue(self.mltInTempSensor.getCalibAdjustment())
            self.mltTempCalibSpinBox.setValue(self.mltTempSensor.getCalibAdjustment())

    def updateStepMashSettings(self):
        if self.brewFSMState == mash_start:
            # Update general settings
            self.brewFSM.setHltTempOvershoot(self.hltOvertempSpinBox.value())
            self.brewFSM.setHltMaxTargetTempOvershoot(self.hltMaxOvershootSpinBox.value())

            if not self.simMode:
                self.hltTempSensor.setCalibAdjustment(self.hltTempCalibSpinBox.value())
                self.mltInTempSensor.setCalibAdjustment(self.mltInTempCalibSpinBox.value())
                self.mltTempSensor.setCalibAdjustment(self.mltTempCalibSpinBox.value())

            # Update step 1 settings
            stepStateInfo = self.brewFSM.getStep1StateInfo()
            stepStateInfo[state_index_temp_target] = self.step1TempSpinBox.value()
            stepStateInfo[state_index_time] = self.step1TimeSpinBox.value()
            self.brewFSM.setStep1StateInfo(stepStateInfo)
            self.brewFSM.setMashInTemperature(self.mashInTempSpinBox.value())

            # Update step 2 settings
            stepStateInfo = self.brewFSM.getStep2StateInfo()
            stepStateInfo[state_index_temp_target] = self.step2TempSpinBox.value()
            stepStateInfo[state_index_time] = self.step2TimeSpinBox.value()
            self.brewFSM.setStep2StateInfo(stepStateInfo)

            # Update step 3 settings
            stepStateInfo = self.brewFSM.getStep3StateInfo()
            stepStateInfo[state_index_temp_target] = self.step3TempSpinBox.value()
            stepStateInfo[state_index_time] = self.step3TimeSpinBox.value()
            self.brewFSM.setStep3StateInfo(stepStateInfo)

            # Update mashout/sparge settings
            self.brewFSM.setMashOutTemperature(self.mashoutTempSpinBox.value())
            self.brewFSM.setMashOutTime(self.mashoutTimeSpinBox.value())
            self.brewFSM.setSpargeTemperature(self.spargeTempSpinBox.value())

            # Disable Apply button - enable proceed/status button
            self.stepMashApplyButton.setText("Abort!")
            self.proceedButton.setEnabled(True)
            self.step2EnableCheckBox.setEnabled(False)
            self.step3EnableCheckBox.setEnabled(False)
        else:
            self.abortFsm()

    def handleStep2CheckBox(self):
        if self.step2EnableCheckBox.isChecked():
            self.step2TempSpinBox.setEnabled(True)
            self.step2TimeSpinBox.setEnabled(True)
            self.step2Label_1.setEnabled(True)
            self.step2Label_2.setEnabled(True)
        else:
            # Disable controls
            self.step2TempSpinBox.setEnabled(False)
            self.step2TimeSpinBox.setEnabled(False)
            self.step2Label_1.setEnabled(False)
            self.step2Label_2.setEnabled(False)

            # Set to defaults
            stepStateInfo = self.brewFSM.getStep2StateInfo()
            stepStateInfo[state_index_temp_target] = 0.0
            stepStateInfo[state_index_time] = 0
            self.brewFSM.setStep2StateInfo(stepStateInfo)

        # Update controls
        self.updateStepMashControls()

    def handleStep3CheckBox(self):
        if self.step3EnableCheckBox.isChecked():
            self.step3TempSpinBox.setEnabled(True)
            self.step3TimeSpinBox.setEnabled(True)
            self.step3Label_1.setEnabled(True)
            self.step3Label_2.setEnabled(True)
        else:
            self.step3TempSpinBox.setEnabled(False)
            self.step3TimeSpinBox.setEnabled(False)
            self.step3Label_1.setEnabled(False)
            self.step3Label_2.setEnabled(False)

            # Set to defaults
            stepStateInfo = self.brewFSM.getStep3StateInfo()
            stepStateInfo[state_index_temp_target] = 0.0
            stepStateInfo[state_index_time] = 0
            self.brewFSM.setStep3StateInfo(stepStateInfo)

        # Update controls
        self.updateStepMashControls()

    def updateStepMashIndicators(self, state):
        if state == mash_start:
            self.step1Indicator.setStyleSheet("Background-color:grey")
            self.step2Indicator.setStyleSheet("Background-color:grey")
            self.step3Indicator.setStyleSheet("Background-color:grey")
        elif state == mash_step1_rest:
            self.step1Indicator.setStyleSheet("Background-color:yellow")
        elif state == mash_pre_step2:
            self.step1Indicator.setStyleSheet("Background-color:lightgreen")
        elif state == mash_step2_rest:
            self.step1Indicator.setStyleSheet("Background-color:lightgreen")
            self.step2Indicator.setStyleSheet("Background-color:yellow")
        elif state == mash_pre_step3:
            self.step1Indicator.setStyleSheet("Background-color:lightgreen")
            self.step2Indicator.setStyleSheet("Background-color:lightgreen")
        elif state == mash_step3_rest:
            self.step1Indicator.setStyleSheet("Background-color:lightgreen")
            self.step2Indicator.setStyleSheet("Background-color:lightgreen")
            self.step3Indicator.setStyleSheet("Background-color:yellow")
        elif state == mash_pre_mash_out:
            self.step1Indicator.setStyleSheet("Background-color:lightgreen")
            if self.step2EnableCheckBox.isChecked():
                self.step2Indicator.setStyleSheet("Background-color:lightgreen")
            if self.step3EnableCheckBox.isChecked():
                self.step3Indicator.setStyleSheet("Background-color:lightgreen")

    def writeHltTempDisplay(self, temp, target_temp):
        display_string = "%.1f" % float(temp)

        if target_temp > 0:
            display_string = display_string + '/' + str(float(target_temp))

        if target_temp > 0:
            if temp < (target_temp - self.tempDisplayTolerance):
                text_color = "blue"
            else:
                if temp > (target_temp + self.tempDisplayTolerance):
                    text_color = "red"
                else:
                    text_color = "green"
        else:
            text_color = "black"

        self.hltTempDisplay.clear()
        self.hltTempDisplay.setStyleSheet("QTextEdit {color : " + text_color + "}")
        self.hltTempDisplay.setAlignment(QtCore.Qt.AlignCenter)
        self.hltTempDisplay.append(display_string)

    def writeMltInTempDisplay(self, temp, target_temp):
        display_string = "%.1f" % float(temp)

        if target_temp > 0:
            display_string = display_string + '/' + str(float(target_temp))

        if target_temp > 0:
            if temp < (target_temp - self.tempDisplayTolerance):
                text_color = "blue"
            else:
                if temp > (target_temp + self.tempDisplayTolerance):
                    text_color = "red"
                else:
                    text_color = "green"
        else:
            text_color = "black"

        self.mtInTempDisplay.clear()
        self.mtInTempDisplay.setStyleSheet("QTextEdit {color : " + text_color + "}")
        self.mtInTempDisplay.setAlignment(QtCore.Qt.AlignCenter)
        self.mtInTempDisplay.append(display_string)

    def writeMltOutTempDisplay(self, temp, target_temp):
        display_string = "%.1f" % float(temp)

        if target_temp > 0:
            display_string = display_string + '/' + str(float(target_temp))

        if target_temp > 0:
            if temp < (target_temp - self.tempDisplayTolerance):
                text_color = "blue"
            else:
                if temp > (target_temp + self.tempDisplayTolerance):
                    text_color = "red"
                else:
                    text_color = "green"
        else:
            text_color = "black"

        self.mtOutTempDisplay.clear()
        self.mtOutTempDisplay.setStyleSheet("QTextEdit {color : " + text_color + "}")
        self.mtOutTempDisplay.setAlignment(QtCore.Qt.AlignCenter)
        self.mtOutTempDisplay.append(display_string)

    def setHltHeaterStatusDisplay(self, enabled):
        if enabled == False:
            self.hltHeaterStatusDisplay.setStyleSheet("QLineEdit {background-color : white}")
            self.hltHeaterStatusDisplay.setText("Stopped")
        else:
            self.hltHeaterStatusDisplay.setStyleSheet("QLineEdit {background-color : orange}")
            self.hltHeaterStatusDisplay.setText("Heating")

    def setHltPumpStatusDisplay(self, enabled):
        if enabled == False:
            self.hltPumpStatusDisplay.setStyleSheet("QLineEdit {background-color : red}")
            self.hltPumpStatusDisplay.setText("Stopped")
        else:
            self.hltPumpStatusDisplay.setStyleSheet("QLineEdit {background-color : lightgreen}")
            self.hltPumpStatusDisplay.setText("Working")

    def setMtPumpStatusDisplay(self, enabled):
        if enabled == False:
            self.mtPumpStatusDisplay.setStyleSheet("QLineEdit {background-color : red}")
            self.mtPumpStatusDisplay.setText("Stopped")
        else:
            self.mtPumpStatusDisplay.setStyleSheet("QLineEdit {background-color : lightgreen}")
            self.mtPumpStatusDisplay.setText("Working")

    def simulateTemperature(self, hltTemp, mltInTemp, mltTemp, heaterOn):
        if heaterOn:
            self.simTempLag = 3
        elif self.simTempLag > 0:
            self.simTempLag -= 1

        if heaterOn or self.simTempLag > 0:
            heating = True
        else:
            heating = False

        if self.brewFSMState == mash_hlt_heating:
            if heating == True:
                hltTemp += 0.2
            else:
                hltTemp -= 0.05
        elif self.brewFSMState == mash_mt_heating:
            if heating == True:
                hltTemp += 0.1
                mltTemp += 0.2
            else:
                hltTemp -= 0.05
            mltInTemp = mltTemp + (hltTemp - mltTemp) / 2
        else:
            if heating == True:
                hltTemp += 0.2
            else:
                hltTemp -= 0.05

            mltInTemp = hltTemp
            mltTemp = hltTemp

        return hltTemp, mltInTemp, mltTemp

    def userProceed(self):
        self.brewFSMState, self.fsmStateTimeLeft, self.fsmChange = self.brewFSM.userActionReceived()
        self.periodic()

    def abortFsm(self):
        self.brewFSM.abort()
        self.periodic()
        self.stepMashApplyButton.setText("Apply")
        self.proceedButton.setEnabled(False)
        self.step2EnableCheckBox.setEnabled(True)
        self.step3EnableCheckBox.setEnabled(True)
        self.clearBrewFsmState()
        self.updateStepMashControls()

    def isHltPumpToBeEnabled(self, fsm_enable):
        if fsm_enable == True:
            if self.hltPumpOverride == False:
                return True
            else:
                return False
        else:
            if (self.hltPumpOverride == False):
                return False
            else:
                return True

    def enableHltPump(self, enable):
        if (self.simMode == False):
            if enable == True:
                self.onboardRelays.ON_1()
            else:
                self.onboardRelays.OFF_1()

    def overrideHltPump(self):
        if self.brewFSMState == mash_pre_check:
            if self.hltPumpOverride == True:
                self.hltPumpOverride = False
            else:
                self.hltPumpOverride = True
        else:
            self.hltPumpOverride = False
        self.periodic()

    def isMltPumpToBeEnabled(self, fsm_enable):
        if fsm_enable == True:
            if self.mltPumpOverride == False:
                return True
            else:
                return False
        else:
            if (self.mltPumpOverride == False):
                return False
            else:
                return True

    def enableMltPump(self, enable):
        if (self.simMode == False):
            if enable == True:
                self.onboardRelays.ON_2()
            else:
                self.onboardRelays.OFF_2()

    def overrideMltPump(self):
        if (self.brewFSMState == mash_pre_check) or \
                (self.brewFSMState == mash_sparge) or \
                (self.brewFSMState == mash_sparge2):
            if self.mltPumpOverride == True:
                self.mltPumpOverride = False
            else:
                self.mltPumpOverride = True
        else:
            self.mltPumpOverride = False
        self.periodic()

    def isHltHeaterToBeEnabled(self, enable):
        if enable == True:
            if self.hltHeaterOverride == False:
                return True
            else:
                return False
        else:
            if self.hltHeaterOverride == False:
                return False
            else:
                return True

    def enableHltHeatingElement(self, enable):
        if (self.simMode == False):
            if enable == True:
                self.heaterSwitch.closeSwitchA()
            else:
                self.heaterSwitch.openSwitchAll()

    def overrideHltHeater(self):
        if self.brewFSMState == mash_pre_check:
            if self.hltHeaterOverride == True:
                self.hltHeaterOverride = False
            else:
                self.hltHeaterOverride = True
        else:
            self.hltHeaterOverride = False
        self.periodic()

    def tempControl(self, currentTemp, hltTemp, hltHeaterState):
        targetTemp = self.brewFSMState[state_index_temp_target]
        if currentTemp <= (targetTemp - self.tempTargetTolerance):
            enableHeater = True
        elif currentTemp >= targetTemp:
            enableHeater = False
        else:
            enableHeater = hltHeaterState

        # Need to check if HLT temp is too high above the target during MLT preheat state
        if self.brewFSMState == mash_mt_heating or self.brewFSMState == mash_mt_heating_wait:
            if currentTemp <= (targetTemp - self.tempTargetTolerance):
                # If we are still well off the target temp check that we are under max HLT overshoot
                if hltTemp > (targetTemp + self.brewFSM.getHltMaxTargetTempOvershoot()):
                    enableHeater = False
                else:
                    enableHeater = True
            # elif currentTemp <= targetTemp:
            #    enableHeater = True

        return enableHeater

    def displayTimeLeft(self, timeInSeconds):
        if timeInSeconds != 0:
            self.label_TimeLeft.show()
            self.timeLeftDisplay.show()
            # First find the number of minutes left
            mins = timeInSeconds // 60
            secs = timeInSeconds % 60
            self.timeLeftDisplay.display('{:d}'.format(int(mins)) + ":" + '{:02d}'.format(int(secs)))
        else:
            self.label_TimeLeft.hide()
            self.timeLeftDisplay.hide()

    def handleSpargePauseButtonPress(self):
        self.overrideMltPump()

        if self.mltPumpOverride == True:
            self.pauseSpargeButton.setText("Resume Sparge")
        else:
            self.pauseSpargeButton.setText("Pause Sparge")

    def restoreBrewFsmState(self):
        # Check for persistence file - load saved state if it exists
        try:
            f = open('BrewSysFSM.persist', "rb")
        except IOError:
            # Do nothing
            print("BrewSysFSM.persist not found")
        else:
            # Load saved state
            self.brewFSM = pickle.load(f)
            f.close()

    def saveBrewFsmState(self):
        # Update persistence file every few calls
        if self.persistence_counter >= 5:
            f = open('BrewSysFSM.persist', "wb")
            pickle.dump(self.brewFSM, f)
            f.close()
            self.persistence_counter = 0

    def clearBrewFsmState(self):
        # Delete persistence file
        try:
            os.remove('BrewSysFSM.persist')
        except OSError:
            print("BrewSysFSM.persist not found")
        else:
            print("BrewSysFSM.persist deleted")

    def handleFsmStateChange(self, state):
        print(state)
        self.proceedButton.setEnabled(True)
        if self.brewFSMState == mash_start:
            self.clearBrewFsmState()
            self.proceedButton.setEnabled(False)

        if (self.brewFSMState == mash_sparge) or (self.brewFSMState == mash_sparge2):
            self.pauseSpargeButton.show()
        else:
            self.pauseSpargeButton.hide()

    def periodic(self):
        # Needs to be called periodically
        self.persistence_counter += 1

        if self.fsmChange == True:
            self.handleFsmStateChange(self.brewFSMState)

        #### Get current temp readings
        if (self.simMode == False):
            self.hltTemp = self.hltTempSensor.readTempCelcius()
            self.mltInTemp = self.mltInTempSensor.readTempCelcius()
            self.mltTemp = self.mltTempSensor.readTempCelcius()
        else:
            self.hltTemp, self.mltInTemp, self.mltTemp = self.simulateTemperature(self.hltTemp, self.mltInTemp,
                                                                                  self.mltTemp, self.enableHltHeater)

        #### Take appropriate actions - state machine processing
        self.brewFSMState, self.fsmStateTimeLeft, self.fsmChange = self.brewFSM.fsmGetUpdate()

        self.proceedButton.setText(self.brewFSMState[state_index_text_disp])

        # Check if HLT temperature reached
        if self.brewFSMState[state_index_time] == time_to_heat_hlt:
            if self.hltTemp >= self.brewFSMState[state_index_temp_target]:
                self.brewFSMState, self.fsmStateTimeLeft, self.fsmChange = self.brewFSM.preheatTempReached()

        # Check if MLT temperature reached
        if self.brewFSMState[state_index_time] == time_to_heat_mlt:
            if self.mltTemp >= self.brewFSMState[state_index_temp_target]:
                self.brewFSMState, self.fsmStateTimeLeft, self.fsmChange = self.brewFSM.preheatTempReached()

        # Check if HLT heater needs to be turned on/off
        if self.brewFSMState[state_index_temp_source] == temp_src_hlt:
            self.enableHltHeater = self.tempControl(self.hltTemp, self.hltTemp, self.enableHltHeater)
        elif self.brewFSMState[state_index_temp_source] == temp_src_mt_in:
            self.enableHltHeater = self.tempControl(self.mltInTemp, self.hltTemp, self.enableHltHeater)
        else:
            self.enableHltHeater = self.tempControl(self.mltTemp, self.hltTemp, self.enableHltHeater)

        # Control relays
        self.enableHltPump(self.isHltPumpToBeEnabled(self.brewFSMState[state_index_hlt_pump]))
        self.enableMltPump(self.isMltPumpToBeEnabled(self.brewFSMState[state_index_mt_pump]))
        self.enableHltHeatingElement(self.isHltHeaterToBeEnabled(self.enableHltHeater))

        #### Update dashboard
        # Update temp display
        if self.brewFSMState[state_index_temp_source] == temp_src_hlt:
            self.writeHltTempDisplay(self.hltTemp, self.brewFSMState[state_index_temp_target])
            self.writeMltInTempDisplay(self.mltInTemp, 0)
            self.writeMltOutTempDisplay(self.mltTemp, 0)
        elif self.brewFSMState[state_index_temp_source] == temp_src_mt_in:
            self.writeHltTempDisplay(self.hltTemp, 0)
            self.writeMltInTempDisplay(self.mltInTemp, self.brewFSMState[state_index_temp_target])
            self.writeMltOutTempDisplay(self.mltTemp, self.brewFSMState[state_index_temp_target])
        else:
            self.writeHltTempDisplay(self.hltTemp, 0)
            self.writeMltInTempDisplay(self.mltInTemp, 0)
            self.writeMltOutTempDisplay(self.mltTemp, self.brewFSMState[state_index_temp_target])

        # Update pump/heater status display
        self.setHltPumpStatusDisplay(self.isHltPumpToBeEnabled(self.brewFSMState[state_index_hlt_pump]))
        self.setMtPumpStatusDisplay(self.isMltPumpToBeEnabled(self.brewFSMState[state_index_mt_pump]))
        self.setHltHeaterStatusDisplay(self.isHltHeaterToBeEnabled(self.enableHltHeater))

        # Update timer display
        self.displayTimeLeft(self.fsmStateTimeLeft)

        # Update step mash indicators
        self.updateStepMashIndicators(self.brewFSMState)

        # Update toggle buttons
        if self.brewFSMState == mash_pre_check:
            self.hltHeaterToggleButton.setEnabled(True)
            self.hltPumpToggleButton.setEnabled(True)
            self.mltPumpToggleButton.setEnabled(True)
        else:
            self.hltHeaterToggleButton.setEnabled(False)
            self.hltPumpToggleButton.setEnabled(False)
            self.mltPumpToggleButton.setEnabled(False)

        # Save FSM state - every once in a while
        if self.brewFSMState != mash_start:
            if self.persistence_counter >= 5:
                self.saveBrewFsmState()
                self.persistence_counter = 0
            self.stepMashApplyButton.setText("Abort!")
        else:
            self.stepMashApplyButton.setText("Apply")

        # TODO: Save temp readings in a comma delim file
        # Time,HLT Temp,MLT In Temp,MLT Temp


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    widget = QtWidgets.QDesktopWidget()

    window = BrewSysApp(False)
    rect = widget.availableGeometry(0)
    window.move(rect.left(), rect.top())
    # window.resize(rect.width(),rect.height())

    print("Window width: ", rect.width(), ", height: ", rect.height())

    window.show()
    sys.exit(app.exec_())
