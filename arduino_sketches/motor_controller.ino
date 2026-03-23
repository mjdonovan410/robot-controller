/*
  Remote Robot Lawn Mower - Arduino Motor Controller Sketch
  
  This sketch demonstrates how to:
  - Receive motor control commands via serial communication from Raspberry Pi
  - Parse JSON format commands
  - Control DC motors with PWM
  - Enable contactor for mower blade
  
  Hardware Requirements:
  - Arduino Uno or compatible
  - Motor driver shield (L298N or similar)
  - DC motor(s)
  - Relay for mower blade contactor
  
  Wiring Example (L298N Motor Driver):
  - Motor 1 PWM: Pin 5 (PWM)
  - Motor 1 Direction 1: Pin 8 (HIGH = forward)
  - Motor 1 Direction 2: Pin 9 (LOW = forward)
  - Contactor Relay: Pin 6 (HIGH = enabled)
  
  Communication:
  - Baud Rate: 115200
  - Format: JSON strings ending with newline
  - Example: {"rpm":1500,"dir":"forward","contactor":true,"accel":50,"decel":50}\n
*/

#include <ArduinoJson.h>  // Include if using JSON parsing library
// Install: Sketch → Include Library → Manage Libraries → Search "ArduinoJson"

// ==================== PIN DEFINITIONS ====================
// Motor 1 Pins
const int MOTOR1_PWM_PIN = 5;      // D5 PWM
const int MOTOR1_DIR_PIN_A = 8;    // D8 Direction
const int MOTOR1_DIR_PIN_B = 9;    // D9 Direction

// Contactor Pins (Mower Blade)
const int CONTACTOR_PIN = 6;       // D6 Contactor relay

// Status LED
const int STATUS_LED_PIN = 13;

// ==================== CONSTANTS ====================
const int MAX_PWM = 255;
const int MIN_PWM = 0;

// Simple motor command structure
struct MotorCommand {
  int rpm;
  char direction[10];      // "forward", "reverse", "stop"
  bool contactor;
  int acceleration;
  int deceleration;
};

// Current motor state
struct MotorState {
  int current_pwm;
  MotorCommand last_command;
} motor_state = {0, {0, "stop", false, 50, 50}};

// ==================== SETUP ====================
void setup() {
  // Initialize Serial Communication
  Serial.begin(115200);
  while (!Serial) {
    delay(100);
  }
  
  Serial.println("Motor Controller Initialized");
  
  // Configure Motor Pins as OUTPUT
  pinMode(MOTOR1_PWM_PIN, OUTPUT);
  pinMode(MOTOR1_DIR_PIN_A, OUTPUT);
  pinMode(MOTOR1_DIR_PIN_B, OUTPUT);
  
  // Configure Contactor Pin
  pinMode(CONTACTOR_PIN, OUTPUT);
  digitalWrite(CONTACTOR_PIN, LOW);  // Start with contactor OFF
  
  // Configure Status LED
  pinMode(STATUS_LED_PIN, OUTPUT);
  
  // Emergency stop - stop motor
  stopMotor();
  
  Serial.println("Waiting for commands...");
}

// ==================== MAIN LOOP ====================
void loop() {
  // Check for incoming serial data
  if (Serial.available() > 0) {
    // Read the command string
    String jsonString = Serial.readStringUntil('\n');
    
    // Debug output
    Serial.print("Received: ");
    Serial.println(jsonString);
    
    // Parse and execute command
    if (parseAndExecuteCommand(jsonString)) {
      // Blink LED to indicate successful command
      blinkStatusLED(1);
      Serial.println("Command executed successfully");
    } else {
      // Blink twice for error
      blinkStatusLED(2);
      Serial.println("Command parse error");
    }
  }
  
  delay(10);  // Small delay to prevent CPU hogging
}

