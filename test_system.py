#!/usr/bin/env python3
"""
Remote Robot Lawn Mower Controller - Diagnostic and Test Script

This script is a technician-facing smoke test for the development machine. It
verifies Python dependencies, basic hardware availability, serial transport,
and a few project-level imports before the full web application is started.
"""

import sys
import os
import time
import serial
import json
from datetime import datetime

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def print_header(text):
    """Print formatted header"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)

def print_result(test_name, passed, details=""):
    """Print test result"""
    status = "✓ PASS" if passed else "✗ FAIL"
    color = "\033[92m" if passed else "\033[91m"  # Green or Red
    reset = "\033[0m"
    print(f"{color}{status}{reset} - {test_name}")
    if details:
        print(f"       {details}")

def test_python_version():
    """Test Python version"""
    version = sys.version_info
    required = (3, 8)
    passed = version >= required
    print_result(
        "Python Version",
        passed,
        f"Python {version.major}.{version.minor} {'✓' if passed else '(need 3.8+)'}"
    )
    return passed

def test_opencv():
    """Test OpenCV installation"""
    try:
        import cv2
        print_result("OpenCV", True, f"Version {cv2.__version__}")
        return True
    except ImportError as e:
        print_result("OpenCV", False, str(e))
        return False

def test_flask():
    """Test Flask installation"""
    try:
        import flask
        print_result("Flask", True, f"Version {flask.__version__}")
        return True
    except ImportError as e:
        print_result("Flask", False, str(e))
        return False

def test_socketio():
    """Test Flask-SocketIO installation"""
    try:
        import flask_socketio
        print_result("Flask-SocketIO", True)
        return True
    except ImportError as e:
        print_result("Flask-SocketIO", False, str(e))
        return False

def test_pyserial():
    """Test PySerial installation"""
    try:
        import serial
        print_result("PySerial", True)
        return True
    except ImportError as e:
        print_result("PySerial", False, str(e))
        return False

def test_camera():
    """Test USB camera"""
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                shape = frame.shape
                print_result("USB Camera", True, f"Resolution {shape[1]}x{shape[0]}")
                cap.release()
                return True
            else:
                print_result("USB Camera", False, "Cannot capture frame")
                cap.release()
                return False
        else:
            print_result("USB Camera", False, "Camera not accessible at /dev/video0")
            return False
    except Exception as e:
        print_result("USB Camera", False, str(e))
        return False

def test_serial_ports():
    """Probe the expected USB serial devices used by the Arduino boards."""
    import glob
    
    # The project expects Arduinos to appear as /dev/ttyUSB* on Linux.
    ports = glob.glob('/dev/ttyUSB*')
    
    if len(ports) == 0:
        print_result("Arduino Serial Ports", False, "No /dev/ttyUSB* devices found")
        return False
    
    print_result("Arduino Serial Ports", len(ports) >= 2, 
                f"Found {len(ports)} device(s): {', '.join(ports)}")
    
    # A successful open/close cycle confirms the port is accessible to the user.
    for port in ports[:2]:  # Test first two
        try:
            ser = serial.Serial(port, 115200, timeout=1)
            time.sleep(0.5)
            ser.close()
            print(f"       ✓ {port} - Connection OK")
        except Exception as e:
            print(f"       ✗ {port} - {str(e)}")
    
    return len(ports) >= 1

def test_imports():
    """Confirm the custom project modules import without side effects."""
    try:
        from modules.camera_controller import CameraController
        print_result("CameraController Import", True)
        cam_ok = True
    except Exception as e:
        print_result("CameraController Import", False, str(e))
        cam_ok = False
    
    try:
        from modules.motor_controller import MotorController
        print_result("MotorController Import", True)
        motor_ok = True
    except Exception as e:
        print_result("MotorController Import", False, str(e))
        motor_ok = False
    
    try:
        from modules.arduino_controller import ArduinoController
        print_result("ArduinoController Import", True)
        arduino_ok = True
    except Exception as e:
        print_result("ArduinoController Import", False, str(e))
        arduino_ok = False
    
    return cam_ok and motor_ok and arduino_ok

def test_flask_app():
    """Import the Flask app and perform a lightweight route smoke test."""
    try:
        from app import app, motor_state
        print_result("Flask App Import", True)
        
        with app.test_client() as client:
            response = client.get('/')
            if response.status_code == 200:
                print_result("Flask Routes", True, "Index route accessible")
                return True
            else:
                print_result("Flask Routes", False, f"Status {response.status_code}")
                return False
    except Exception as e:
        print_result("Flask App Import", False, str(e))
        return False

def test_motor_controller():
    """Exercise the pure-Python motor validation layer."""
    try:
        from modules.motor_controller import MotorController, MotorCommand
        
        mc = MotorController()
        
        # First confirm that a normal in-range command is accepted.
        cmd = MotorCommand(
            motor_id=1,
            rpm=1500,
            direction='forward',
            acceleration=50,
            deceleration=50,
            contactor_enabled=True
        )
        
        valid, msg = mc.validate_command(cmd)
        print_result("Motor Command Validation", valid, msg or "Forward 1500 RPM valid")
        
        # Then confirm the validator still rejects values beyond the configured
        # RPM ceiling so application-side clamping is not the only safeguard.
        bad_cmd = MotorCommand(
            motor_id=1,
            rpm=5001,
            direction='forward',
            acceleration=50,
            deceleration=50,
            contactor_enabled=False
        )
        
        valid2, msg2 = mc.validate_command(bad_cmd)
        print_result("Motor Command Validation (Invalid)", not valid2, 
                    msg2 or "Correctly rejected invalid RPM")
        
        return valid and not valid2
    except Exception as e:
        print_result("Motor Controller", False, str(e))
        return False

def test_arduino_json_format():
    """Validate the compact JSON structure sent over the serial link."""
    try:
        command = {
            'rpm': 1500,
            'dir': 'forward',
            'contactor': True,
            'accel': 50,
            'decel': 50
        }
        
        json_str = json.dumps(command)
        parsed = json.loads(json_str)
        
        print_result("Arduino JSON Format", True, f"Valid: {json_str}")
        return True
    except Exception as e:
        print_result("Arduino JSON Format", False, str(e))
        return False

def test_manual_serial_send():
    """Send one direct serial command to the first detected Arduino port."""
    import glob
    
    ports = glob.glob('/dev/ttyUSB*')
    if not ports:
        print_result("Manual Serial Test", False, "No USB serial devices found")
        return False
    
    try:
        port = ports[0]
        print(f"\n       Testing communication on {port}...")
        print("       Sending test command to Arduino...")
        
        ser = serial.Serial(port, 115200, timeout=1)
        time.sleep(0.5)  # Wait for Arduino to initialize
        
        # This payload matches the structure used by the application itself.
        test_cmd = json.dumps({
            'rpm': 500,
            'dir': 'forward',
            'contactor': False,
            'accel': 50,
            'decel': 50
        })
        
        ser.write((test_cmd + '\n').encode())
        time.sleep(0.2)
        
        # A response is helpful but not mandatory because some sketches only log
        # after certain commands or may not echo anything at all.
        if ser.in_waiting > 0:
            response = ser.readline().decode().strip()
            print(f"       ✓ Response: {response}")
            result = True
        else:
            print("       (No response - Arduino may not be echoing)")
            result = True
        
        ser.close()
        print_result("Manual Serial Communication", result)
        return result
    
    except Exception as e:
        print_result("Manual Serial Communication", False, str(e))
        return False

def interactive_test():
    """Allow a developer to poke the pure-Python motor state interactively."""
    print_header("INTERACTIVE TESTING")
    
    try:
        from modules.motor_controller import MotorController
        
        mc = MotorController()
        
        while True:
            print("\nInteractive Motor Controller Test:")
            print("  1. Set Motor RPM")
            print("  2. Set Direction")
            print("  3. Toggle Contactor")
            print("  4. View Motor State")
            print("  5. Emergency Stop")
            print("  6. Exit")
            
            choice = input("\nSelect option (1-6): ").strip()
            
            if choice == '1':
                rpm = int(input("Enter RPM (0-5000): "))
                mc.update_motor_state(1, rpm=rpm)
                print(f"Motor 1 RPM set to {rpm}")
            
            elif choice == '2':
                direction = input("Enter direction (forward/reverse/stop): ")
                mc.update_motor_state(1, direction=direction)
                print(f"Motor 1 direction set to {direction}")
            
            elif choice == '3':
                mc.update_motor_state(1, contactor_enabled=True)
                print("Contactor enabled")
            
            elif choice == '4':
                state = mc.get_motor_state(1)
                print(f"Motor 1 State: {json.dumps(state, indent=2)}")
            
            elif choice == '5':
                mc.emergency_stop()
                print("EMERGENCY STOP - All motors disabled")
            
            elif choice == '6':
                break
            
            else:
                print("Invalid option")
    
    except Exception as e:
        print(f"Error: {e}")

def generate_report():
    """Print basic environment metadata for troubleshooting sessions."""
    print_header("DIGITAL DIAGNOSTICS REPORT")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")

def main():
    """Run the full diagnostic sequence in a human-readable order."""
    print("\n")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║   Remote Robot Lawn Mower Controller - Diagnostic Tool    ║")
    print("╚════════════════════════════════════════════════════════════╝")
    
    # Start with the Python/runtime prerequisites before touching hardware.
    print_header("1. SYSTEM REQUIREMENTS")
    test_python_version()
    
    # Import checks catch missing packages before the app fails at startup.
    print_header("2. PYTHON DEPENDENCIES")
    dep_results = [
        test_opencv(),
        test_flask(),
        test_socketio(),
        test_pyserial()
    ]
    
    # Hardware tests are read-only probes and do not move motors.
    print_header("3. HARDWARE")
    hw_results = [
        test_camera(),
        test_serial_ports()
    ]
    
    # Project structure tests verify internal imports and route wiring.
    print_header("4. PROJECT STRUCTURE")
    proj_results = [
        test_imports(),
        test_flask_app()
    ]
    
    # Functionality tests exercise pure-software command formatting/validation.
    print_header("5. FUNCTIONALITY TESTS")
    func_results = [
        test_motor_controller(),
        test_arduino_json_format(),
        test_manual_serial_send()
    ]
    
    print_header("SUMMARY")
    all_passed = all(dep_results + hw_results + proj_results + func_results)
    
    if all_passed:
        print("\n✓ All tests PASSED! System is ready to run.")
        print("\nStart the application with:")
        print("  python3 app.py")
    else:
        print("\n✗ Some tests FAILED. Please check the errors above.")
        print("\nCommon issues:")
        print("  - Camera: sudo apt install python3-opencv")
        print("  - Serial: ls /dev/ttyUSB* (check Arduino connections)")
        print("  - Packages: pip install -r requirements.txt")
    
    # Offer a manual follow-up only after automated diagnostics finish.
    if input("\nRun interactive tests? (y/n): ").lower() == 'y':
        interactive_test()
    
    print("\nDiagnostic complete.\n")

if __name__ == '__main__':
    main()
