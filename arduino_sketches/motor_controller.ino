/*
  Remote Robot Lawn Mower - Arduino Motor Controller Sketch

  Role in the system:
  - Receive newline-delimited JSON commands from the Raspberry Pi.
  - Translate those commands into STEP/DIR motion for a stepper driver.
  - Ramp speed up and down smoothly instead of jumping instantly.
  - Hold direction during deceleration, and only flip DIR once the motor has
    coasted down to zero RPM.
  - Switch the blade contactor relay on or off.

  Hardware assumptions:
  - Arduino Uno or compatible board.
  - One external stepper driver that accepts STEP and DIR inputs.
  - One relay output used to energize the mower blade contactor.

  Wiring:
  - STEP  -> D5
  - DIR   -> D8 (LOW = forward, HIGH = reverse)
  - Relay -> D6

  Serial protocol:
  - Baud rate: 115200
  - Framing: one JSON object per line
  - Example: {"rpm":1500,"dir":"forward","contactor":true,"accel":50,"decel":50}
*/

// ==================== PIN DEFINITIONS ====================
// Motor 1 Pins
const int MOTOR1_STEP_PIN = 5;     // D5 Step output
const int MOTOR1_DIR_PIN = 8;      // D8 Direction (LOW=forward, HIGH=reverse)

// Contactor Pins (Mower Blade)
const int CONTACTOR_PIN = 6;       // D6 Contactor relay

// Status LED
const int STATUS_LED_PIN = 13;

// ==================== CONSTANTS ====================
const int MAX_RPM = 10500;
const int MIN_RPM = 0;
const int MAX_ACCEL_SETTING = 100;
const int MAX_DECEL_SETTING = 100;
const unsigned long STEP_PULSES_PER_REV = 200;
const unsigned long LED_BLINK_INTERVAL_MS = 100;
// Ramp update cadence for the speed integrator.
const unsigned long RAMP_UPDATE_MICROS = 1000UL;
// Convert accel/decel slider settings into RPM-per-second rates.
const float MIN_RAMP_RATE_RPM_PER_SEC = 10.0f;
const float MAX_RAMP_RATE_RPM_PER_SEC = 30000.0f;
const float STOP_RPM_THRESHOLD = 0.5f;
const float STOP_SNAP_RPM_THRESHOLD = 120.0f;

// Direction strings are reused throughout parsing, validation, and state
// updates. Keeping them centralized avoids typo-driven bugs.
const char DIRECTION_FORWARD[] = "forward";
const char DIRECTION_REVERSE[] = "reverse";
const char DIRECTION_STOP[] = "stop";

// Simple motor command structure
struct MotorCommand {
  int rpm;
  char direction[10];      // "forward", "reverse", "stop"
  bool contactor;
  int acceleration;
  int deceleration;
};

// Runtime state for the motion engine.
//
// The sketch keeps both a current RPM and a target RPM. That allows the main
// loop to change frequency gradually over time rather than making abrupt jumps
// whenever the browser sends a new command.
struct MotorState {
  float current_rpm;            // actual running RPM (ramped, floating-point for smoothness)
  int target_rpm;               // desired RPM (forced 0 while waiting for dir flip)
  int pending_target_rpm;       // RPM to ramp to after direction flip completes
  bool stepper_enabled;
  unsigned long step_interval_micros;
  unsigned long active_step_frequency_hz;
  bool tone_running;
  unsigned long last_ramp_update_micros;
  char latched_direction[10];   // direction currently on the DIR pin
  char pending_direction[10];   // direction to flip to once current_rpm reaches 0
  bool direction_change_pending;
  MotorCommand last_command;
} motor_state = {0, 0, 0, false, 0, 0, false, 0, "stop", "stop", false, {0, "stop", false, 50, 50}};

// Serial input is accumulated here until a full newline-delimited command is
// received. This makes the sketch tolerant of partial serial reads.
String serialBuffer = "";
bool led_is_on = false;
int led_toggle_count_remaining = 0;
unsigned long last_led_toggle_millis = 0;

// ==================== INTERNAL HELPERS ====================
bool isDirectionValid(const char *direction) {
  return strcmp(direction, DIRECTION_FORWARD) == 0 ||
         strcmp(direction, DIRECTION_REVERSE) == 0 ||
         strcmp(direction, DIRECTION_STOP) == 0;
}

bool isEffectivelyStopped(float rpm) {
  return rpm <= STOP_RPM_THRESHOLD;
}

void copyDirection(char *dest, const char *src, size_t destSize) {
  if (destSize == 0) {
    return;
  }
  strncpy(dest, src, destSize - 1);
  dest[destSize - 1] = '\0';
}

