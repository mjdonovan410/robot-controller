# Quick Setup Guide for Raspberry Pi

## Prerequisites
- Raspberry Pi 4 or later (4GB RAM minimum recommended)
- Raspberry Pi OS (Bullseye or later)
- USB Webcam connected to RPi
- 2x Arduino boards with motor shield connected via USB
- Internet connection for initial setup

## Step 1: Update System

```bash
sudo apt update
sudo apt upgrade -y
```

## Step 2: Install Python and Dependencies

```bash
sudo apt install -y python3-pip python3-venv python3-dev
sudo apt install -y libatlas-base-dev libjasper-dev libtiff5 libjasper-dev zinc libharfbuzz0b libwebp6
sudo apt install -y build-essential git
```

## Step 3: Clone/Download Project

```bash
cd ~
git clone <your-repo-url> RemoteRobot
# OR download and extract the ZIP file
cd RemoteRobot
```

## Step 4: Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

## Step 5: Install Python Packages

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This will install:
- Flask (Web framework)
- Flask-SocketIO (Real-time communication)
- OpenCV (Camera handling)
- PySerial (Arduino communication)

## Step 6: Configure Serial Ports

### Find Your Arduino Ports

```bash
ls /dev/ttyUSB*
```

You should see something like:
- `/dev/ttyUSB0` (Motor 1)
- `/dev/ttyUSB1` (Motor 2)

### Verify Camera

```bash
ls /dev/video*
```

You should see at least `/dev/video0`

### Update `app.py` if needed

If your ports are different, edit the ArduinoController initialization in `app.py`:

```python
arduino_controller = ArduinoController(
    motor1_port='/dev/ttyUSB0',  # Change if different
    motor2_port='/dev/ttyUSB1',  # Change if different
    baud_rate=115200
)
```

## Step 7: Upload Arduino Sketches

1. Connect each Arduino to your computer via USB
2. Open Arduino IDE
3. Load `arduino_sketches/motor_controller.ino`
4. Select correct Board and Port
5. Click Upload
6. Repeat for second Arduino

## Step 8: Test the System

### Start the Server (Development Mode)

```bash
python3 app.py
```

You should see:
```
Initializing Remote Robot Lawn Mower Controller...
Initializing camera...
Initializing motor controller...
Initializing Arduino controllers...
Starting Flask-SocketIO server...
 * Running on http://0.0.0.0:5000
```

### Access the Web Interface

On another device on your network:
```
http://<your-pi-ip>:5000
```

Find your Pi's IP:
```bash
hostname -I
```

## Step 9: Test Controls

1. Open the web interface
2. You should see the live camera feed
3. Test the motor control sliders (start with low values)
4. Toggle Motor Enable
5. Test direction buttons
6. Monitor Arduino responses in terminal

## Step 10: Run Automatically on Startup (Optional)

### Option A: Using systemd (Recommended)

```bash
sudo cp remoterobot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable remoterobot.service
sudo systemctl start remoterobot.service
```

Check status:
```bash
sudo systemctl status remoterobot.service
```

View logs:
```bash
journalctl -u remoterobot.service -f
```

### Option B: Using Cron

```bash
crontab -e
```

Add this line:
```
@reboot /home/pi/RemoteRobot/start.sh
```

## Troubleshooting

### Camera Not Showing

```bash
# Test camera
python3 << 'EOF'
import cv2
cap = cv2.VideoCapture(0)
if cap.isOpened():
    ret, frame = cap.read()
    print(f"Camera OK: {frame.shape}")
else:
    print("Camera FAILED")
cap.release()
EOF

# Check permissions
sudo usermod -a -G video pi

# Test with v4l2 tools
sudo apt install v4l-utils
v4l2-ctl --list-devices
```

### Arduino Not Communicating

```bash
# Test serial port
# Install minicom: sudo apt install minicom
# Connect to Arduino:
minicom -D /dev/ttyUSB0 -b 115200

# Send test command:
{"rpm":100,"dir":"forward","contactor":false,"accel":50,"decel":50}

# Exit: Ctrl+A then X
```

### Port Already in Use

```bash
# Find what's using port 5000
sudo lsof -i :5000

# Kill the process
sudo kill <PID>
```

### Connection Refused

Check firewall:
```bash
sudo ufw status
sudo ufw allow 5000/tcp  # If needed
```

### High CPU Usage

- Reduce camera FPS in `config.py`
- Use faster SD card
- Set CPU governor to performance

```bash
echo performance | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
```

## Performance Optimization

### For Better Performance

1. Use a fast SD card (UHS recommended)
2. Enable hardware camera if available (Pi Camera)
3. Reduce video resolution if needed
4. Use Gunicorn for production:

```bash
pip install gunicorn
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:5000 app:app
```

## Network Access from Outside

To access remotely, consider:
- Using a VPN
- Port forwarding (with caution)
- SSH tunneling

SSH tunnel example:
```bash
ssh -L 5000:localhost:5000 pi@<pi-ip>
```

Then access at: `http://localhost:5000`

## Safety Reminders

⚠️ **IMPORTANT:**
- Always test motor commands at LOW RPM first
- Keep hands away from spinning blades
- Implement emergency stop button on Arduino side
- Use proper electrical safety practices
- Never leave running mower unattended

## Support

For issues or questions:
1. Check README.md for detailed documentation
2. Review logs in `/var/log/remote-robot/` (if configured)
3. Test components individually
4. Consult Arduino and Raspberry Pi forums

Happy mowing! 🤖