// ==================== COMMAND PARSING ====================
bool parseAndExecuteCommand(String jsonString) {
  // Simple JSON parsing (if ArduinoJson not available, use manual parsing)
  
  MotorCommand cmd;
  
  // Manual parsing approach (simple and works without extra libraries)
  if (!parseJSONManual(jsonString, cmd)) {
    return false;
  }
  
  // Validate command
  if (!validateCommand(cmd)) {
    Serial.println("Command validation failed");
    return false;
  }
  
  // Execute the command
  executeMotorCommand(cmd);
  
  // Store command as last known state
  motor_state.last_command = cmd;
  
  return true;
}

// ==================== JSON PARSING ====================
bool parseJSONManual(String jsonString, MotorCommand &cmd) {
  // Extract rpm
  int rpmStartIdx = jsonString.indexOf("\"rpm\":");
  if (rpmStartIdx == -1) return false;
  int rpmEndIdx = jsonString.indexOf(",", rpmStartIdx);
  if (rpmEndIdx == -1) rpmEndIdx = jsonString.indexOf("}", rpmStartIdx);
  
  String rpmStr = jsonString.substring(rpmStartIdx + 6, rpmEndIdx);
  rpmStr.trim();
  cmd.rpm = rpmStr.toInt();
  
  // Extract direction
  int dirStartIdx = jsonString.indexOf("\"dir\":");
  if (dirStartIdx == -1) return false;
  int dirEndIdx = jsonString.indexOf("\"", dirStartIdx + 7);  // Find closing quote
  String dirStr = jsonString.substring(dirStartIdx + 7, dirEndIdx);
  dirStr.trim();
  strcpy(cmd.direction, dirStr.c_str());
  
  // Extract contactor
  int contactorStartIdx = jsonString.indexOf("\"contactor\":");
  if (contactorStartIdx == -1) return false;
  String contactorStr = jsonString.substring(contactorStartIdx + 12, contactorStartIdx + 17);
  cmd.contactor = (contactorStr.indexOf("true") != -1);
  
  // Extract acceleration
  int accelStartIdx = jsonString.indexOf("\"accel\":");
  if (accelStartIdx != -1) {
    int accelEndIdx = jsonString.indexOf(",", accelStartIdx);
    if (accelEndIdx == -1) accelEndIdx = jsonString.indexOf("}", accelStartIdx);
    String accelStr = jsonString.substring(accelStartIdx + 8, accelEndIdx);
    accelStr.trim();
    cmd.acceleration = accelStr.toInt();
  }
  
  // Extract deceleration
  int decelStartIdx = jsonString.indexOf("\"decel\":");
  if (decelStartIdx != -1) {
    int decelEndIdx = jsonString.indexOf("}", decelStartIdx);
    String decelStr = jsonString.substring(decelStartIdx + 8, decelEndIdx);
    decelStr.trim();
    cmd.deceleration = decelStr.toInt();
  }
  
  return true;
}

// ==================== COMMAND VALIDATION ====================
bool validateCommand(const MotorCommand &cmd) {
  // Validate RPM range (0-3000)
  if (cmd.rpm < 0 || cmd.rpm > 3000) {
    Serial.print("Invalid RPM: ");
    Serial.println(cmd.rpm);
    return false;
  }
  
  // Validate direction
  if (strcmp(cmd.direction, "forward") != 0 &&
      strcmp(cmd.direction, "reverse") != 0 &&
      strcmp(cmd.direction, "stop") != 0) {
    Serial.print("Invalid direction: ");
    Serial.println(cmd.direction);
    return false;
  }
  
  return true;
}

// ==================== MOTOR CONTROL ====================
void executeMotorCommand(const MotorCommand &cmd) {
  // Set direction
  setMotorDirection(cmd.direction);
  
  // Set speed (convert RPM to PWM)
  int pwm = rpmToPWM(cmd.rpm);
  setMotorSpeed(pwm);
  
  // Control contactor (mower blade)
  setContactor(cmd.contactor);
  
  // Optional: Log telemetry
  logMotorState(cmd);
}

