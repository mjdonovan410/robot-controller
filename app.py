#!/usr/bin/env python3
"""
Remote Robot Lawn Mower Controller

This module hosts the web UI, streams camera frames, accepts live control
updates from the browser, forwards wheel commands to the Arduino controllers,
and republishes state/log information back to connected clients.
"""

import cv2
import numpy as np
from collections import deque
from threading import Lock
from flask import Flask, render_template, Response
from flask_socketio import SocketIO, emit
from datetime import datetime
import logging

from modules.arduino_controller import ArduinoController
from modules.camera_controller import CameraController
from modules.motor_controller import MotorController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask App Configuration
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
socketio = SocketIO(app, cors_allowed_origins="*")

# Hardware and shared runtime state. These are created once during process
# startup and then reused by request handlers and Socket.IO events.
camera = None
motor_controller = None
arduino_controller = None
control_lock = Lock()
arduino_state_lock = Lock()
arduino_command_log = deque(maxlen=200)

# The browser uses this structure to render the Arduino communication card.
# It intentionally stores timestamps and last-error text rather than raw serial
# objects so the UI can be updated safely from background tasks.
arduino_status = {
    'connected': False,
    'motor1_connected': False,
    'motor2_connected': False,
    'communication_ok': False,
    'last_tx': None,
    'last_rx': None,
    'last_error': None
}

# Browser-facing motor state. This remains the single source of truth for the
# current UI snapshot and is broadcast after every accepted control update.
motor_state = {
    'rpm': 0,
    'acceleration': 50,
    'deceleration': 50,
    'motor_enabled': True,
    'blade_enabled': False,
    'direction': 'stop',  # forward, reverse, stop, mixed
    'speed_percent': 0,
    'control_mode': 'manual',
    'left_wheel': {
        'motor_id': 1,
        'rpm': 0,
        'direction': 'stop'
    },
    'right_wheel': {
        'motor_id': 2,
        'rpm': 0,
        'direction': 'stop'
    }
}


def _clamp(value, min_value, max_value):
    """Clamp a numeric value to a safe range."""
    return max(min_value, min(max_value, value))


def _sanitize_wheel_command(raw_command):
    """Normalize a single wheel command from the browser payload.

    The UI can send independent left/right wheel commands. This helper clamps
    RPM values and coerces unsupported directions to a safe stop command before
    the command is mirrored into the shared motor state or sent to hardware.
    """
    motor_id = int(raw_command.get('motor_id', 1))
    rpm = int(_clamp(raw_command.get('rpm', 0), 0, 10500))
    direction = raw_command.get('direction', 'stop')
    if direction not in ['forward', 'reverse', 'stop']:
        direction = 'stop'

    return {
        'motor_id': motor_id,
        'rpm': rpm,
        'direction': direction
    }


def _invert_direction_for_arduino(direction):
    """Swap forward/reverse to match corrected motor polarity wiring."""
    if direction == 'forward':
        return 'reverse'
    if direction == 'reverse':
        return 'forward'
    return 'stop'


def _iso_now():
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat()


def _append_arduino_log(entry):
    """Append an Arduino log entry and broadcast it to connected clients."""
    full_entry = {
        'timestamp': _iso_now(),
        **entry
    }
    with arduino_state_lock:
        arduino_command_log.append(full_entry)
    socketio.emit('arduino_command_log', full_entry)


