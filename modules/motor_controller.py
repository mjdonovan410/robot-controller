"""
Motor Controller Module

This module centralizes command validation and simple in-memory motor state for
the two-wheel drivetrain. It does not talk to hardware directly; instead it
provides a structured place for validation and future higher-level control
policies.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MotorCommand:
    """Structured representation of a single motor command."""
    motor_id: int
    rpm: int
    direction: str  # forward, reverse, stop
    acceleration: int
    deceleration: int
    contactor_enabled: bool  # Enable blade contactor (mower)


class MotorController:
    """Validate and store the latest logical state for each motor."""
    
    # System-wide command limits used by validation and state clamping.
    MAX_RPM = 10500
    MIN_RPM = 0
    MAX_ACCELERATION = 100
    MAX_DECELERATION = 100
    
    def __init__(self):
        """Create default motor state for both wheels."""
        self.motor_states = {
            1: {
                'rpm': 0,
                'direction': 'stop',
                'acceleration': 50,
                'deceleration': 50,
                'contactor_enabled': False
            },
            2: {
                'rpm': 0,
                'direction': 'stop',
                'acceleration': 50,
                'deceleration': 50,
                'contactor_enabled': False
            }
        }
        
        logger.info(f"Motor controller initialized with MAX_RPM={self.MAX_RPM}")
    
    def validate_command(self, command: MotorCommand) -> tuple[bool, str]:
        """
        Validate a motor command
        
        Args:
            command: MotorCommand object
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if command.motor_id not in [1, 2]:
            return False, "Invalid motor ID"
        
        if not (self.MIN_RPM <= command.rpm <= self.MAX_RPM):
            return False, f"RPM must be between {self.MIN_RPM} and {self.MAX_RPM}"
        
        if command.direction not in ['forward', 'reverse', 'stop']:
            return False, "Invalid direction"
        
        if not (0 <= command.acceleration <= self.MAX_ACCELERATION):
            return False, f"Acceleration must be between 0 and {self.MAX_ACCELERATION}"
        
        if not (0 <= command.deceleration <= self.MAX_DECELERATION):
            return False, f"Deceleration must be between 0 and {self.MAX_DECELERATION}"
        
        return True, ""
    
    def update_motor_state(self, motor_id: int, **kwargs) -> bool:
        """
        Update motor state
        
        Args:
            motor_id: Motor ID (1 or 2)
            **kwargs: State parameters to update
        
        Returns:
            Success status
        """
        if motor_id not in self.motor_states:
            logger.error(f"Invalid motor ID: {motor_id}")
            return False
        
        try:
            # Each field is clamped independently so partial updates remain safe.
            if 'rpm' in kwargs:
                rpm = max(self.MIN_RPM, min(kwargs['rpm'], self.MAX_RPM))
                self.motor_states[motor_id]['rpm'] = rpm
            
            if 'direction' in kwargs:
                if kwargs['direction'] in ['forward', 'reverse', 'stop']:
                    self.motor_states[motor_id]['direction'] = kwargs['direction']
            
            if 'acceleration' in kwargs:
                accel = max(0, min(kwargs['acceleration'], self.MAX_ACCELERATION))
                self.motor_states[motor_id]['acceleration'] = accel
            
            if 'deceleration' in kwargs:
                decel = max(0, min(kwargs['deceleration'], self.MAX_DECELERATION))
                self.motor_states[motor_id]['deceleration'] = decel
            
            if 'contactor_enabled' in kwargs:
                self.motor_states[motor_id]['contactor_enabled'] = bool(kwargs['contactor_enabled'])
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating motor state: {e}")
            return False
    
    def get_motor_state(self, motor_id: int) -> dict:
        """
        Get the current state of a motor
        
        Args:
            motor_id: Motor ID (1 or 2)
        
        Returns:
            Motor state dictionary
        """
        return self.motor_states.get(motor_id, {}).copy()
    
    def get_all_motor_states(self) -> dict:
        """
        Get state of all motors
        
        Returns:
            Dictionary with motor states
        """
        return {mid: state.copy() for mid, state in self.motor_states.items()}
    
    def emergency_stop(self):
        """Force both stored motor states to a stopped, de-energized state."""
        logger.warning("EMERGENCY STOP triggered!")
        
        for motor_id in self.motor_states:
            self.motor_states[motor_id] = {
                'rpm': 0,
                'direction': 'stop',
                'acceleration': 0,
                'deceleration': 100,
                'contactor_enabled': False
            }