void setMotorDirection(const char *direction) {
  if (strcmp(direction, "forward") == 0) {
    digitalWrite(MOTOR1_DIR_PIN_A, HIGH);
    digitalWrite(MOTOR1_DIR_PIN_B, LOW);
    Serial.println("Direction: FORWARD");
  }
  else if (strcmp(direction, "reverse") == 0) {
    digitalWrite(MOTOR1_DIR_PIN_A, LOW);
    digitalWrite(MOTOR1_DIR_PIN_B, HIGH);
    Serial.println("Direction: REVERSE");
  }
  else {
    // Stop
    digitalWrite(MOTOR1_DIR_PIN_A, LOW);
    digitalWrite(MOTOR1_DIR_PIN_B, LOW);
    Serial.println("Direction: STOP");
  }
}

void setMotorSpeed(int pwm) {
  // Constrain PWM to valid range
  pwm = constrain(pwm, MIN_PWM, MAX_PWM);
  
  // Apply PWM to motor
  analogWrite(MOTOR1_PWM_PIN, pwm);
  
  motor_state.current_pwm = pwm;
  Serial.print("PWM set to: ");
  Serial.println(pwm);
}

void stopMotor() {
  digitalWrite(MOTOR1_PWM_PIN, LOW);
  digitalWrite(MOTOR1_DIR_PIN_A, LOW);
  digitalWrite(MOTOR1_DIR_PIN_B, LOW);
  motor_state.current_pwm = 0;
  Serial.println("Motor stopped");
}

void setContactor(bool enabled) {
  digitalWrite(CONTACTOR_PIN, enabled ? HIGH : LOW);
  Serial.print("Contactor: ");
  Serial.println(enabled ? "ON" : "OFF");
}

// ==================== UTILITY FUNCTIONS ====================
int rpmToPWM(int rpm) {
  // Simple linear mapping: RPM to PWM
  // Adjust these values based on your motor characteristics
  // You may need to implement min/max PWM thresholds
  
  if (rpm == 0) return 0;
  
  // Example: 3000 RPM = 255 PWM
  int pwm = (rpm * 255) / 3000;
  
  // Optional: Set minimum PWM for motor to overcome static friction
  if (pwm > 0 && pwm < 80) {
    pwm = 80;  // Minimum PWM to get motor moving
  }
  
  return constrain(pwm, 0, 255);
}

void blinkStatusLED(int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(STATUS_LED_PIN, HIGH);
    delay(100);
    digitalWrite(STATUS_LED_PIN, LOW);
    delay(100);
  }
}

void logMotorState(const MotorCommand &cmd) {
  Serial.print("Motor State - RPM: ");
  Serial.print(cmd.rpm);
  Serial.print(" | Direction: ");
  Serial.print(cmd.direction);
  Serial.print(" | PWM: ");
  Serial.print(motor_state.current_pwm);
  Serial.print(" | Contactor: ");
  Serial.print(cmd.contactor ? "ON" : "OFF");
  Serial.print(" | Accel: ");
  Serial.print(cmd.acceleration);
  Serial.print(" | Decel: ");
  Serial.println(cmd.deceleration);
}

// ==================== OPTIONAL FEATURES ====================

/*
// Smooth acceleration/deceleration (optional)
void smoothAccelerate(int targetPWM, int acceleration) {
  int steps = acceleration / 10;  // More acceleration = fewer steps
  int pwmDifference = targetPWM - motor_state.current_pwm;
  int stepSize = pwmDifference / max(steps, 1);
  
  for (int current = motor_state.current_pwm; 
       current != targetPWM; 
       current += stepSize) {
    analogWrite(MOTOR1_PWM_PIN, constrain(current, 0, 255));
    delay(50);
  }
  
  analogWrite(MOTOR1_PWM_PIN, targetPWM);
}

// Current sensing (if using current sensor on A0)
int readMotorCurrent() {
  int rawValue = analogRead(A0);
  // Convert to amps: 5V / 1024 * 30A per 5V = ~0.147A per step
  int current_mA = (rawValue * 147) / 1024;
  return current_mA;
}
*/
