from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
import websockets
import asyncio
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///drink_tracker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

reset_pending = False


class DeviceStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    added_count = db.Column(db.Integer, default=0)
    consumption_count = db.Column(db.Integer, default=0)
    inventory_count = db.Column(db.Integer, default=0)
    lock_status = db.Column(db.Boolean, default=False)
    lid_status = db.Column(db.Boolean, default=False)
    lockout_remaining = db.Column(db.Integer, default=0)
    consumption_limit = db.Column(db.Integer, default=2)
    lockout_timer = db.Column(db.Integer, default=30)
    lockout_end_time = db.Column(db.DateTime, nullable=True)
    cycle_start_time = db.Column(db.DateTime, nullable=True)
    cycle_end_time = db.Column(db.DateTime, nullable=True)
    cycle_duration = db.Column(db.Integer, default=24*60)
    penalty_multiplier = db.Column(db.Float, default=1.5)

class ConsumptionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    count = db.Column(db.Integer)

with app.app_context():
    db.create_all()

def get_or_create_device_status():
    status = DeviceStatus.query.first()
    if not status:
        status = DeviceStatus()

        now = datetime.utcnow()
        status.cycle_start_time = now
        status.lockout_end_time = None

        db.session.add(status)
        db.session.commit()
        status = DeviceStatus.query.first()

        status.cycle_end_time = status.cycle_start_time + timedelta(seconds=status.cycle_duration)
        db.session.commit()
    return status


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status_update', get_device_status())


@socketio.on('get_initial_status')
def handle_get_initial_status():
    emit('status_update', get_device_status())


@socketio.on('update_settings')
def handle_update_settings(data):
    try:
        if data['confirmation-phrase'] == "I am not lying":
            print(f"Updating settings: {data}")
            status = get_or_create_device_status()
            status.consumption_limit = int(data['consumption-limit'])
            status.cycle_duration = int(data['cycle-duration'])
            status.cycle_end_time = status.cycle_start_time + timedelta(seconds=status.cycle_duration)

            db.session.commit()

            emit('status_update', get_device_status())
            return {'status': 'success'}
        return {'status': 'error', 'message': 'Confirmation phrase is incorrect.'}
    except ValueError:
        return {'status': 'error', 'message': 'Invalid input. Please enter numbers.'}


@socketio.on('reset_device')
def handle_reset_device(data):
    if data['confirmation_phrase'] == "I am not lying":
        global reset_pending
        reset_pending = True

        status = get_or_create_device_status()
        status.consumption_count = 0
        status.lock_status = False
        status.lockout_remaining = 0
        status.lockout_end_time = None
        status.cycle_start_time = datetime.utcnow()
        db.session.commit()

        emit('status_update', get_device_status())

        return {'status': 'success'}
    return {'status': 'error', 'message': 'Confirmation phrase is incorrect.'}

def handle_esp32_status_update(data):
    status = get_or_create_device_status()
    status.added_count = data['totalAddCount']
    status.consumption_count = data['totalRemCount']
    status.inventory_count = data['drinkCount']
    status.lock_status = data['lockState']
    status.lid_status = data['lidClosed']


    # Calculate lockout remaining
    if status.lockout_remaining >= 1:
        now = datetime.utcnow()
        status.lockout_remaining = max(0, int((status.lockout_end_time - now).total_seconds()))

        if status.lockout_remaining == 0:
            status.lockout_end_time = None
    else:
        status.lockout_remaining = 0
        status.lockout_end_time = None

    status.last_updated = datetime.utcnow()
    db.session.commit()

    # Log consumption
    if data['totalRemCount'] > status.consumption_count:
        log = ConsumptionLog(count=data['totalRemCount'] - status.consumption_count)
        db.session.add(log)
        db.session.commit()

    socketio.emit('status_update', get_device_status())

    if status.lid_status and status.consumption_count >= status.consumption_limit:
        penalty = max(0, status.consumption_count - status.consumption_limit)

        if status.lockout_end_time is None:
            if penalty >= 1:
                status.lockout_end_time = status.cycle_start_time + timedelta(seconds=(status.cycle_duration * status.penalty_multiplier))
            else:
                status.lockout_end_time = status.cycle_end_time

        now = datetime.utcnow()
        status.lockout_remaining = max(0, int((status.lockout_end_time - now).total_seconds()))

        db.session.commit()
        return {"action": "lock"}

    if status.lockout_remaining >= 1:
        return {"action": "lock"}
    return {"action": "unlock"}

def check_and_reset_cycle():
    status = get_or_create_device_status()

    now = datetime.utcnow()
    if status.cycle_end_time <= now:
        status.cycle_start_time = now
        status.consumption_count = 0
        status.added_drinks_count = 0  # Reset added drinks count at the start of a new cycle
        status.lock_status = False
        status.cycle_end_time = status.cycle_start_time + timedelta(seconds=status.cycle_duration)
        db.session.commit()

        global reset_pending
        reset_pending = True

def get_device_status():
    status = get_or_create_device_status()
    return {
        'added_count': status.added_count,
        'consumption_count': status.consumption_count,
        'inventory_count': status.inventory_count,
        'lock_status': status.lock_status,
        'lid_status': status.lid_status,
        'lockout_remaining': status.lockout_remaining,
        'consumption_limit': status.consumption_limit,
        'lockout_timer': status.lockout_remaining,
        'cycle_end_time': (status.cycle_end_time + timedelta(hours=8)).strftime("%m/%d/%Y, %I:%M:%S %p"),
    }

# WebSocket handler (runs separately from Flask)
async def websocket_handler(websocket, path):
    # limit = 4
    print(f"Client connected: {path}")

    try:
        async for message in websocket:
            data = json.loads(message)
            resp = {"action": "none"}
            print(data)

            with app.app_context():
                check_and_reset_cycle()

            global reset_pending
            if reset_pending:
                resp = {"action": "reset"}
                reset_pending = False
            elif "totalRemCount" in data:
                with app.app_context():
                    resp = handle_esp32_status_update(data)

            # Convert dictionary to JSON string
            resp_json = json.dumps(resp)
            await websocket.send(resp_json)

    except websockets.ConnectionClosed as e:
        print(f"Client disconnected: {e}")


async def start_websocket_server():
    # Start the WebSocket server on a separate port (e.g., 8765)
    async with websockets.serve(websocket_handler, "0.0.0.0", 8765):
        await asyncio.Future()  # Run forever


def start_servers():
    loop = asyncio.get_event_loop()

    # Start the Flask-SocketIO server on one port (e.g., 5000)
    flask_socketio_server = loop.run_in_executor(
        None,
        socketio.run,
        app,  # debug mode
        '0.0.0.0',  # host
        5000  # port
    )

    # Start the WebSocket server on a different port (e.g., 8765)
    websocket_server = start_websocket_server()

    # Run both servers concurrently
    loop.run_until_complete(asyncio.gather(flask_socketio_server, websocket_server))


if __name__ == '__main__':
    start_servers()