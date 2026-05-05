/**
 * Remote Robot Lawn Mower Controller Frontend
 * Handles UI interactions and WebSocket communication
 */

// Initialize Socket.IO connection
const socket = io();

// UI Elements
const motorEnableToggle = document.getElementById('motor-enable-toggle');
const bladeEnableToggle = document.getElementById('blade-enable-toggle');
const motorEnableStatus = document.getElementById('motor-enable-status');
const bladeEnableStatus = document.getElementById('blade-enable-status');

const rpmSlider = document.getElementById('rpm-slider');
const accelerationSlider = document.getElementById('acceleration-slider');
const decelerationSlider = document.getElementById('deceleration-slider');
const maxRpmSlider = document.getElementById('max-rpm-slider');
const rpmValue = document.getElementById('rpm-value');
const accelerationValue = document.getElementById('acceleration-value');
const decelerationValue = document.getElementById('deceleration-value');
const maxRpmValue = document.getElementById('max-rpm-value');

const forwardBtn = document.getElementById('forward-btn');
const stopBtn = document.getElementById('stop-btn');
const reverseBtn = document.getElementById('reverse-btn');

const statusRpm = document.getElementById('status-rpm');
const statusMaxRpm = document.getElementById('status-max-rpm');
const statusAccel = document.getElementById('status-accel');
const statusDecel = document.getElementById('status-decel');
const statusMotor = document.getElementById('status-motor');
const statusBlade = document.getElementById('status-blade');
const statusDirection = document.getElementById('status-direction');
const statusControlMode = document.getElementById('status-control-mode');
const statusSpeedPercent = document.getElementById('status-speed-percent');
const statusLeftWheel = document.getElementById('status-left-wheel');
const statusRightWheel = document.getElementById('status-right-wheel');
const statusGamepad = document.getElementById('status-gamepad');
const gamepadStatusText = document.getElementById('gamepad-status-text');
const gamepadTriggerDebug = document.getElementById('gamepad-trigger-debug');
const statusArduinoLink = document.getElementById('status-arduino-link');
const statusArduinoComms = document.getElementById('status-arduino-comms');
const statusArduinoM1 = document.getElementById('status-arduino-m1');
const statusArduinoM2 = document.getElementById('status-arduino-m2');
const statusArduinoLastTx = document.getElementById('status-arduino-last-tx');
const statusArduinoLastRx = document.getElementById('status-arduino-last-rx');
const statusArduinoError = document.getElementById('status-arduino-error');
const arduinoCommandLog = document.getElementById('arduino-command-log');

const connectionIndicator = document.getElementById('connection-indicator');
const connectionText = document.getElementById('connection-text');
const lastUpdate = document.getElementById('last-update');
const videoTimestamp = document.getElementById('video-timestamp');

// Browser-side control state.
//
// This object mirrors the latest dashboard values and the last accepted gamepad
// interpretation. It is also the payload template used when sending commands to
// the Flask backend.
let controlState = {
    rpm: 0,
    max_rpm: 10500,
    acceleration: 50,
    deceleration: 50,
    motor_enabled: true,
    blade_enabled: false,
    direction: 'stop',
    speed_percent: 0,
    control_mode: 'manual',
    left_wheel: {
        motor_id: 1,
        rpm: 0,
        direction: 'stop'
    },
    right_wheel: {
        motor_id: 2,
        rpm: 0,
        direction: 'stop'
    }
};

let currentDirection = 'stop';
let activeGamepadIndex = null;
let lastGamepadCommand = '';
let wasGamepadConnected = false;
let arduinoLogEntries = [];
// The most recently dominant trigger direction. This is used as a small amount
// of hysteresis so trigger release noise does not briefly flip from forward to
// reverse or vice versa.
let lastTriggerDirection = 'stop';

const DEFAULT_MAX_RPM = 10500;
const TURN_DEADZONE = 0.35;
const GAMEPAD_POLL_MS = 20;
// Ignore tiny trigger values caused by controller noise near the released
// position, and require a visible margin before switching dominance.
const TRIGGER_DEADZONE = 0.05;
const TRIGGER_SWITCH_MARGIN = 0.08;

