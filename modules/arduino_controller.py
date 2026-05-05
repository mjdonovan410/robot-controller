"""
Arduino Controller Module

This module owns the serial links to the two Arduino motor controllers. It
accepts high-level wheel commands from the Flask app, serializes them to the
compact JSON format expected by the sketches, and exposes helper methods for
reading back diagnostic messages from each board.
"""

import serial
import logging
import json
from threading import Thread, Lock
from queue import Queue, Empty
from datetime import datetime

logger = logging.getLogger(__name__)


class ArduinoController:
    """Manage the pair of Arduino serial links used for left/right wheel control."""
    
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
        """Open both serial ports and remember whether the pair is fully available."""
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
        """Start the background thread that drains the outgoing command queue."""
        self.running = True
        self.sender_thread = Thread(target=self._sender_loop, daemon=True)
        self.sender_thread.start()
        logger.info("Arduino sender thread started")
    
    def _sender_loop(self):
        """Continuously dequeue commands and push them to the correct serial port.

        The loop coalesces bursts of queued commands and only sends the latest
        command per motor. This prevents command backlog latency when the
        browser is producing frequent updates (e.g., gamepad polling).
        """
        while self.running:
            try:
                command = self.command_queue.get(timeout=0.05)
            except Empty:
                continue

            latest_by_motor = {command['motor_id']: command}

            while True:
                try:
                    queued_command = self.command_queue.get_nowait()
                    latest_by_motor[queued_command['motor_id']] = queued_command
                except Empty:
                    break

            for motor_id in sorted(latest_by_motor.keys()):
                self._send_command(latest_by_motor[motor_id])
    
    def send_motor_command(self, motor_id, rpm, direction, contactor_enabled=False, 
                          acceleration=50, deceleration=50):
        """
        Queue a motor command for sending to Arduino
        
        Args:
            motor_id: Motor ID (1 or 2)
            rpm: RPM value (0-10500)
            direction: 'forward', 'reverse', or 'stop'
            contactor_enabled: Enable mower blade contactor
            acceleration: Acceleration value (0-300)
            deceleration: Deceleration value (0-300)
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
        """Serialize one queued command and write it to the correct Arduino."""
        try:
            motor_id = command['motor_id']
            ser = self.ser1 if motor_id == 1 else self.ser2
            
            if ser is None or not ser.is_open:
                logger.debug(f"Arduino for motor {motor_id} not available - simulating command")
                return
            
            # The Arduino sketch expects compact JSON terminated by a newline so
            # it can recover whole command frames even on a small serial buffer.
            command_json = {
                'rpm': int(command['rpm']),
                'dir': command['direction'],
                'contactor': bool(command['contactor']),
                'accel': int(command['acceleration']),
                'decel': int(command['deceleration'])
            }
            
            # Keep frames short to reduce the chance of merged or truncated
            # packets when commands are sent at a high rate.
            command_str = json.dumps(command_json, separators=(',', ':')) + '\n'
            
            with self.send_lock:
                ser.write(command_str.encode())
                logger.debug(f"Motor {motor_id} command sent: {command_str.strip()}")
        
        except Exception as e:
            logger.error(f"Error sending command to motor {command.get('motor_id')}: {e}")
    
    def read_arduino_response(self, motor_id):
        """Return a single newline-delimited diagnostic line from one Arduino."""
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
        """Stop the sender thread and close both serial ports safely."""
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