def _build_arduino_status_snapshot():
    """Build the latest Arduino status payload expected by the frontend.

    Serial connectivity and communication health are derived here instead of
    being stored redundantly elsewhere so the UI always receives a consistent,
    freshly computed snapshot.
    """
    with arduino_state_lock:
        snapshot = dict(arduino_status)

    if arduino_controller:
        motor1_connected = bool(arduino_controller.ser1 and arduino_controller.ser1.is_open)
        motor2_connected = bool(arduino_controller.ser2 and arduino_controller.ser2.is_open)
        snapshot['motor1_connected'] = motor1_connected
        snapshot['motor2_connected'] = motor2_connected
        snapshot['connected'] = motor1_connected and motor2_connected
    else:
        snapshot['motor1_connected'] = False
        snapshot['motor2_connected'] = False
        snapshot['connected'] = False

    # Communication is considered healthy only when both serial links are open
    # and the application has observed a recent response from either Arduino.
    if snapshot['last_rx'] and snapshot['connected']:
        try:
            age_seconds = (datetime.now() - datetime.fromisoformat(snapshot['last_rx'])).total_seconds()
            snapshot['communication_ok'] = age_seconds <= 5
        except Exception:
            snapshot['communication_ok'] = False
    else:
        snapshot['communication_ok'] = False

    return snapshot


def _publish_arduino_status():
    """Publish Arduino status to all clients."""
    socketio.emit('arduino_status_update', _build_arduino_status_snapshot())


def _set_arduino_status(**kwargs):
    """Update internal Arduino status fields."""
    with arduino_state_lock:
        for key, value in kwargs.items():
            if key in arduino_status:
                arduino_status[key] = value


def _mark_arduino_tx_success():
    """Record successful command transmit activity."""
    _set_arduino_status(last_tx=_iso_now(), last_error=None)


def _mark_arduino_rx():
    """Record successful response receive activity."""
    _set_arduino_status(last_rx=_iso_now(), last_error=None)


def _arduino_monitor_task():
    """Background task that harvests serial responses and updates UI state.

    Flask-SocketIO runs this as a cooperative background job. Each loop polls
    both Arduino ports, records any received messages in the rolling log, and
    republishes the connection/comms snapshot for the browser dashboard.
    """
    while True:
        try:
            if arduino_controller:
                for motor_id in [1, 2]:
                    response = arduino_controller.read_arduino_response(motor_id)
                    if response:
                        _mark_arduino_rx()
                        _append_arduino_log({
                            'type': 'rx',
                            'motor_id': motor_id,
                            'message': response
                        })

            _publish_arduino_status()
        except Exception as e:
            _set_arduino_status(last_error=str(e))
            _append_arduino_log({
                'type': 'error',
                'message': f'Arduino monitor error: {e}'
            })
            _publish_arduino_status()

        socketio.sleep(0.25)


def init_controllers():
    """Initialize camera, logical motor state, and Arduino serial bridges."""
    global camera, motor_controller, arduino_controller
    
    try:
        # The camera is optional. If it fails, the rest of the control stack
        # should still run so the mower can be driven without video.
        logger.info("Initializing camera...")
        camera = CameraController(camera_index=0)
        if not camera.is_running():
            logger.warning("Camera failed to initialize, running without webcam")
            
    except Exception as e:
        logger.error(f"Camera initialization error: {e}")
        camera = None
    
    try:
        # This controller currently provides validation/state helpers and keeps
        # the application structure ready for more advanced local logic later.
        logger.info("Initializing motor controller...")
        motor_controller = MotorController()
        
    except Exception as e:
        logger.error(f"Motor controller initialization error: {e}")
        motor_controller = None
    
    try:
        # Each wheel has its own Arduino-controlled driver path, so two serial
        # ports are opened and managed together by the ArduinoController.
        logger.info("Initializing Arduino controllers...")
        arduino_controller = ArduinoController(
            motor1_port='/dev/ttyUSB1',
            motor2_port='/dev/ttyUSB0',
            baud_rate=115200
        )
        
    except Exception as e:
        logger.error(f"Arduino controller initialization error: {e}")
        logger.info("Running in simulation mode - no Arduino communication")
        arduino_controller = None