// Standard XInput-style gamepad mapping used by modern browsers.
const BTN_A = 0;
const BTN_LEFT_TRIGGER = 6;
const BTN_RIGHT_TRIGGER = 7;
const AXIS_LEFT_STICK_X = 0;
const AXIS_LEFT_TRIGGER = 2;
const AXIS_RIGHT_TRIGGER = 5;

const hasGamepadApi = typeof navigator !== 'undefined' && (
    typeof navigator.getGamepads === 'function' ||
    typeof navigator.webkitGetGamepads === 'function'
);

// ==================== SOCKET.IO EVENTS ====================

socket.on('connect', () => {
    console.log('Connected to server');
    connectionIndicator.classList.remove('disconnected');
    connectionIndicator.classList.add('connected');
    connectionText.textContent = 'Connected';
    updateLastUpdate();
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
    connectionIndicator.classList.remove('connected');
    connectionIndicator.classList.add('disconnected');
    connectionText.textContent = 'Disconnected';
});

socket.on('connection_response', (data) => {
    console.log('Server response:', data);
});

socket.on('motor_state_update', (data) => {
    console.log('Motor state updated:', data);
    const preservedMaxRpm = controlState.max_rpm || DEFAULT_MAX_RPM;
    controlState = {
        ...controlState,
        ...data,
        max_rpm: data.max_rpm ?? preservedMaxRpm
    };
    updateUIFromState();
    updateLastUpdate();
});

socket.on('error', (data) => {
    console.error('Server error:', data);
    showNotification('Error: ' + data.message, 'error');
});

socket.on('test_response', (data) => {
    console.log('Test response:', data);
});

socket.on('arduino_status_update', (data) => {
    updateArduinoStatus(data);
});

socket.on('arduino_command_log', (entry) => {
    appendArduinoLogEntry(entry);
});

socket.on('arduino_command_history', (payload) => {
    const entries = Array.isArray(payload?.entries) ? payload.entries : [];
    arduinoLogEntries = entries.slice(-60);
    renderArduinoLog();
});

// ==================== UI EVENT LISTENERS ====================

// Toggle Event Listeners
motorEnableToggle.addEventListener('change', () => {
    controlState.motor_enabled = motorEnableToggle.checked;
    updateMotorState();
    updateMotorStatus();
});

bladeEnableToggle.addEventListener('change', () => {
    controlState.blade_enabled = bladeEnableToggle.checked;
    updateMotorState();
    updateBladeStatus();
});

// Slider Event Listeners
rpmSlider.addEventListener('input', (e) => {
    controlState.rpm = parseInt(e.target.value);
    rpmValue.textContent = controlState.rpm;
    updateMotorState();
    updateStatusDisplay();
});

accelerationSlider.addEventListener('input', (e) => {
    controlState.acceleration = parseInt(e.target.value);
    accelerationValue.textContent = controlState.acceleration;
    updateMotorState();
    updateStatusDisplay();
});

decelerationSlider.addEventListener('input', (e) => {
    controlState.deceleration = parseInt(e.target.value);
    decelerationValue.textContent = controlState.deceleration;
    updateMotorState();
    updateStatusDisplay();
});

maxRpmSlider.addEventListener('input', (e) => {
    controlState.max_rpm = parseInt(e.target.value);
    maxRpmValue.textContent = controlState.max_rpm;
    updateStatusDisplay();
});

// Direction Button Event Listeners
forwardBtn.addEventListener('click', () => {
    selectDirection('forward', forwardBtn);
});

stopBtn.addEventListener('click', () => {
    selectDirection('stop', stopBtn);
});

reverseBtn.addEventListener('click', () => {
    selectDirection('reverse', reverseBtn);
});

// ==================== CONTROL FUNCTIONS ====================

/**
 * Send updated motor state to server
 */
