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
const rpmValue = document.getElementById('rpm-value');
const accelerationValue = document.getElementById('acceleration-value');
const decelerationValue = document.getElementById('deceleration-value');

const forwardBtn = document.getElementById('forward-btn');
const stopBtn = document.getElementById('stop-btn');
const reverseBtn = document.getElementById('reverse-btn');

const statusRpm = document.getElementById('status-rpm');
const statusAccel = document.getElementById('status-accel');
const statusDecel = document.getElementById('status-decel');
const statusMotor = document.getElementById('status-motor');
const statusBlade = document.getElementById('status-blade');
const statusDirection = document.getElementById('status-direction');

const connectionIndicator = document.getElementById('connection-indicator');
const connectionText = document.getElementById('connection-text');
const lastUpdate = document.getElementById('last-update');
const videoTimestamp = document.getElementById('video-timestamp');

// Control State
let controlState = {
    rpm: 0,
    acceleration: 50,
    deceleration: 50,
    motor_enabled: false,
    blade_enabled: false,
    direction: 'stop'
};

let currentDirection = 'stop';

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
    controlState = { ...data };
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
    const command = {
        rpm: controlState.rpm,
        acceleration: controlState.acceleration,
        deceleration: controlState.deceleration,
        motor_enabled: controlState.motor_enabled,
        blade_enabled: controlState.blade_enabled,
        direction: controlState.direction
    };

    console.log('Sending motor command:', command);
    socket.emit('update_motor_control', command);
}

/**
 * Handle direction button click
 */
function selectDirection(direction, button) {
    // Remove active class from all buttons
    document.querySelectorAll('.direction-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    // Add active class to clicked button
    button.classList.add('active');

    // Update state
    currentDirection = direction;
    controlState.direction = direction;

    // If motor is not enabled or RPM is 0, still update direction but don't send command
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
    statusAccel.textContent = controlState.acceleration;
    statusDecel.textContent = controlState.deceleration;
    statusDirection.textContent = capitalizeFirstLetter(controlState.direction);
}

/**
 * Update UI elements from current state
 */
function updateUIFromState() {
    // Update sliders and values
    rpmSlider.value = controlState.rpm;
    rpmValue.textContent = controlState.rpm;

    accelerationSlider.value = controlState.acceleration;
    accelerationValue.textContent = controlState.acceleration;

    decelerationSlider.value = controlState.deceleration;
    decelerationValue.textContent = controlState.deceleration;

    // Update toggles
    motorEnableToggle.checked = controlState.motor_enabled;
    bladeEnableToggle.checked = controlState.blade_enabled;
    updateMotorStatus();
    updateBladeStatus();

    // Update direction buttons
    document.querySelectorAll('.direction-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.direction === controlState.direction) {
            btn.classList.add('active');
        }
    });
    currentDirection = controlState.direction;

    // Update status display
    updateStatusDisplay();
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
    console.log(`[${type.toUpperCase()}] ${message}`);
    // Can implement a visual notification here
}

/**
 * Update video timestamp
 */
function updateVideoTimestamp() {
    const now = new Date();
    videoTimestamp.textContent = now.toLocaleTimeString();
}

// ==================== INITIALIZATION ====================

// Initialize video timestamp
setInterval(updateVideoTimestamp, 1000);

// Initialize keyboard shortcuts (optional)
document.addEventListener('keydown', (e) => {
    // Space bar to toggle motor
    if (e.code === 'Space' && !e.target.matches('input')) {
        e.preventDefault();
        motorEnableToggle.click();
        updateMotorState();
    }

    // Arrow keys for direction (if motor is enabled)
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

// Initial setup
window.addEventListener('load', () => {
    console.log('Remote Robot Controller loaded');
    updateLastUpdate();
});

// ==================== XBOX CONTROLLER SUPPORT (Optional) ====================
/**
 * Optional: Add Xbox controller support
 * Uncomment and implement as needed
 */

/*
let gamepadIndex = null;

window.addEventListener('gamepadconnected', (e) => {
    console.log('Gamepad connected:', e.gamepad.id);
    gamepadIndex = e.gamepad.index;
});

window.addEventListener('gamepaddisconnected', (e) => {
    console.log('Gamepad disconnected');
    gamepadIndex = null;
});

function updateGamepadInput() {
    if (gamepadIndex === null) return;

    const gamepad = navigator.getGamepads()[gamepadIndex];
    if (!gamepad) return;

    // Analog stick for RPM (right stick Y-axis)
    const rpmInput = Math.abs(gamepad.axes[3]) > 0.1 ? gamepad.axes[3] : 0;
    const newRpm = Math.floor((1 - rpmInput) * 3000);
    
    if (newRpm !== controlState.rpm) {
        controlState.rpm = Math.max(0, Math.min(3000, newRpm));
        rpmSlider.value = controlState.rpm;
        rpmValue.textContent = controlState.rpm;
        updateMotorState();
    }

    // A button (0) for motor enable
    if (gamepad.buttons[0].pressed && !motorEnableToggle.checked) {
        motorEnableToggle.click();
    }

    // B button (1) for motor disable
    if (gamepad.buttons[1].pressed && motorEnableToggle.checked) {
        motorEnableToggle.click();
    }

    // X button (2) for blade toggle
    if (gamepad.buttons[2].pressed) {
        bladeEnableToggle.click();
    }

    // Dpad for direction
    if (gamepad.buttons[12].pressed) { // Dpad Up
        forwardBtn.click();
    } else if (gamepad.buttons[13].pressed) { // Dpad Down
        reverseBtn.click();
    } else if (gamepad.buttons[14].pressed || gamepad.buttons[15].pressed) { // Dpad Left/Right
        stopBtn.click();
    }
}

// Uncomment to enable gamepad polling
// setInterval(updateGamepadInput, 50);
*/
