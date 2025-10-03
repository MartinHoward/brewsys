# Flask project structure for BrewSys web UI

webapp/
├── app.py              # Main Flask app
├── templates/          # Jinja2 HTML templates
│   ├── base.html       # Base template
│   ├── status.html     # Main status page
│   └── ...             # Other pages as needed
├── static/             # Static files (CSS, JS, images)
│   ├── style.css       # Main stylesheet
│   └── ...
└── ...

- app.py: Flask routes and backend logic
- templates/: HTML templates for each page
- static/: CSS/JS for styling and interactivity

The main status page (status.html) will show:
- Temperatures (HLT, MT In, MT Out)
- Current state
- Heating element status
- Motor/pump status
- Time left
- Proceed button (if needed)

Other pages can be added as needed for configuration, logs, etc.