function updateMotorState() {
    // The backend accepts both aggregate state and explicit per-wheel commands.
    // This function always sends both wheel commands so the transport format is
    // consistent regardless of whether input came from the manual UI or gamepad.
    const command = {
        rpm: controlState.rpm,
        acceleration: controlState.acceleration,
        deceleration: controlState.deceleration,
        motor_enabled: controlState.motor_enabled,
        blade_enabled: controlState.blade_enabled,
        direction: controlState.direction,
        speed_percent: controlState.speed_percent || 0,
        control_mode: controlState.control_mode || 'manual',
        motor_commands: [
            {
                motor_id: 1,
                rpm: controlState.left_wheel?.rpm || controlState.rpm,
                direction: controlState.left_wheel?.direction || controlState.direction
            },
            {
                motor_id: 2,
                rpm: controlState.right_wheel?.rpm || controlState.rpm,
                direction: controlState.right_wheel?.direction || controlState.direction
            }
        ]
    };

    console.log('Sending motor command:', command);
    socket.emit('update_motor_control', command);
}

/**
 * Handle direction button click
 */
function selectDirection(direction, button) {
    // Manual direction buttons are a legacy/fallback control path. They remain
    // useful when debugging without a controller connected.
    document.querySelectorAll('.direction-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    button.classList.add('active');

    currentDirection = direction;
    controlState.direction = direction;
    controlState.control_mode = 'manual';
    controlState.left_wheel = { motor_id: 1, rpm: controlState.rpm, direction };
    controlState.right_wheel = { motor_id: 2, rpm: controlState.rpm, direction };

    // If the user is only staging a direction change while stopped, keep the UI
    // in sync without generating an unnecessary serial command.
    if (controlState.motor_enabled && controlState.rpm > 0) {
        updateMotorState();
    } else {
        updateStatusDisplay();
    }

    updateLastUpdate();
}

/**
 * Update motor status text
 */
function updateMotorStatus() {
    motorEnableStatus.textContent = motorEnableToggle.checked ? 'Enabled' : 'Disabled';
    statusMotor.textContent = motorEnableToggle.checked ? 'Enabled' : 'Disabled';

    // Disable sliders and direction buttons if motor is disabled
    if (!motorEnableToggle.checked) {
        rpmSlider.disabled = true;
        rpmSlider.style.opacity = '0.5';
        document.querySelectorAll('.direction-btn').forEach(btn => {
            btn.disabled = true;
            btn.style.opacity = '0.5';
        });
    } else {
        rpmSlider.disabled = false;
        rpmSlider.style.opacity = '1';
        document.querySelectorAll('.direction-btn').forEach(btn => {
            btn.disabled = false;
            btn.style.opacity = '1';
        });
    }
}

/**
 * Update blade status text
 */
function updateBladeStatus() {
    bladeEnableStatus.textContent = bladeEnableToggle.checked ? 'On' : 'Off';
    statusBlade.textContent = bladeEnableToggle.checked ? 'Running' : 'Off';
}

/**
 * Update status display values
 */
function updateStatusDisplay() {
    statusRpm.textContent = controlState.rpm;
    statusMaxRpm.textContent = controlState.max_rpm || DEFAULT_MAX_RPM;
    statusAccel.textContent = controlState.acceleration;
    statusDecel.textContent = controlState.deceleration;
    statusDirection.textContent = capitalizeFirstLetter(controlState.direction);
    statusControlMode.textContent = prettyControlMode(controlState.control_mode || 'manual');
    statusSpeedPercent.textContent = `${controlState.speed_percent || 0}%`;

    const leftWheel = controlState.left_wheel || { direction: 'stop', rpm: 0 };
    const rightWheel = controlState.right_wheel || { direction: 'stop', rpm: 0 };
    statusLeftWheel.textContent = `${capitalizeFirstLetter(leftWheel.direction)} ${leftWheel.rpm}`;
    statusRightWheel.textContent = `${capitalizeFirstLetter(rightWheel.direction)} ${rightWheel.rpm}`;
}

/**
 * Update UI elements from current state
 */
function updateUIFromState() {
    // Rebuild the dashboard from the latest server state snapshot.
    rpmSlider.value = controlState.rpm;
    rpmValue.textContent = controlState.rpm;

    accelerationSlider.value = controlState.acceleration;
    accelerationValue.textContent = controlState.acceleration;

    decelerationSlider.value = controlState.deceleration;
    decelerationValue.textContent = controlState.deceleration;

    maxRpmSlider.value = controlState.max_rpm || DEFAULT_MAX_RPM;
    maxRpmValue.textContent = controlState.max_rpm || DEFAULT_MAX_RPM;

    motorEnableToggle.checked = controlState.motor_enabled;
    bladeEnableToggle.checked = controlState.blade_enabled;
    updateMotorStatus();
    updateBladeStatus();

    document.querySelectorAll('.direction-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.direction === controlState.direction) {
            btn.classList.add('active');
        }
    });
    currentDirection = controlState.direction;

    updateStatusDisplay();
}

