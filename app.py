from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO, emit
from datetime import datetime, timedelta
import os

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'iot_device.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)
socketio = SocketIO(app, cors_allowed_origins="*")

class DeviceSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    consumption_limit = db.Column(db.Integer, default=10)
    lockout_timer = db.Column(db.Integer, default=30)
    inventory_count = db.Column(db.Integer, default=10)
    lock_status = db.Column(db.Boolean, default=False)
    consumption_count = db.Column(db.Integer, default=0)
    lockout_end_time = db.Column(db.DateTime, nullable=True)

def create_default_settings():
    if not DeviceSettings.query.first():
        default_settings = DeviceSettings()
        db.session.add(default_settings)
        db.session.commit()

@app.cli.command("init-db")
def init_db():
    """Initialize the database."""
    db.create_all()
    create_default_settings()
    print('Initialized the database.')

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print("Client connected")
    emit_status_update()

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

@socketio.on('get_initial_status')
def handle_get_initial_status():
    emit_status_update()

@socketio.on('update_settings')
def handle_update_settings(data):
    if data.get('confirmation_phrase') == "I am not lying":
        settings = DeviceSettings.query.first()
        settings.consumption_limit = int(data.get('consumption_limit', settings.consumption_limit))
        settings.lockout_timer = int(data.get('lockout_timer', settings.lockout_timer))
        settings.inventory_count = int(data.get('inventory_count', settings.inventory_count))
        db.session.commit()
        emit_status_update()
        return {'status': 'success'}
    return {'status': 'failed', 'message': 'Confirmation phrase is incorrect.'}

@socketio.on('reset_device')
def handle_reset_device(data):
    if data.get('confirmation_phrase') == "I am not lying":
        settings = DeviceSettings.query.first()
        settings.consumption_count = 0
        settings.lock_status = False
        settings.lockout_end_time = None
        db.session.commit()
        emit_status_update()
        return {'status': 'success', 'message': 'Device reset successfully'}
    return {'status': 'failed', 'message': 'Incorrect confirmation phrase'}

@socketio.on('esp32_data')
def handle_esp32_data(data):
    print(f"Received ESP32 data: {data}")
    if 'switch_state' in data:
        handle_switch_event(data['switch_state'])
    
    # Emit ESP32 update to all clients
    socketio.emit('esp32_update', data)

def handle_switch_event(switch_state):
    settings = DeviceSettings.query.first()
    
    if switch_state:  # Can removed (switch pressed)
        if settings.inventory_count > 0:
            settings.consumption_count += 1
            settings.inventory_count -= 1

            if settings.consumption_count >= settings.consumption_limit:
                settings.lock_status = True
                settings.lockout_end_time = datetime.utcnow() + timedelta(minutes=settings.lockout_timer)
    else:  # Can added (switch released)
        settings.inventory_count += 1

    db.session.commit()
    emit_status_update()
    emit_lock_status()

def emit_status_update():
    settings = DeviceSettings.query.first()
    if settings:
        socketio.emit('status_update', {
            'consumption_count': settings.consumption_count,
            'inventory_count': settings.inventory_count,
            'lock_status': settings.lock_status,
            'lockout_remaining': get_lockout_remaining(settings)
        })
    else:
        print("Error: No DeviceSettings found")

def emit_lock_status():
    settings = DeviceSettings.query.first()
    if settings:
        socketio.emit('lock_status', {'locked': settings.lock_status})
    else:
        print("Error: No DeviceSettings found")

def get_lockout_remaining(settings):
    if settings.lockout_end_time and settings.lockout_end_time > datetime.utcnow():
        return int((settings.lockout_end_time - datetime.utcnow()).total_seconds())
    return 0

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_default_settings()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)