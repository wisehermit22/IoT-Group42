# Import necessary libraries
from flask import Flask, render_template, request, jsonify  # Flask web framework
from flask_socketio import SocketIO, emit  # For real-time bidirectional communication
from flask_sqlalchemy import SQLAlchemy  # ORM for database operations
import websockets  # For WebSocket communication with ESP32
import asyncio  # For asynchronous programming
import json  # For JSON parsing and encoding
from datetime import datetime, timedelta  # For date and time operations

# Initialize Flask app and configure it
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'  # Secret key for session management
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///drink_tracker.db'  # SQLite database file
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Disable modification tracking
db = SQLAlchemy(app)  # Initialize SQLAlchemy with the Flask app
socketio = SocketIO(app, cors_allowed_origins="*")  # Initialize SocketIO with CORS enabled

# Global variable to track if a reset is pending
reset_pending = False

# Define database models
class DeviceStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    added_count = db.Column(db.Integer, default=0)  # Total drinks added
    consumption_count = db.Column(db.Integer, default=0)  # Total drinks consumed
    inventory_count = db.Column(db.Integer, default=0)  # Current drink inventory
    lock_status = db.Column(db.Boolean, default=False)  # Is the device locked?
    lid_status = db.Column(db.Boolean, default=False)  # Is the lid closed?
    lockout_remaining = db.Column(db.Integer, default=0)  # Remaining lockout time in seconds
    consumption_limit = db.Column(db.Integer, default=2)  # Max drinks allowed per cycle
    lockout_timer = db.Column(db.Integer, default=30)  # Default lockout duration
    lockout_end_time = db.Column(db.DateTime, nullable=True)  # When the lockout ends
    cycle_start_time = db.Column(db.DateTime, nullable=True)  # Start of current cycle
    cycle_end_time = db.Column(db.DateTime, nullable=True)  # End of current cycle
    cycle_duration = db.Column(db.Integer, default=24*60)  # Cycle duration in minutes
    penalty_multiplier = db.Column(db.Float, default=1.5)  # Penalty for exceeding limit
    current_streak = db.Column(db.Integer, default=0)  # Current streak of cycles within limit
    highest_streak = db.Column(db.Integer, default=0)  # Highest achieved streak

class ConsumptionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # When the log was created
    count = db.Column(db.Integer)  # Number of drinks consumed in this cycle
    cycle_start = db.Column(db.DateTime)  # Start of the cycle for this log
    cycle_end = db.Column(db.DateTime)  # End of the cycle for this log
    limit_exceeded = db.Column(db.Boolean)  # Was the limit exceeded in this cycle?
    consumption_limit = db.Column(db.Integer)  # What was the limit for this cycle?

# Create database tables
with app.app_context():
    db.create_all()

# Function to get or create device status
def get_or_create_device_status():
    status = DeviceStatus.query.first()
    if not status:
        # If no status exists, create a new one with default values
        status = DeviceStatus()
        now = datetime.utcnow()
        status.cycle_start_time = now
        status.lockout_end_time = None
        db.session.add(status)
        db.session.commit()
        status = DeviceStatus.query.first()
        # Set the cycle end time based on the cycle duration
        status.cycle_end_time = status.cycle_start_time + timedelta(seconds=status.cycle_duration)
        db.session.commit()
    return status

# Route for the main page
@app.route('/')
def index():
    return render_template('index.html')

# SocketIO event handler for client connection
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status_update', get_device_status())

# SocketIO event handler for getting initial status
@socketio.on('get_initial_status')
def handle_get_initial_status():
    emit('status_update', get_device_status())

# SocketIO event handler for updating settings
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

# SocketIO event handler for resetting the device
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

