
from flask import Flask, render_template, jsonify, request
from status_provider import BrewSysStatusProvider

app = Flask(__name__)
status_provider = BrewSysStatusProvider()

import sys
sys.path.append('../src')
try:
    from BrewSysTools import BrewSysRelay, Brew1WireSwitch
except ImportError:
    BrewSysRelay = None
    Brew1WireSwitch = None

relay = None
switch = None
if not status_provider.sim_mode and BrewSysRelay and Brew1WireSwitch:
    relay = BrewSysRelay()
    switch = Brew1WireSwitch('/sys/bus/w1/devices/3a-000000211dad/output')

@app.route('/')
def status():
    status_data = status_provider.get_status()
    return render_template('status.html', **status_data)

# API endpoint for AJAX polling
@app.route('/api/status')
def api_status():
    status_data = status_provider.get_status()
    return jsonify(status_data)

# API endpoints to control heater and pumps (sim mode only)
@app.route('/api/control', methods=['POST'])
def api_control():
    data = request.json
    changed = False
    if status_provider.sim_mode:
        # Sim mode: just update simulation state
        if 'hlt_heater' in data:
            status_provider._sim_hlt_heater = bool(data['hlt_heater'])
            changed = True
        if 'hlt_pump' in data:
            status_provider._sim_hlt_pump = bool(data['hlt_pump'])
            changed = True
        if 'mt_pump' in data:
            status_provider._sim_mt_pump = bool(data['mt_pump'])
            changed = True
    else:
        # Real hardware control, track last set state for status
        if relay:
            if 'hlt_pump' in data:
                if data['hlt_pump']:
                    relay.ON_1()
                    status_provider._last_hlt_pump = True
                else:
                    relay.OFF_1()
                    status_provider._last_hlt_pump = False
                changed = True
            if 'mt_pump' in data:
                if data['mt_pump']:
                    relay.ON_2()
                    status_provider._last_mt_pump = True
                else:
                    relay.OFF_2()
                    status_provider._last_mt_pump = False
                changed = True
        if switch:
            if 'hlt_heater' in data:
                if data['hlt_heater']:
                    switch.closeSwitchA()
                    status_provider._last_hlt_heater = True
                else:
                    switch.openSwitchAll()
                    status_provider._last_hlt_heater = False
                changed = True
    return jsonify({'success': changed})

# Add more routes for other pages as needed

@app.route('/other')
def other_page():
    return render_template('other.html')

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Run BrewSys Web App')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='Web server IP address (default: 127.0.0.1)')
    args = parser.parse_args()
    app.run(debug=True, host=args.host)