function prettyControlMode(mode) {
    // Convert internal tokens like "gamepad_pivot_left" into readable labels.
    return mode
        .split('_')
        .map((part) => capitalizeFirstLetter(part))
        .join(' ');
}

function formatTimestamp(ts) {
    if (!ts) {
        return 'Never';
    }

    const date = new Date(ts);
    if (Number.isNaN(date.getTime())) {
        return ts;
    }

    return date.toLocaleTimeString();
}

function updateArduinoStatus(status) {
    // The backend already normalizes the serial health snapshot, so the browser
    // only needs to map booleans/timestamps to readable text.
    statusArduinoLink.textContent = status.connected ? 'Connected' : 'Disconnected';
    statusArduinoComms.textContent = status.communication_ok ? 'Active' : 'Idle';
    statusArduinoM1.textContent = status.motor1_connected ? 'Online' : 'Offline';
    statusArduinoM2.textContent = status.motor2_connected ? 'Online' : 'Offline';
    statusArduinoLastTx.textContent = `Last TX: ${formatTimestamp(status.last_tx)}`;
    statusArduinoLastRx.textContent = `Last RX: ${formatTimestamp(status.last_rx)}`;
    statusArduinoError.textContent = `Last Error: ${status.last_error || 'None'}`;
}

function buildArduinoLogLine(entry) {
    const timeText = formatTimestamp(entry.timestamp);
    if (entry.type === 'tx') {
        return `${timeText} TX M${entry.motor_id} rpm=${entry.rpm} dir=${entry.direction} blade=${entry.contactor ? 'on' : 'off'} src=${entry.source || 'unknown'}`;
    }

    if (entry.type === 'rx') {
        return `${timeText} RX M${entry.motor_id} ${entry.message || ''}`;
    }

    return `${timeText} ${String(entry.message || 'Status update')}`;
}

function renderArduinoLog() {
    // Re-render the compact rolling log whenever a history snapshot arrives or
    // a single live entry is appended.
    arduinoCommandLog.innerHTML = '';

    if (arduinoLogEntries.length === 0) {
        const empty = document.createElement('li');
        empty.textContent = 'No Arduino messages yet.';
        arduinoCommandLog.appendChild(empty);
        return;
    }

    arduinoLogEntries.slice(-60).forEach((entry) => {
        const item = document.createElement('li');
        item.textContent = buildArduinoLogLine(entry);

        if (entry.type === 'tx') {
            item.classList.add('log-tx');
        } else if (entry.type === 'rx') {
            item.classList.add('log-rx');
        } else if (entry.type === 'error') {
            item.classList.add('log-error');
        }

        arduinoCommandLog.appendChild(item);
    });

    arduinoCommandLog.scrollTop = arduinoCommandLog.scrollHeight;
}

function appendArduinoLogEntry(entry) {
    arduinoLogEntries.push(entry);
    if (arduinoLogEntries.length > 60) {
        arduinoLogEntries = arduinoLogEntries.slice(-60);
    }
    renderArduinoLog();
}

