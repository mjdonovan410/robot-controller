#!/bin/bash

# Remote Robot Lawn Mower Controller - Startup Script
# Run this script to start the web server on your Raspberry Pi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Remote Robot Lawn Mower Controller${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
    
    # Activate and upgrade pip
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip
    
    # Install requirements
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -r "$PROJECT_DIR/requirements.txt"
    echo -e "${GREEN}Dependencies installed${NC}"
else
    echo -e "${GREEN}Virtual environment found${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source "$VENV_DIR/bin/activate"

# Check if all modules can be imported
echo -e "${YELLOW}Checking dependencies...${NC}"
python3 << EOF
import sys
try:
    import flask
    import flask_socketio
    import cv2
    import serial
    print("✓ All dependencies found")
except ImportError as e:
    print(f"✗ Missing dependency: {e}")
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    echo -e "${RED}Dependency check failed${NC}"
    exit 1
fi

# Get Raspberry Pi IP address
PI_IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${GREEN}Configuration:${NC}"
echo "  Project Directory: $PROJECT_DIR"
echo "  Python Version: $(python3 --version)"
echo "  Raspberry Pi IP: $PI_IP"
echo ""

# Check for camera
echo -e "${YELLOW}Checking for camera...${NC}"
if python3 << EOF
import cv2
cap = cv2.VideoCapture(0)
if cap.isOpened():
    print("✓ Camera found")
    cap.release()
    exit(0)
else:
    print("✗ Camera not found at /dev/video0")
    exit(1)
EOF
then
    :
else
    echo -e "${YELLOW}WARNING: Camera not detected. Check USB connection.${NC}"
    echo "         Enter 'ls /dev/video*' to find your camera"
    echo ""
fi

# Check for Arduino connections
echo -e "${YELLOW}Checking for Arduino connections...${NC}"
USB_DEVICES=$(ls /dev/ttyUSB* 2>/dev/null | wc -l)
if [ "$USB_DEVICES" -ge 2 ]; then
    echo -e "${GREEN}✓ Found $USB_DEVICES USB devices${NC}"
elif [ "$USB_DEVICES" -eq 1 ]; then
    echo -e "${YELLOW}WARNING: Found only 1 USB device. Expected 2 (Motor 1 and Motor 2)${NC}"
else
    echo -e "${YELLOW}WARNING: No USB devices found. Arduino boards may not be connected.${NC}"
    echo "         Enter 'ls /dev/ttyUSB*' to check connections"
fi

echo ""
echo -e "${GREEN}Starting Remote Robot Lawn Mower Controller...${NC}"
echo ""
echo -e "${GREEN}Access web interface at:${NC}"
echo "  Local:   http://localhost:5000"
echo "  Network: http://$PI_IP:5000"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
echo ""

# Start the application
python3 "$PROJECT_DIR/app.py"

# Deactivate virtual environment on exit
deactivate