@app.route('/')
def index():
    """Serve the main control page"""
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    """Stream MJPEG frames to the browser video element.

    The browser keeps an <img> tag pointed at this route. The generator yields
    a multipart MJPEG stream so clients can render live video without a custom
    WebRTC/WebSocket video transport.
    """
    if camera is None:
        return "Camera not available", 503
    
    def generate_frames():
        """Yield the continuous MJPEG frame stream consumed by the UI."""
        while True:
            frame = camera.get_frame()
            if frame is not None:
                ret, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n'
                       + frame_bytes + b'\r\n')
            else:
                # Keep the HTTP stream alive even when no fresh camera frame is
                # available so the browser does not have to reconnect.
                blank = np.zeros((480, 640, 3), dtype=np.uint8)
                ret, buffer = cv2.imencode('.jpg', blank)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n'
                       + frame_bytes + b'\r\n')
    
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@socketio.on('connect')
def on_connect():
    """Handle a new browser session connecting over Socket.IO."""
    logger.info(f"Client connected")
    emit('connection_response', {'data': 'Connected to Remote Robot Lawn Mower Controller'})
    # Send the complete current state immediately so a refreshed browser can
    # rebuild the dashboard without waiting for the next control event.
    emit('motor_state_update', motor_state)
    emit('arduino_status_update', _build_arduino_status_snapshot())
    emit('arduino_command_history', {'entries': list(arduino_command_log)})


@socketio.on('disconnect')
def on_disconnect():
    """Handle browser disconnects by issuing a full safety stop."""
    logger.info(f"Client disconnected")
    update_motor_state(
        rpm=0,
        motor_enabled=False,
        blade_enabled=False,
        speed_percent=0,
        control_mode='disconnected',
        direction='stop',
        left_wheel={'motor_id': 1, 'rpm': 0, 'direction': 'stop'},
        right_wheel={'motor_id': 2, 'rpm': 0, 'direction': 'stop'}
    )

    if arduino_controller:
        for mid in [1, 2]:
            arduino_controller.send_motor_command(
                motor_id=mid,
                rpm=0,
                direction='stop',
                contactor_enabled=False,
                acceleration=0,
                deceleration=100
            )
            _mark_arduino_tx_success()
            _append_arduino_log({
                'type': 'tx',
                'motor_id': mid,
                'rpm': 0,
                'direction': 'stop',
                'contactor': False,
                'acceleration': 0,
                'deceleration': 100,
                'source': 'disconnect_safety_stop'
            })

    _publish_arduino_status()