function axisToPercent(axisValue) {
    // Some browsers expose triggers as axes instead of buttons. Convert the
    // usual -1..1 range into the same 0..1 range used for button values.
    const normalized = (axisValue + 1) / 2;
    return Math.max(0, Math.min(1, normalized));
}

function triggerToPercent(gamepad, triggerButtonIndex, triggerAxisIndex) {
    const triggerButton = gamepad.buttons?.[triggerButtonIndex];

    // Standard mapping exposes LT/RT as analog buttons with value 0..1.
    if (triggerButton && typeof triggerButton.value === 'number') {
        return Math.max(0, Math.min(1, triggerButton.value));
    }

    // Fall back to axis-based triggers for older browser/controller mappings.
    return axisToPercent(gamepad.axes?.[triggerAxisIndex] ?? -1);
}

function getGamepadsSnapshot() {
    // Grab a filtered snapshot rather than relying solely on connect/disconnect
    // events because browser gamepad events are inconsistent across platforms.
    const getPads = navigator.getGamepads || navigator.webkitGetGamepads;
    if (!getPads) {
        return [];
    }

    const rawPads = getPads.call(navigator) || [];
    const pads = [];
    for (let i = 0; i < rawPads.length; i++) {
        if (rawPads[i]) {
            pads.push(rawPads[i]);
        }
    }

    return pads;
}

function findActiveGamepad() {
    const pads = getGamepadsSnapshot();

    if (activeGamepadIndex !== null) {
        for (let i = 0; i < pads.length; i++) {
            if (pads[i].index === activeGamepadIndex) {
                return pads[i];
            }
        }
    }

    if (pads.length > 0) {
        activeGamepadIndex = pads[0].index;
        return pads[0];
    }

    activeGamepadIndex = null;
    return null;
}

function setGamepadConnected(isConnected, gamepadName = '') {
    if (isConnected) {
        const text = `Gamepad: Connected (${gamepadName || 'XBOX Controller'})`;
        gamepadStatusText.textContent = text;
        statusGamepad.textContent = 'Connected';
    } else {
        gamepadStatusText.textContent = hasGamepadApi
            ? 'Gamepad: Not connected (press any controller button after plugging in)'
            : 'Gamepad: Browser does not support Gamepad API';
        statusGamepad.textContent = 'Disconnected';
    }
}

function updateGamepadDebug(leftTrigger = 0, rightTrigger = 0, turnAxis = 0) {
    gamepadTriggerDebug.textContent = `LT: ${leftTrigger.toFixed(2)} | RT: ${rightTrigger.toFixed(2)} | Turn X: ${turnAxis.toFixed(2)}`;
}

function monitorGamepadConnection() {
    // Continuously refresh connection text so controllers that appear only after
    // the first button press still become visible in the UI.
    const gamepad = findActiveGamepad();
    if (gamepad) {
        setGamepadConnected(true, gamepad.id);
    } else {
        setGamepadConnected(false);
    }

    window.requestAnimationFrame(monitorGamepadConnection);
}