bool findFieldValueStart(const String &jsonString, const char *fieldKey, int &valueStart) {
  int fieldIdx = jsonString.indexOf(fieldKey);
  if (fieldIdx == -1) {
    return false;
  }

  valueStart = fieldIdx + strlen(fieldKey);
  while (valueStart < jsonString.length() &&
         (jsonString[valueStart] == ' ' || jsonString[valueStart] == '\t')) {
    valueStart++;
  }

  return valueStart < jsonString.length();
}

bool parseIntField(const String &jsonString, const char *fieldKey, int &outValue, bool required) {
  int valueStart = 0;
  if (!findFieldValueStart(jsonString, fieldKey, valueStart)) {
    return !required;
  }

  int valueEnd = jsonString.indexOf(",", valueStart);
  if (valueEnd == -1) {
    valueEnd = jsonString.indexOf("}", valueStart);
  }
  if (valueEnd == -1 || valueEnd <= valueStart) {
    return false;
  }

  String valueToken = jsonString.substring(valueStart, valueEnd);
  valueToken.trim();
  if (valueToken.length() == 0) {
    return false;
  }

  outValue = valueToken.toInt();
  return true;
}

bool parseBoolField(const String &jsonString, const char *fieldKey, bool &outValue, bool required) {
  int valueStart = 0;
  if (!findFieldValueStart(jsonString, fieldKey, valueStart)) {
    return !required;
  }

  int valueEnd = jsonString.indexOf(",", valueStart);
  if (valueEnd == -1) {
    valueEnd = jsonString.indexOf("}", valueStart);
  }
  if (valueEnd == -1 || valueEnd <= valueStart) {
    return false;
  }

  String valueToken = jsonString.substring(valueStart, valueEnd);
  valueToken.trim();

  if (valueToken == "true") {
    outValue = true;
    return true;
  }
  if (valueToken == "false") {
    outValue = false;
    return true;
  }

  return false;
}

bool parseStringField(const String &jsonString, const char *fieldKey, char *dest, size_t destSize, bool required) {
  int valueStart = 0;
  if (!findFieldValueStart(jsonString, fieldKey, valueStart)) {
    return !required;
  }

  if (jsonString[valueStart] != '"') {
    return false;
  }

  int valueEnd = jsonString.indexOf('"', valueStart + 1);
  if (valueEnd == -1 || valueEnd <= valueStart + 1) {
    return false;
  }

  String valueToken = jsonString.substring(valueStart + 1, valueEnd);
  valueToken.trim();
  copyDirection(dest, valueToken.c_str(), destSize);
  return true;
}

// ==================== SETUP ====================
void setup() {
  // Initialize the serial link used by the Raspberry Pi control process.
  Serial.begin(115200);
  while (!Serial) {
    delay(100);
  }
  
  Serial.println("Motor Controller Initialized");
  
  // Set all hardware outputs to known-safe startup states.
  pinMode(MOTOR1_STEP_PIN, OUTPUT);
  pinMode(MOTOR1_DIR_PIN, OUTPUT);
  digitalWrite(MOTOR1_STEP_PIN, LOW);
  
  // Configure Contactor Pin
  pinMode(CONTACTOR_PIN, OUTPUT);
  digitalWrite(CONTACTOR_PIN, LOW);  // Start with contactor OFF
  
  // Configure Status LED
  pinMode(STATUS_LED_PIN, OUTPUT);
  
  // The controller should always boot in a non-moving state.
  stopMotor();
  
  Serial.println("Waiting for commands...");
}

// ==================== MAIN LOOP ====================
void loop() {
  // Each service function performs a small, non-blocking slice of work so the
  // sketch can keep pulse timing stable even while it is receiving commands.
  serviceSerialInput();
  serviceStepper();
  serviceStatusLED();
}

void serviceSerialInput() {
  // Read every available byte so we do not fall behind when commands arrive
  // quickly from the browser gamepad polling loop.
  while (Serial.available() > 0) {
    char incoming = static_cast<char>(Serial.read());

    if (incoming == '\r') {
      continue;
    }

    if (incoming == '\n') {
      String rawInput = serialBuffer;
      serialBuffer = "";
      rawInput.trim();

      if (rawInput.length() == 0) {
        continue;
      }

      // Recover the last complete JSON object in case serial timing caused
      // extra bytes or merged frames to appear in the buffer.
      String jsonString = extractLastCompleteJson(rawInput);
      if (jsonString.length() == 0) {
        Serial.print("Command framing error: ");
        Serial.println(rawInput);
        blinkStatusLED(2);
        continue;
      }

      if (parseAndExecuteCommand(jsonString)) {
        blinkStatusLED(1);
      } else {
        blinkStatusLED(2);
        Serial.println("Command parse error");
      }

      continue;
    }

    serialBuffer += incoming;
    if (serialBuffer.length() > 160) {
      serialBuffer.remove(0, serialBuffer.length() - 160);
    }
  }
}