@socketio.on('update_motor_control')
def on_motor_control(data):
    """Apply a browser control update and forward it to the hardware layer.

    The handler accepts either a legacy single-command payload or explicit
    per-wheel commands. Every incoming command path is normalized into two wheel
    commands before state is updated and serial output is attempted.
    """
    try:
        with control_lock:
            rpm = data.get('rpm', motor_state['rpm'])
            acceleration = int(_clamp(data.get('acceleration', motor_state['acceleration']), 0, 100))
            deceleration = int(_clamp(data.get('deceleration', motor_state['deceleration']), 0, 100))
            motor_enabled = data.get('motor_enabled', motor_state['motor_enabled'])
            blade_enabled = data.get('blade_enabled', motor_state['blade_enabled'])
            direction = data.get('direction', motor_state['direction'])
            speed_percent = int(_clamp(data.get('speed_percent', 0), 0, 100))
            control_mode = data.get('control_mode', motor_state['control_mode'])

            incoming_motor_commands = data.get('motor_commands')
            if incoming_motor_commands:
                motor_commands = {}
                for cmd in incoming_motor_commands:
                    safe_cmd = _sanitize_wheel_command(cmd)
                    if safe_cmd['motor_id'] in [1, 2]:
                        motor_commands[safe_cmd['motor_id']] = safe_cmd

                # Every downstream path expects both wheel entries to exist,
                # even if the browser only sent one side.
                for mid in [1, 2]:
                    if mid not in motor_commands:
                        motor_commands[mid] = {
                            'motor_id': mid,
                            'rpm': 0,
                            'direction': 'stop'
                        }
            else:
                # Older manual UI paths still emit a single RPM/direction pair.
                # Mirror that command to both wheels to preserve compatibility.
                safe_rpm = int(_clamp(rpm, 0, 10500))
                safe_direction = direction if direction in ['forward', 'reverse', 'stop'] else 'stop'
                motor_commands = {
                    1: {'motor_id': 1, 'rpm': safe_rpm, 'direction': safe_direction},
                    2: {'motor_id': 2, 'rpm': safe_rpm, 'direction': safe_direction}
                }

            if not motor_enabled:
                # Motor disable overrides every other browser input. This keeps
                # the enable toggle as a hard software interlock.
                blade_enabled = False
                speed_percent = 0
                for mid in [1, 2]:
                    motor_commands[mid]['rpm'] = 0
                    motor_commands[mid]['direction'] = 'stop'

            # The top-level RPM and direction fields are retained for the UI and
            # for older code paths that still read aggregate state instead of
            # individual wheel values.
            rpm = max(motor_commands[1]['rpm'], motor_commands[2]['rpm'])
            if motor_commands[1]['direction'] == motor_commands[2]['direction']:
                direction = motor_commands[1]['direction']
            else:
                direction = 'mixed'
            
            update_motor_state(
                rpm=rpm,
                acceleration=acceleration,
                deceleration=deceleration,
                motor_enabled=motor_enabled,
                blade_enabled=blade_enabled,
                direction=direction,
                speed_percent=speed_percent,
                control_mode=control_mode,
                left_wheel=motor_commands[1],
                right_wheel=motor_commands[2]
            )
            
            # Serial output is emitted per wheel so each Arduino receives only
            # the command relevant to its own motor driver.
            if arduino_controller:
                for mid in [1, 2]:
                    wheel = motor_commands[mid]
                    arduino_direction = _invert_direction_for_arduino(wheel['direction'])
                    arduino_controller.send_motor_command(
                        motor_id=mid,
                        rpm=wheel['rpm'],
                        direction=arduino_direction,
                        contactor_enabled=blade_enabled,
                        acceleration=acceleration,
                        deceleration=deceleration
                    )
                    _mark_arduino_tx_success()
                    _append_arduino_log({
                        'type': 'tx',
                        'motor_id': mid,
                        'rpm': wheel['rpm'],
                        'direction': arduino_direction,
                        'requested_direction': wheel['direction'],
                        'contactor': blade_enabled,
                        'acceleration': acceleration,
                        'deceleration': deceleration,
                        'source': control_mode
                    })
            else:
                _set_arduino_status(last_error='Arduino controller unavailable (simulation mode)')
            
            # Broadcast the accepted state so multiple browser sessions remain
            # in sync even when only one of them is actively issuing commands.
            emit('motor_state_update', motor_state, broadcast=True)
            _publish_arduino_status()
            
            logger.info(
                "Motor control updated: mode=%s speed=%s%% m1=%s/%s m2=%s/%s motor=%s blade=%s",
                control_mode,
                speed_percent,
                motor_commands[1]['direction'],
                motor_commands[1]['rpm'],
                motor_commands[2]['direction'],
                motor_commands[2]['rpm'],
                motor_enabled,
                blade_enabled
            )
            
    except Exception as e:
        logger.error(f"Error processing motor control: {e}")
        emit('error', {'message': str(e)})


@socketio.on('test_command')
def on_test_command(data):
    """Handle lightweight debug commands from the browser."""
    command = data.get('command', '')
    logger.info(f"Test command received: {command}")
    
    if command == 'ping':
        emit('test_response', {'status': 'pong', 'timestamp': datetime.now().isoformat()})
    elif command == 'get_motor_state':
        emit('test_response', {'status': 'motor_state', 'data': motor_state})
    else:
        emit('test_response', {'status': 'unknown_command'})


def update_motor_state(**kwargs):
    """Update keys on the shared browser-facing motor state dictionary."""
    global motor_state
    for key, value in kwargs.items():
        if key in motor_state:
            motor_state[key] = value
    logger.debug(f"Motor state updated: {motor_state}")


if __name__ == '__main__':
    logger.info("Initializing Remote Robot Lawn Mower Controller...")
    init_controllers()
    socketio.start_background_task(_arduino_monitor_task)
    
    logger.info("Starting Flask-SocketIO server...")
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=False
    )