function applyGamepadControl() {
    const gamepad = findActiveGamepad();
    if (!gamepad) {
        if (wasGamepadConnected && controlState.motor_enabled) {
            // A disappearing controller should behave like a safety stop rather
            // than leaving the last movement command latched in the backend.
            controlState.control_mode = 'gamepad_disconnected';
            controlState.speed_percent = 0;
            controlState.rpm = 0;
            controlState.blade_enabled = false;
            controlState.direction = 'stop';
            controlState.left_wheel = { motor_id: 1, rpm: 0, direction: 'stop' };
            controlState.right_wheel = { motor_id: 2, rpm: 0, direction: 'stop' };
            bladeEnableToggle.checked = false;
            updateMotorState();
            updateBladeStatus();
            updateStatusDisplay();
            updateLastUpdate();
        }
        wasGamepadConnected = false;
        lastTriggerDirection = 'stop';
        setGamepadConnected(false);
        updateGamepadDebug(0, 0, 0);
        return;
    }

    wasGamepadConnected = true;
    setGamepadConnected(true, gamepad.id);

    if (!motorEnableToggle.checked) {
        // The gamepad should never bypass the explicit motor-enable toggle.
        return;
    }

    const aPressed = !!gamepad.buttons[BTN_A]?.pressed;

    const rightTrigger = triggerToPercent(gamepad, BTN_RIGHT_TRIGGER, AXIS_RIGHT_TRIGGER);
    const leftTrigger = triggerToPercent(gamepad, BTN_LEFT_TRIGGER, AXIS_LEFT_TRIGGER);
    const turnAxis = gamepad.axes[AXIS_LEFT_STICK_X] ?? 0;
    updateGamepadDebug(leftTrigger, rightTrigger, turnAxis);

    // Decide which trigger currently "owns" throttle. Hysteresis keeps the
    // direction stable while one trigger is being released.
    let driveDirection = 'stop';
    let activeTriggerValue = 0;

    if (rightTrigger < TRIGGER_DEADZONE && leftTrigger < TRIGGER_DEADZONE) {
        lastTriggerDirection = 'stop';
    } else if (lastTriggerDirection === 'forward') {
        if (leftTrigger > rightTrigger + TRIGGER_SWITCH_MARGIN && leftTrigger >= TRIGGER_DEADZONE) {
            driveDirection = 'reverse';
            activeTriggerValue = leftTrigger;
            lastTriggerDirection = 'reverse';
        } else {
            driveDirection = 'forward';
            activeTriggerValue = rightTrigger;
        }
    } else if (lastTriggerDirection === 'reverse') {
        if (rightTrigger > leftTrigger + TRIGGER_SWITCH_MARGIN && rightTrigger >= TRIGGER_DEADZONE) {
            driveDirection = 'forward';
            activeTriggerValue = rightTrigger;
            lastTriggerDirection = 'forward';
        } else {
            driveDirection = 'reverse';
            activeTriggerValue = leftTrigger;
        }
    } else if (rightTrigger >= leftTrigger) {
        driveDirection = 'forward';
        activeTriggerValue = rightTrigger;
        lastTriggerDirection = 'forward';
    } else {
        driveDirection = 'reverse';
        activeTriggerValue = leftTrigger;
        lastTriggerDirection = 'reverse';
    }

    // The trigger value is expressed as a percentage for the UI, then mapped to
    // the configured gamepad max RPM for the backend command.
    const speedPercent = Math.round(activeTriggerValue * 100);
    const maxRpm = controlState.max_rpm || DEFAULT_MAX_RPM;
    const rpm = Math.round((speedPercent / 100) * maxRpm);

    let leftDirection = 'stop';
    let rightDirection = 'stop';
    let mode = 'gamepad_stop';

    if (rpm > 0 && Math.abs(turnAxis) >= TURN_DEADZONE) {
        // Pivot mode deliberately drives the wheels in opposite directions.
        // That matches a skid-steer style rotation in place.
        if (turnAxis > 0) {
            leftDirection = 'forward';
            rightDirection = 'reverse';
            mode = 'gamepad_pivot_right';
        } else {
            leftDirection = 'reverse';
            rightDirection = 'forward';
            mode = 'gamepad_pivot_left';
        }
    } else if (rpm > 0 && driveDirection === 'forward') {
        leftDirection = 'forward';
        rightDirection = 'forward';
        mode = 'gamepad_forward';
    } else if (rpm > 0 && driveDirection === 'reverse') {
        leftDirection = 'reverse';
        rightDirection = 'reverse';
        mode = 'gamepad_reverse';
    }

    controlState.control_mode = mode;
    controlState.speed_percent = speedPercent;
    controlState.rpm = rpm;
    controlState.blade_enabled = aPressed;
    controlState.direction = (leftDirection === rightDirection) ? leftDirection : 'mixed';
    controlState.left_wheel = { motor_id: 1, rpm: rpm, direction: leftDirection };
    controlState.right_wheel = { motor_id: 2, rpm: rpm, direction: rightDirection };

    // The blade UI is still rendered as a toggle, but gamepad A behaves as a
    // hold-to-run input. Keep the visual toggle synchronized with that state.
    bladeEnableToggle.checked = controlState.blade_enabled;

    const gamepadSignature = JSON.stringify({
        motor_enabled: controlState.motor_enabled,
        blade_enabled: controlState.blade_enabled,
        speed_percent: controlState.speed_percent,
        control_mode: controlState.control_mode,
        left_wheel: controlState.left_wheel,
        right_wheel: controlState.right_wheel,
        acceleration: controlState.acceleration,
        deceleration: controlState.deceleration
    });

    if (gamepadSignature !== lastGamepadCommand) {
        lastGamepadCommand = gamepadSignature;
        updateMotorState();
        updateBladeStatus();
        updateStatusDisplay();
        updateLastUpdate();
    }
}