String extractLastCompleteJson(const String &input) {
  // Commands are expected to be one JSON object per line. When serial framing
  // gets messy, this helper salvages the last fully closed object on the line.
  int endIdx = input.lastIndexOf('}');
  if (endIdx == -1) {
    return "";
  }

  int startIdx = input.lastIndexOf('{', endIdx);
  if (startIdx == -1 || startIdx > endIdx) {
    return "";
  }

  return input.substring(startIdx, endIdx + 1);
}

// ==================== COMMAND PARSING ====================
bool parseAndExecuteCommand(String jsonString) {
  MotorCommand cmd;
  
  // The sketch uses lightweight manual parsing to avoid pulling in a full JSON
  // library on the microcontroller.
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
  
  // Keep the command so the ramp engine can continue using the most recent
  // acceleration and deceleration parameters between serial updates.
  motor_state.last_command = cmd;
  
  return true;
}

// ==================== JSON PARSING ====================
bool parseJSONManual(String jsonString, MotorCommand &cmd) {
  // Each field is extracted independently so malformed input can be rejected
  // early without applying partial state to the motor.

  // Safe defaults ensure deterministic behavior even if optional fields are
  // absent in a malformed or legacy command payload.
  cmd.rpm = 0;
  copyDirection(cmd.direction, DIRECTION_STOP, sizeof(cmd.direction));
  cmd.contactor = false;
  cmd.acceleration = 50;
  cmd.deceleration = 50;

  if (!parseIntField(jsonString, "\"rpm\":", cmd.rpm, true)) {
    return false;
  }

  if (!parseStringField(jsonString, "\"dir\":", cmd.direction, sizeof(cmd.direction), true)) {
    return false;
  }

  if (!parseBoolField(jsonString, "\"contactor\":", cmd.contactor, true)) {
    return false;
  }

  if (!parseIntField(jsonString, "\"accel\":", cmd.acceleration, false)) {
    return false;
  }

  if (!parseIntField(jsonString, "\"decel\":", cmd.deceleration, false)) {
    return false;
  }
  
  return true;
}

// ==================== COMMAND VALIDATION ====================
bool validateCommand(const MotorCommand &cmd) {
  // Validate RPM range (0-10500)
  if (cmd.rpm < MIN_RPM || cmd.rpm > MAX_RPM) {
    Serial.print("Invalid RPM: ");
    Serial.println(cmd.rpm);
    return false;
  }
  
  // Validate direction
  if (!isDirectionValid(cmd.direction)) {
    Serial.print("Invalid direction: ");
    Serial.println(cmd.direction);
    return false;
  }
  
  // Validate accel/decel tuning ranges used by the ramp engine.
  if (cmd.acceleration < 0 || cmd.acceleration > MAX_ACCEL_SETTING) {
    Serial.print("Invalid acceleration: ");
    Serial.println(cmd.acceleration);
    return false;
  }

  if (cmd.deceleration < 0 || cmd.deceleration > MAX_DECEL_SETTING) {
    Serial.print("Invalid deceleration: ");
    Serial.println(cmd.deceleration);
    return false;
  }

  return true;
}

// ==================== MOTOR CONTROL ====================
void executeMotorCommand(const MotorCommand &cmd) {
  int newRpm = constrain(cmd.rpm, MIN_RPM, MAX_RPM);
  bool isStop = (newRpm == 0) || (strcmp(cmd.direction, DIRECTION_STOP) == 0);

  // For a stop command the DIR pin should remain where it is until the ramp has
  // brought the motor fully to zero. That prevents the release jerk caused by
  // flipping direction while pulses are still being generated.
  const char *newDir = isStop ? motor_state.latched_direction : cmd.direction;

  bool directionChanging = !isStop &&
                           !isEffectivelyStopped(motor_state.current_rpm) &&
                           (strcmp(newDir, motor_state.latched_direction) != 0);

  if (directionChanging || motor_state.direction_change_pending) {
    // A live direction change is handled as a three-stage sequence:
    // 1. Ramp the currently latched direction down to zero RPM.
    // 2. Flip the DIR pin only after the motor is fully stopped.
    // 3. Ramp back up to the newly requested RPM.
    //
    // Pending values are overwritten every time so a new trigger command can
    // cancel an older pending reversal during the ramp-down phase.
    copyDirection(motor_state.pending_direction, newDir, sizeof(motor_state.pending_direction));
    motor_state.pending_target_rpm = isStop ? 0 : newRpm;
    motor_state.direction_change_pending = true;
    motor_state.target_rpm = 0;   // force ramp-down regardless of new RPM
    motor_state.stepper_enabled = !isEffectivelyStopped(motor_state.current_rpm);
  } else {
    // Same-direction speed changes are safe: there is no need to force a stop
    // because the ramp engine can move directly toward the new target RPM.
    if (isEffectivelyStopped(motor_state.current_rpm)) {
      setMotorDirection(newDir);
      copyDirection(motor_state.latched_direction, newDir, sizeof(motor_state.latched_direction));
    }
    motor_state.target_rpm = newRpm;
    if (newRpm > 0) {
      motor_state.stepper_enabled = true;
    }
  }

  setContactor(cmd.contactor);
  logMotorState(cmd);
}