# Function to handle status updates from ESP32
def handle_esp32_status_update(data):
    status = get_or_create_device_status()
    prev_consumption_count = status.consumption_count
    status.added_count = data['totalAddCount']
    status.consumption_count = data['totalRemCount']
    status.inventory_count = data['drinkCount']
    status.lock_status = data['lockState']
    status.lid_status = data['lidClosed']

    # Calculate remaining lockout time
    if status.lockout_remaining >= 1:
        now = datetime.utcnow()
        status.lockout_remaining = max(0, int((status.lockout_end_time - now).total_seconds()))
        if status.lockout_remaining == 0:
            status.lockout_end_time = None
    else:
        status.lockout_remaining = 0
        status.lockout_end_time = None

    status.last_updated = datetime.utcnow()
    
    # Log consumption if drinks were consumed
    if status.consumption_count > prev_consumption_count:
        consumption_difference = status.consumption_count - prev_consumption_count
        existing_log = ConsumptionLog.query.filter_by(cycle_start=status.cycle_start_time).first()
        
        if existing_log:
            existing_log.count += consumption_difference
            existing_log.limit_exceeded = (existing_log.count > status.consumption_limit)
            existing_log.consumption_limit = status.consumption_limit
        else:
            new_log = ConsumptionLog(
                count=consumption_difference,
                cycle_start=status.cycle_start_time,
                cycle_end=status.cycle_end_time,
                limit_exceeded=(status.consumption_count > status.consumption_limit),
                consumption_limit=status.consumption_limit
            )
            db.session.add(new_log)

    db.session.commit()
    socketio.emit('status_update', get_device_status())

    # Determine if the device should be locked
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

# Function to update streak
def update_streak(status, limit_exceeded):
    if limit_exceeded:
        status.current_streak = 0
    else:
        status.current_streak += 1
        if status.current_streak > status.highest_streak:
            status.highest_streak = status.current_streak
    db.session.commit()

# Function to check and reset cycle if needed
def check_and_reset_cycle():
    status = get_or_create_device_status()
    now = datetime.utcnow()
    if status.cycle_end_time <= now:
        limit_exceeded = status.consumption_count > status.consumption_limit
        update_streak(status, limit_exceeded)
        
        # Update the existing log for this cycle
        existing_log = ConsumptionLog.query.filter_by(cycle_start=status.cycle_start_time).first()
        if existing_log:
            existing_log.count = status.consumption_count
            existing_log.limit_exceeded = limit_exceeded
        else:
            # Create a new log if one doesn't exist (shouldn't happen)
            log = ConsumptionLog(
                count=status.consumption_count,
                cycle_start=status.cycle_start_time,
                cycle_end=status.cycle_end_time,
                limit_exceeded=limit_exceeded
            )
            db.session.add(log)
        
        # Reset cycle
        status.cycle_start_time = now
        status.cycle_end_time = status.cycle_start_time + timedelta(seconds=status.cycle_duration)
        status.consumption_count = 0
        status.added_count = 0
        status.lock_status = False
        status.lockout_end_time = None
        status.lockout_remaining = 0
        db.session.commit()

        global reset_pending
        reset_pending = True

# API route to get consumption history
@app.route('/api/consumption_history')
def consumption_history():
    logs = ConsumptionLog.query.order_by(ConsumptionLog.cycle_start.desc()).limit(30).all()
    status = get_or_create_device_status()
    history = [{
        'cycle_start': log.cycle_start.isoformat(),
        'cycle_end': log.cycle_end.isoformat(),
        'count': log.count,
        'limit_exceeded': log.limit_exceeded,
        'consumption_limit': log.consumption_limit
    } for log in logs]
    
    status = get_or_create_device_status()
    return jsonify({
        'history': history,
        'current_streak': status.current_streak,
        'highest_streak': status.highest_streak,
        'current_consumption_limit': status.consumption_limit
    })

# Function to get current device status
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
        'current_streak': status.current_streak,
        'highest_streak': status.highest_streak,
        'cycle_start_time': status.cycle_start_time.isoformat(),
        'cycle_end_time_iso': status.cycle_end_time.isoformat(),
    }

# WebSocket handler for ESP32 communication
async def websocket_handler(websocket, path):
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

# Function to start WebSocket server
async def start_websocket_server():
    # Start the WebSocket server on port 8765
    async with websockets.serve(websocket_handler, "0.0.0.0", 8765):
        await asyncio.Future()  # Run forever

# Function to start both Flask-SocketIO and WebSocket servers
def start_servers():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Start the Flask-SocketIO server on port 5000
    flask_socketio_server = loop.run_in_executor(
        None,
        socketio.run,
        app,  # Flask app
        '0.0.0.0',  # host
        5000  # port
    )

    # Start the WebSocket server
    websocket_server = start_websocket_server()

    # Run both servers concurrently
    loop.run_until_complete(asyncio.gather(flask_socketio_server, websocket_server))

# Main entry point
if __name__ == '__main__':
    start_servers()