/**
 * Update last update timestamp
 */
function updateLastUpdate() {
    const now = new Date();
    lastUpdate.textContent = `Last update: ${now.toLocaleTimeString()}`;
}

/**
 * Capitalize first letter of string
 */
function capitalizeFirstLetter(string) {
    return string.charAt(0).toUpperCase() + string.slice(1);
}

/**
 * Show notification (optional implementation)
 */
function showNotification(message, type = 'info') {
    // Notifications are currently logged only. This helper exists so a visual
    // toast implementation can be dropped in without changing call sites.
    console.log(`[${type.toUpperCase()}] ${message}`);
}

/**
 * Update video timestamp
 */
function updateVideoTimestamp() {
    const now = new Date();
    videoTimestamp.textContent = now.toLocaleTimeString();
}

// ==================== INITIALIZATION ====================

// Run the live UI loops once the script loads.
setInterval(updateVideoTimestamp, 1000);
setInterval(applyGamepadControl, GAMEPAD_POLL_MS);
window.requestAnimationFrame(monitorGamepadConnection);

window.addEventListener('gamepadconnected', (event) => {
    activeGamepadIndex = event.gamepad.index;
    setGamepadConnected(true, event.gamepad.id);
    console.log('Gamepad connected:', event.gamepad.id);
});

window.addEventListener('gamepaddisconnected', (event) => {
    if (activeGamepadIndex === event.gamepad.index) {
        activeGamepadIndex = null;
        lastGamepadCommand = '';
    }
    wasGamepadConnected = false;

    if (controlState.motor_enabled) {
        controlState.control_mode = 'gamepad_disconnected';
        controlState.speed_percent = 0;
        controlState.rpm = 0;
        controlState.blade_enabled = false;
        controlState.direction = 'stop';
        controlState.left_wheel = { motor_id: 1, rpm: 0, direction: 'stop' };
        controlState.right_wheel = { motor_id: 2, rpm: 0, direction: 'stop' };
        bladeEnableToggle.checked = false;
        updateMotorState();
        updateBladeStatus();
        updateStatusDisplay();
        updateLastUpdate();
    }

    setGamepadConnected(false);
    console.log('Gamepad disconnected:', event.gamepad.id);
});

// Keyboard controls exist primarily as a fallback when debugging on a desktop.
document.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && !e.target.matches('input')) {
        e.preventDefault();
        motorEnableToggle.click();
        updateMotorState();
    }

    if (controlState.motor_enabled) {
        if (e.code === 'ArrowUp') {
            forwardBtn.click();
        } else if (e.code === 'ArrowDown') {
            reverseBtn.click();
        } else if (e.code === 'ArrowLeft' || e.code === 'ArrowRight') {
            stopBtn.click();
        }
    }
});

// Build the initial static UI before the first server or gamepad event arrives.
window.addEventListener('load', () => {
    console.log('Remote Robot Controller loaded');
    updateLastUpdate();
    renderArduinoLog();
});