void setMotorDirection(const char *direction) {
  // The hardware uses a single DIR pin, so this function deliberately reduces
  // the direction decision to a simple HIGH/LOW write.
  if (strcmp(direction, DIRECTION_REVERSE) == 0) {
    digitalWrite(MOTOR1_DIR_PIN, HIGH);  // 1 = reverse
  } else {
    digitalWrite(MOTOR1_DIR_PIN, LOW);   // 0 = forward (also for stop)
  }
}

// Recompute the period between STEP pulses from the current commanded RPM.
// This runs after every ramp tick so tone() tracks the current step frequency.
void recalcStepInterval() {
  if (isEffectivelyStopped(motor_state.current_rpm)) {
    motor_state.stepper_enabled = false;
    motor_state.step_interval_micros = 0;
    if (motor_state.tone_running) {
      noTone(MOTOR1_STEP_PIN);
      motor_state.tone_running = false;
      motor_state.active_step_frequency_hz = 0;
    }
    digitalWrite(MOTOR1_STEP_PIN, LOW);
    motor_state.current_rpm = 0.0f;
    return;
  }

  motor_state.stepper_enabled = true;
  unsigned long stepsPerSecond = static_cast<unsigned long>((motor_state.current_rpm * STEP_PULSES_PER_REV) / 60.0f);
  if (stepsPerSecond == 0) {
    stepsPerSecond = 1;
  }
  motor_state.step_interval_micros = 1000000UL / stepsPerSecond;

  // tone() generates a continuous square wave; each rising edge becomes one
  // STEP event at the external driver input.
  if (!motor_state.tone_running || motor_state.active_step_frequency_hz != stepsPerSecond) {
    tone(MOTOR1_STEP_PIN, stepsPerSecond);
    motor_state.tone_running = true;
    motor_state.active_step_frequency_hz = stepsPerSecond;
  }
}

float accelerationSettingToRate(int setting) {
  // Map the browser's 0-100 acceleration slider directly into an RPM-per-
  // second ramp rate.
  float normalized = constrain(setting, 0, MAX_ACCEL_SETTING) /
                     static_cast<float>(MAX_ACCEL_SETTING);
  return MIN_RAMP_RATE_RPM_PER_SEC +
         (MAX_RAMP_RATE_RPM_PER_SEC - MIN_RAMP_RATE_RPM_PER_SEC) * normalized;
}

float decelerationSettingToRate(int setting) {
  // Deceleration uses the same scale as acceleration, but is kept separate so
  // the two behaviors are easy to tune independently later.
  float normalized = constrain(setting, 0, MAX_DECEL_SETTING) /
                     static_cast<float>(MAX_DECEL_SETTING);
  return MIN_RAMP_RATE_RPM_PER_SEC +
         (MAX_RAMP_RATE_RPM_PER_SEC - MIN_RAMP_RATE_RPM_PER_SEC) * normalized;
}

