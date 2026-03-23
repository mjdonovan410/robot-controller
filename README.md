# 🤖 Remote Robot Lawn Mower Controller

A comprehensive web-based control system for a Raspberry Pi-powered lawn mower with remote Arduino motor controllers and live webcam feed.

## Project Overview

This system allows you to:
- 📹 View a live USB webcam feed from your Raspberry Pi
- 🎮 Control two motors with precise RPM, acceleration, and deceleration settings
- ⚙️ Toggle motor enable/disable and mower blade activation
- 📱 Manage controls from any connected device via web browser
- 🔌 Communicate with Arduino boards via USB serial connections

## Features

### Web Server
- **Flask-based** web server optimized for Raspberry Pi
- **Real-time communication** using WebSocket (Socket.IO)
- **Live video streaming** from USB webcam via MJPEG
- **Responsive design** that works on mobile and desktop

### Control Frontend
- **Motor Enable/Disable Toggle**
- **Mower Blade Manual Run Toggle**
- **RPM Slider**: 0-3000 RPM control
- **Acceleration Slider**: 0-100% control
- **Deceleration Slider**: 0-100% control
- **Direction Buttons**: Forward, Stop, Reverse
- **Live Status Display**: Real-time monitoring of all parameters
- **Connection Status Indicator**

### Backend Architecture
- **CameraController**: Manages USB webcam streaming with OpenCV
- **MotorController**: Handles motor state management and validation
- **ArduinoController**: Serial communication with two Arduino boards

## Hardware Requirements

- **Raspberry Pi** (4 or higher recommended)
- **USB Webcam** (connected to RPi USB port)
- **2x Arduino Boards** (e.g., Arduino Uno) with motor driver shields
- **USB to Serial Cables** (for Arduino connections)
- **Power Supply** for RPi and motor controllers

## Software Requirements

- **Python 3.8+**
- **Raspberry Pi OS** (Debian-based)

## Installation

### 1. Clone or Setup the Project

```bash
cd /path/to/RemoteRobot
```

### 2. Create Python Virtual Environment (Recommended)

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Serial Ports

Update the serial port configurations in `app.py` (ArduinoController initialization):
- Motor 1: Default `/dev/ttyUSB0`
- Motor 2: Default `/dev/ttyUSB1`

On Raspberry Pi, you can find connected devices using:
```bash
ls /dev/ttyUSB*
```

### 5. Set Camera Index

If you have multiple cameras or your camera is at a different index, update `app.py`:
```python
camera = CameraController(camera_index=0)  # Change 0 to appropriate index
```

To find your camera:
```bash
ls /dev/video*
```

## Running the Server

### Development Mode (Raspberry Pi)

```bash
python3 app.py
```

The server will start on `http://0.0.0.0:5000`

### On Your Network

Access from another device:
```
http://<raspberry_pi_ip>:5000
```

To find your Raspberry Pi's IP:
```bash
hostname -I
```

### Production Mode (Using Gunicorn)

```bash
pip install gunicorn
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:5000 app:app
```

## Arduino Communication Protocol

The Raspberry Pi sends motor commands to Arduino boards as JSON strings over serial (115200 baud):

### Command Format
```json
{
  "rpm": 1500,
  "dir": "forward",
  "contactor": true,
  "accel": 50,
  "decel": 50
}
```

### Parameters
- **rpm**: Motor speed (0-3000)
- **dir**: Direction ("forward", "reverse", or "stop")
- **contactor**: Blade contactor enable (true/false)
- **accel**: Acceleration (0-100)
- **decel**: Deceleration (0-100)

### Arduino Sketch Example
```c
void setup() {
  Serial.begin(115200);
  // Initialize motor pins, PWM, etc.
}

void loop() {
  if (Serial.available() > 0) {
    String jsonString = Serial.readStringUntil('\n');
    // Parse JSON and control motors
    // Send response back if needed
  }
}
```

## Project Structure

```
RemoteRobot/
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── modules/
│   ├── __init__.py
│   ├── camera_controller.py   # USB camera management
│   ├── motor_controller.py    # Motor state & validation
│   └── arduino_controller.py  # Serial communication
├── templates/
│   └── index.html             # Web interface
├── static/
│   ├── style.css              # UI styling
│   └── script.js              # Frontend logic
└── config/
    └── config.py              # Configuration settings
```

## Keyboard Shortcuts (Optional)

When web interface is focused:
- **SPACE**: Toggle motor enable/disable
- **Arrow Up**: Forward
- **Arrow Down**: Reverse
- **Arrow Left/Right**: Stop

## Xbox Controller Support

Xbox controller support is available but commented out by default. To enable:

1. Connect your Xbox controller to your device
2. Uncomment the gamepad code in `static/script.js`
3. Customize button mappings as needed:
   - **A Button**: Motor Enable
   - **B Button**: Motor Disable
   - **X Button**: Blade Toggle
   - **D-Pad**: Direction Control
   - **Right Analog Stick**: RPM Control

## Troubleshooting

### Camera Not Working
- Verify webcam is connected: `lsusb | grep -i camera`
- Check permissions: `sudo usermod -a -G video pi`
- Test camera: `python3 -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened())"`

### Arduino Not Communicating
- Check USB connections: `ls /dev/ttyUSB*`
- Verify baud rate matches Arduino sketch (115200)
- Test with minicom: `minicom -D /dev/ttyUSB0 -b 115200`
- Check Arduino sketch is uploaded and working

### WebSocket Connection Issues
- Ensure firewalls allow port 5000
- Check Flask-SocketIO is properly installed
- Verify CORS settings in `app.py`

### Performance Issues on Raspberry Pi
- Reduce video frame rate in `CameraController.__init__()`
- Use CPU governor: `echo performance | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor`
- Consider using a faster SD card

## Safety Considerations

⚠️ **Important Safety Notes:**
- Always test motor commands at low RPM first
- Implement emergency stop logic on Arduino side
- Disable motors when connection is lost
- Keep hands away from moving blades
- Use proper electrical safety practices
- Consider adding a hardware emergency stop button

## Future Enhancements

- [ ] GPS-based mowing pattern planning
- [ ] Multiple user support with permission levels
- [ ] Data logging and telemetry
- [ ] Advanced motion control (PID tuning)
- [ ] Weather API integration (pause on rain)
- [ ] Mobile app (React Native or Flutter)
- [ ] Cloud-based control and monitoring
- [ ] Machine learning for obstacle detection

## API Documentation

### WebSocket Events

#### Client → Server
- `update_motor_control`: Send motor control parameters
- `test_command`: Send debug commands

#### Server → Client
- `connection_response`: Confirmation of connection
- `motor_state_update`: Current motor state broadcast
- `error`: Error message from server

## License

[Add your license here]

## Support

For issues, questions, or contributions, please refer to the project repository or documentation.

---

**Built with ❤️ for remote-controlled lawn mowing automation**
