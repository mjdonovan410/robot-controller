#!/usr/bin/env python3
"""
Remote Robot Lawn Mower Controller
Main Flask application for web server and motor control
"""

import os
import sys
import cv2
import numpy as np
from threading import Thread, Lock
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

# Global Controllers
camera = None
motor_controller = None
arduino_controller = None
control_lock = Lock()

# Motor state tracking
motor_state = {
    'rpm': 0,
    'acceleration': 0,
    'deceleration': 0,
    'motor_enabled': False,
    'blade_enabled': False,
    'direction': 'forward'  # forward, reverse, stop
}


def init_controllers():
    """Initialize all hardware controllers"""
    global camera, motor_controller, arduino_controller
    
    try:
        # Initialize camera (USB webcam, typically /dev/video0 on Raspberry Pi)
        logger.info("Initializing camera...")
        camera = CameraController(camera_index=0)
        if not camera.is_running():
            logger.warning("Camera failed to initialize, running without webcam")
            
    except Exception as e:
        logger.error(f"Camera initialization error: {e}")
        camera = None
    
    try:
        # Initialize motor controller (local logic)
        logger.info("Initializing motor controller...")
        motor_controller = MotorController()
        
    except Exception as e:
        logger.error(f"Motor controller initialization error: {e}")
        motor_controller = None
    
    try:
        # Initialize Arduino controller for serial communication
        # Configure ports: Motor 1 (/dev/ttyUSB0), Motor 2 (/dev/ttyUSB1)
        logger.info("Initializing Arduino controllers...")
        arduino_controller = ArduinoController(
            motor1_port='/dev/ttyUSB0',
            motor2_port='/dev/ttyUSB1',
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
    """Serve the video stream"""
    if camera is None:
        # Return a placeholder image if camera unavailable
        return "Camera not available", 503
    
    def generate_frames():
        while True:
            frame = camera.get_frame()
            if frame is not None:
                # Encode frame to JPEG
                ret, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n'
                       + frame_bytes + b'\r\n')
            else:
                # Send a blank frame if unavailable
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
    """Handle client connection"""
    logger.info(f"Client connected")
    emit('connection_response', {'data': 'Connected to Remote Robot Lawn Mower Controller'})
    # Send current motor state to newly connected client
    emit('motor_state_update', motor_state)


@socketio.on('disconnect')
def on_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected")
    # Optional: stop motors on disconnect
    update_motor_state(
        rpm=0,
        motor_enabled=False,
        blade_enabled=False
    )


@socketio.on('update_motor_control')
def on_motor_control(data):
    """Handle motor control updates from the client"""
    try:
        with control_lock:
            rpm = data.get('rpm', motor_state['rpm'])
            acceleration = data.get('acceleration', motor_state['acceleration'])
            deceleration = data.get('deceleration', motor_state['deceleration'])
            motor_enabled = data.get('motor_enabled', motor_state['motor_enabled'])
            blade_enabled = data.get('blade_enabled', motor_state['blade_enabled'])
            direction = data.get('direction', motor_state['direction'])
            
            # Update motor state
            update_motor_state(
                rpm=rpm,
                acceleration=acceleration,
                deceleration=deceleration,
                motor_enabled=motor_enabled,
                blade_enabled=blade_enabled,
                direction=direction
            )
            
            # Send motor command to Arduinos
            if arduino_controller and motor_enabled:
                arduino_controller.send_motor_command(
                    motor_id=1,
                    rpm=rpm,
                    direction=direction,
                    contactor_enabled=blade_enabled,
                    acceleration=acceleration,
                    deceleration=deceleration
                )
                arduino_controller.send_motor_command(
                    motor_id=2,
                    rpm=rpm,
                    direction=direction,
                    contactor_enabled=blade_enabled,
                    acceleration=acceleration,
                    deceleration=deceleration
                )
            elif not motor_enabled:
                # Stop motors when disabled
                if arduino_controller:
                    arduino_controller.send_motor_command(
                        motor_id=1,
                        rpm=0,
                        direction='stop',
                        contactor_enabled=False
                    )
                    arduino_controller.send_motor_command(
                        motor_id=2,
                        rpm=0,
                        direction='stop',
                        contactor_enabled=False
                    )
            
            # Broadcast updated state to all connected clients
            emit('motor_state_update', motor_state, broadcast=True)
            
            logger.info(f"Motor control updated: RPM={rpm}, Accel={acceleration}, "
                       f"Decel={deceleration}, Motor={motor_enabled}, Blade={blade_enabled}")
            
    except Exception as e:
        logger.error(f"Error processing motor control: {e}")
        emit('error', {'message': str(e)})


@socketio.on('test_command')
def on_test_command(data):
    """Handle test commands (useful for debugging)"""
    command = data.get('command', '')
    logger.info(f"Test command received: {command}")
    
    if command == 'ping':
        emit('test_response', {'status': 'pong', 'timestamp': datetime.now().isoformat()})
    elif command == 'get_motor_state':
        emit('test_response', {'status': 'motor_state', 'data': motor_state})
    else:
        emit('test_response', {'status': 'unknown_command'})


def update_motor_state(**kwargs):
    """Update the global motor state"""
    global motor_state
    for key, value in kwargs.items():
        if key in motor_state:
            motor_state[key] = value
    logger.debug(f"Motor state updated: {motor_state}")


if __name__ == '__main__':
    logger.info("Initializing Remote Robot Lawn Mower Controller...")
    init_controllers()
    
    logger.info("Starting Flask-SocketIO server...")
    # In production, use a proper WSGI server (e.g., gunicorn)
    # For development/RPi: socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=False,
        allow_unsafe_werkzeug=True
    )
