"""Centralized configuration values for the robot controller application.

These constants define the runtime defaults and safety limits shared by the web
server, browser UI expectations, and the hardware control layer.
"""

# Flask Configuration
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5000
FLASK_DEBUG = False
SECRET_KEY = 'change-this-in-production-to-a-random-string'

# Camera Configuration
CAMERA_INDEX = 0  # /dev/video0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30
CAMERA_ENABLED = True

# Motor Configuration
MAX_RPM = 10500
MIN_RPM = 0
MAX_ACCELERATION = 100
MAX_DECELERATION = 100
DEFAULT_ACCELERATION = 50
DEFAULT_DECELERATION = 50

# Arduino Serial Configuration
MOTOR1_SERIAL_PORT = '/dev/ttyUSB0'
MOTOR2_SERIAL_PORT = '/dev/ttyUSB1'
ARDUINO_BAUD_RATE = 115200
ARDUINO_TIMEOUT = 1  # seconds
ARDUINO_ENABLED = True

# Logging Configuration
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# WebSocket Configuration
SOCKETIO_CORS_ALLOWED_ORIGINS = '*'
SOCKETIO_ASYNC_MODE = 'threading'

# Safety Configuration
MOTOR_ENABLE_REQUIRED_FOR_RPM = True
AUTO_DISABLE_ON_CONNECTION_LOSS = True
CONNECTION_LOSS_TIMEOUT = 5  # seconds

# Motor Control Limits
MIN_RPM_FOR_MOVEMENT = 100  # Ignore tiny commands below this when needed.
RPM_RAMP_RATE = 50  # Reserved for higher-level software ramping if added later.