void updateRampedSpeed(unsigned long nowMicros) {
  if (motor_state.last_ramp_update_micros == 0) {
    motor_state.last_ramp_update_micros = nowMicros;
    return;
  }

  unsigned long elapsedMicros = nowMicros - motor_state.last_ramp_update_micros;
  if (elapsedMicros < RAMP_UPDATE_MICROS) {
    return;
  }
  motor_state.last_ramp_update_micros = nowMicros;

  float elapsedSeconds = elapsedMicros / 1000000.0f;
  float targetRpm = static_cast<float>(motor_state.target_rpm);

  if (motor_state.current_rpm < targetRpm) {
    float accelRate = accelerationSettingToRate(motor_state.last_command.acceleration);
    float rpmStep = accelRate * elapsedSeconds;
    motor_state.current_rpm = min(targetRpm, motor_state.current_rpm + rpmStep);
  } else if (motor_state.current_rpm > targetRpm) {
    float decelRate = decelerationSettingToRate(motor_state.last_command.deceleration);
    float rpmStep = decelRate * elapsedSeconds;
    motor_state.current_rpm = max(targetRpm, motor_state.current_rpm - rpmStep);
  }

  // When the operator has explicitly released to a stop, do not spend time
  // crawling at a barely-moving RPM. Snap the final bit cleanly to zero.
  if (targetRpm <= 0.0f && motor_state.current_rpm <= STOP_SNAP_RPM_THRESHOLD) {
    motor_state.current_rpm = 0.0f;
  }

  recalcStepInterval();
}

void stopMotor() {
  // This is the hard stop used during boot and explicit safety-stop paths. It
  // clears both the active and pending motion state in one place.
  noTone(MOTOR1_STEP_PIN);
  digitalWrite(MOTOR1_STEP_PIN, LOW);
  digitalWrite(MOTOR1_DIR_PIN, LOW);
  motor_state.current_rpm = 0;
  motor_state.target_rpm = 0;
  motor_state.pending_target_rpm = 0;
  motor_state.stepper_enabled = false;
  motor_state.step_interval_micros = 0;
  motor_state.active_step_frequency_hz = 0;
  motor_state.tone_running = false;
  motor_state.last_ramp_update_micros = 0;
  motor_state.direction_change_pending = false;
  copyDirection(motor_state.latched_direction, DIRECTION_STOP, sizeof(motor_state.latched_direction));
  Serial.println("Motor stopped");
}

void setContactor(bool enabled) {
  // The relay output is independent of the motion engine, so it can be updated
  // immediately without affecting step pulse timing.
  digitalWrite(CONTACTOR_PIN, enabled ? HIGH : LOW);
}

// ==================== UTILITY FUNCTIONS ====================
void serviceStepper() {
  unsigned long now = micros();

  // Speed is integrated over elapsed time to avoid the visible jerk caused by
  // fixed integer RPM jumps.
  updateRampedSpeed(now);

  // Direction flips are only allowed at standstill.
  if (isEffectivelyStopped(motor_state.current_rpm) && motor_state.direction_change_pending) {
    setMotorDirection(motor_state.pending_direction);
    copyDirection(motor_state.latched_direction, motor_state.pending_direction,
                  sizeof(motor_state.latched_direction));
    motor_state.target_rpm = motor_state.pending_target_rpm;
    motor_state.direction_change_pending = false;
    if (motor_state.target_rpm > 0) {
      motor_state.stepper_enabled = true;
    }
  }
}

void blinkStatusLED(int times) {
  // LED blinking is scheduled rather than delayed so the motion engine keeps
  // running while status feedback is displayed.
  led_toggle_count_remaining = times * 2;
  led_is_on = true;
  last_led_toggle_millis = millis();
  digitalWrite(STATUS_LED_PIN, HIGH);
  led_toggle_count_remaining--;
}

void serviceStatusLED() {
  if (led_toggle_count_remaining <= 0) {
    if (led_is_on) {
      digitalWrite(STATUS_LED_PIN, LOW);
      led_is_on = false;
    }
    return;
  }

  unsigned long now = millis();
  if (now - last_led_toggle_millis < LED_BLINK_INTERVAL_MS) {
    return;
  }

  led_is_on = !led_is_on;
  digitalWrite(STATUS_LED_PIN, led_is_on ? HIGH : LOW);
  last_led_toggle_millis = now;
  led_toggle_count_remaining--;
}

void logMotorState(const MotorCommand &cmd) {
  // Serial logging is intentionally compact because the Raspberry Pi already
  // mirrors these lines into the browser-side diagnostic panel.
  Serial.print("Motor State - RPM: ");
  Serial.print(cmd.rpm);
  Serial.print(" | CurrentRPM: ");
  Serial.print(motor_state.current_rpm, 1);
  Serial.print(" | Direction: ");
  Serial.print(cmd.direction);
  Serial.print(" | StepFreqHz: ");
  Serial.print(motor_state.active_step_frequency_hz);
  Serial.print(" | Contactor: ");
  Serial.print(cmd.contactor ? "ON" : "OFF");
  Serial.print(" | Accel: ");
  Serial.print(cmd.acceleration);
  Serial.print(" | Decel: ");
  Serial.println(cmd.deceleration);
}
