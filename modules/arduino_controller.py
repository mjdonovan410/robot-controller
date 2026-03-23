"""
Arduino Controller Module
Handles serial communication with Arduino boards for motor control
"""

import serial
import logging
import json
from threading import Thread, Lock
from queue import Queue
from datetime import datetime

logger = logging.getLogger(__name__)


class ArduinoController:
    """Manages serial communication with Arduino motor controllers"""
    
    def __init__(self, motor1_port='/dev/ttyUSB0', motor2_port='/dev/ttyUSB1', baud_rate=115200):
        """
        Initialize Arduino controller
        
        Args:
            motor1_port: Serial port for Motor 1 Arduino
            motor2_port: Serial port for Motor 2 Arduino
            baud_rate: Serial communication baud rate
        """
        self.motor1_port = motor1_port
        self.motor2_port = motor2_port
        self.baud_rate = baud_rate
        
        self.ser1 = None
        self.ser2 = None
        self.connected = False
        
        self.command_queue = Queue()
        self.send_lock = Lock()
        self.sender_thread = None
        self.running = False
        
        self._init_serial_connections()
        self._start_sender_thread()
    
    def _init_serial_connections(self):
        """Initialize serial connections to both Arduinos"""
        try:
            # Motor 1
            self.ser1 = serial.Serial(
                port=self.motor1_port,
                baudrate=self.baud_rate,
                timeout=1,
                write_timeout=1
            )
            logger.info(f"Connected to Motor 1 on {self.motor1_port} @ {self.baud_rate} baud")
        except Exception as e:
            logger.warning(f"Failed to connect to Motor 1: {e}")
            self.ser1 = None
        
        try:
            # Motor 2
            self.ser2 = serial.Serial(
                port=self.motor2_port,
                baudrate=self.baud_rate,
                timeout=1,
                write_timeout=1
            )
            logger.info(f"Connected to Motor 2 on {self.motor2_port} @ {self.baud_rate} baud")
        except Exception as e:
            logger.warning(f"Failed to connect to Motor 2: {e}")
            self.ser2 = None
        
        self.connected = (self.ser1 is not None and self.ser2 is not None)
        if not self.connected:
            logger.warning("One or more Arduino connections failed - running in simulation mode")
    
    def _start_sender_thread(self):
        """Start the command sender thread"""
        self.running = True
        self.sender_thread = Thread(target=self._sender_loop, daemon=True)
        self.sender_thread.start()
        logger.info("Arduino sender thread started")
    
    def _sender_loop(self):
        """Process queued commands and send to Arduinos"""
        while self.running:
            try:
                command = self.command_queue.get(timeout=1)
                self._send_command(command)
            except:
                pass
    
    def send_motor_command(self, motor_id, rpm, direction, contactor_enabled=False, 
                          acceleration=50, deceleration=50):
        """
        Queue a motor command for sending to Arduino
        
        Args:
            motor_id: Motor ID (1 or 2)
            rpm: RPM value (0-3000)
            direction: 'forward', 'reverse', or 'stop'
            contactor_enabled: Enable mower blade contactor
            acceleration: Acceleration value (0-100)
            deceleration: Deceleration value (0-100)
        """
        command = {
            'motor_id': motor_id,
            'rpm': rpm,
            'direction': direction,
            'contactor': contactor_enabled,
            'acceleration': acceleration,
            'deceleration': deceleration,
            'timestamp': datetime.now().isoformat()
        }
        
        self.command_queue.put(command)
    
    def _send_command(self, command):
        """
        Send a command to the appropriate Arduino
        
        Args:
            command: Command dictionary
        """
        try:
            motor_id = command['motor_id']
            ser = self.ser1 if motor_id == 1 else self.ser2
            
            if ser is None or not ser.is_open:
                logger.debug(f"Arduino for motor {motor_id} not available - simulating command")
                return
            
            # Format command as JSON for Arduino
            # Expected format: {"rpm":1500,"dir":"forward","contactor":true,"accel":50,"decel":50}
            command_json = {
                'rpm': int(command['rpm']),
                'dir': command['direction'],
                'contactor': bool(command['contactor']),
                'accel': int(command['acceleration']),
                'decel': int(command['deceleration'])
            }
            
            # Add newline for Arduino serial parsing
            command_str = json.dumps(command_json) + '\n'
            
            with self.send_lock:
                ser.write(command_str.encode())
                logger.debug(f"Motor {motor_id} command sent: {command_str.strip()}")
        
        except Exception as e:
            logger.error(f"Error sending command to motor {command.get('motor_id')}: {e}")
    
    def read_arduino_response(self, motor_id):
        """
        Read response from Arduino (for debugging)
        
        Args:
            motor_id: Motor ID (1 or 2)
        
        Returns:
            Response string or None
        """
        try:
            ser = self.ser1 if motor_id == 1 else self.ser2
            
            if ser is None or not ser.is_open:
                return None
            
            if ser.in_waiting > 0:
                response = ser.readline().decode().strip()
                logger.debug(f"Response from Motor {motor_id}: {response}")
                return response
            
            return None
        
        except Exception as e:
            logger.error(f"Error reading from motor {motor_id}: {e}")
            return None
    
    def is_connected(self):
        """Check if connected to Arduinos"""
        return self.connected
    
    def close_all(self):
        """Close all serial connections"""
        self.running = False
        
        if self.ser1:
            self.ser1.close()
            logger.info("Motor 1 connection closed")
        
        if self.ser2:
            self.ser2.close()
            logger.info("Motor 2 connection closed")
        
        if self.sender_thread:
            self.sender_thread.join(timeout=2)
    
    def __del__(self):
        """Cleanup on deletion"""
        self.close_all()
