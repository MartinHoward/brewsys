#!/usr/bin/env python3
import sys
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from BrewSysController import BrewSysController

sim_mode = '--hardware' not in sys.argv
controller = BrewSysController(sim_mode=sim_mode)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    controller.stop()


app = FastAPI(lifespan=lifespan)
app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
async def index():
    return FileResponse('static/index.html')


@app.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(controller.get_state())
            await asyncio.sleep(2)
    except (WebSocketDisconnect, Exception):
        pass


@app.get('/state')
async def get_state():
    return controller.get_state()


@app.post('/proceed')
async def proceed():
    return controller.proceed()


@app.post('/abort')
async def abort():
    return controller.abort()


@app.post('/override/heater')
async def toggle_heater():
    return controller.toggle_heater_override()


@app.post('/override/hlt_pump')
async def toggle_hlt_pump():
    return controller.toggle_hlt_pump_override()


@app.post('/override/mlt_pump')
async def toggle_mlt_pump():
    return controller.toggle_mlt_pump_override()


@app.post('/settings')
async def update_settings(request: Request):
    settings = await request.json()
    success = controller.update_settings(settings)
    state = controller.get_state()
    return {'success': success, **state}


if __name__ == '__main__':
    mode = 'hardware' if not sim_mode else 'simulation'
    print(f'Starting BrewSys web interface in {mode} mode on http://0.0.0.0:9929')
    uvicorn.run(app, host='0.0.0.0', port=9929)
