# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Raspberry Pi Beer Brewing System (BrewSys v0.3) — a PyQt5 desktop GUI that automates a multi-vessel home brewery by controlling heaters, pumps, and temperature sensors via Raspberry Pi GPIO.

## Running the Application

```bash
cd src
python BrewSysApp.py        # runs with sim_mode=True (safe on non-Pi hardware)
```

The `__main__` block hardcodes `sim_mode=True`, so the app runs on any machine without attempting to open 1-Wire or I2C hardware. Set `sim_mode=False` only on a Raspberry Pi with the hardware connected.

## Regenerating the UI File

`BrewSysMain.py` is auto-generated from `BrewSysMain.ui` by PyQt5's `pyuic5` — do not edit it directly:

```bash
cd src
pyuic5 BrewSysMain.ui -o BrewSysMain.py
```

## Architecture

The app has three logical layers that live across two files:

### `BrewSysTools.py` — data model and hardware drivers

- **State table**: Each brewing stage is a plain Python list with 9 positional fields. The `state_index_*` constants are the only safe way to access fields. Special `time` values (`time_to_heat_hlt`, `time_to_heat_mlt`, `time_wait_user`) drive the FSM instead of a countdown.
- **`BrewSysFSM`**: Walks through `mash_schedule` (a fixed ordered list of state lists). Transitions happen via `userActionReceived()`, `preheatTempReached()`, or automatic timer expiry in `fsmGetUpdate()`. Steps 2 and 3 are skipped when their target temp is 0. The FSM also owns the configurable recipe parameters (mash temps, step times, overshoot offsets).
- **Hardware classes**: `BrewTempSensor` reads DS18B20 sensors via the 1-Wire sysfs interface. `BrewSysRelay` drives an I2C relay board (address `0x20`) — relay 1 = HLT pump, relay 2 = MLT pump. `Brew1WireSwitch` controls a DS2413 1-Wire switch for the HLT heating element.

### `BrewSysApp.py` — Qt application and control loop

- `periodic()` is called every 2 seconds by `QTimer`. It queries the FSM, evaluates temperature control (`tempControl()`), drives the hardware relays, and refreshes all UI widgets.
- Temperature readings run in a dedicated background thread (`thr1`) that polls sensors every 5 seconds and writes to `self.hltTemp / mltInTemp / mltTemp`. These are shared with `periodic()` without a lock — reads are atomic on CPython.
- FSM state is pickled to `BrewSysFSM.persist` every 5 `periodic()` calls so a restart can resume mid-brew. The file is deleted on abort or when returning to `mash_start`.
- Override flags (`hltHeaterOverride`, `hltPumpOverride`, `mltPumpOverride`) invert the FSM's requested relay state. Each override is only active when the current FSM state permits it (`state_index_*_override == True`).

### `BrewSysMain.py` — generated UI

Defines `Ui_brewSysMain` with all widget geometry and labels. `BrewSysApp` inherits from both `QMainWindow` and `Ui_brewSysMain` (mixin pattern).

## Key Constants

```
state_index_*   — positional indices into each state list (9 fields)
time_to_heat_hlt / time_to_heat_mlt / time_wait_user — sentinel values for the time field
temp_src_hlt / temp_src_mlt_in / temp_src_mlt — which sensor drives temperature control
```

When the `time` field is a positive integer it represents **minutes**; `fsmGetUpdate()` converts it to seconds internally.
