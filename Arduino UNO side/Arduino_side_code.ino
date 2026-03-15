#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ==============================================================================
// HARDWARE INITIALIZATION
// ==============================================================================
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

// --- I2C Servo Channels (PCA9685) ---
#define SHOULDER_LEFT   0
#define ELBOW_LEFT      3
#define BASE_LEFT       7
#define BASE_RIGHT      8
#define ELBOW_RIGHT    12
#define SHOULDER_RIGHT 15

// --- TB6612 Motor Driver Pins ---
#define PWMA 9
#define PWMB 10
#define INA1 7
#define INA2 8
#define INB1 4
#define INB2 5
#define STBY 6

// --- Sensors & Status Pins ---
const int FRONT_TRIG = 12;
const int FRONT_ECHO = 11;
const int BACK_TRIG  = A2;
const int BACK_ECHO  = A3;
const int STATUS_LED = 2;

// ==============================================================================
// STATE & TUNING VARIABLES
// ==============================================================================
const float STOP_DISTANCE = 10.0; // Distance in cm to trigger hardware reflex

int8_t currentSpdLeft = 0;
int8_t currentSpdRight = 0;

unsigned long lastSensorCheck = 0;
unsigned long lastAvoidSignal = 0;
unsigned long lastCmdTime = 0;

// LED Pulse state tracking
unsigned long ledTimer = 0;
bool ledIsOn = false;
bool reflexTriggered = false;

// ==============================================================================
// MAIN SETUP
// ==============================================================================
void setup() {
  Serial.begin(115200);

  // --- Initialize Motor Pins ---
  pinMode(PWMA, OUTPUT);
  pinMode(PWMB, OUTPUT);
  pinMode(INA1, OUTPUT);
  pinMode(INA2, OUTPUT);
  pinMode(INB1, OUTPUT);
  pinMode(INB2, OUTPUT);
  pinMode(STBY, OUTPUT);

  // --- Initialize Sensor Pins ---
  pinMode(FRONT_TRIG, OUTPUT);
  pinMode(FRONT_ECHO, INPUT);
  pinMode(BACK_TRIG,  OUTPUT);
  pinMode(BACK_ECHO,  INPUT);

  // --- Initialize Status LED ---
  pinMode(STATUS_LED, OUTPUT);
  digitalWrite(STATUS_LED, LOW);
  
  // Enable the TB6612 Motor Driver
  digitalWrite(STBY, HIGH);

  // --- Initialize Servo Shield ---
  pwm.begin();
  pwm.setPWMFreq(50); // 50Hz is standard for SG90 Analog Servos
  
  // Ensure everything starts in a safe, dead-stop state
  emergencyStop();
}

// ==============================================================================
// MAIN LOOP
// ==============================================================================
void loop() {
  // 1. Hardware Reflex Check (Runs every 100ms)
  if (millis() - lastSensorCheck > 100) {
    checkSafety();
    lastSensorCheck = millis();
  }

  // 2. Process Incoming Serial Commands from Pi Zero
  if (Serial.available() > 0) {
    lastCmdTime = millis(); // Reset the communications watchdog timer
    
    char cmd = Serial.read();
    if (cmd == 'S') {
      handleServo();
    } 
    else if (cmd == 'M') {
      handleMotor();
    } 
    else if (cmd == 'R') {
      handleRelease();
    } 
    else if (cmd == 'X') {
      emergencyStop();
    }
  }

  // 3. Update the heartbeat LED (Non-blocking)
  updateStatusLED();
}

// ==============================================================================
// NON-BLOCKING LED HEARTBEAT
// ==============================================================================
void updateStatusLED() {
  unsigned long currentMillis = millis();
  int onDuration = 0;
  int offDuration = 0;

  // Watchdog check: Have we heard from the Pi in the last 3 seconds?
  bool piConnected = (currentMillis - lastCmdTime) < 3000;

  // Set the LED pulsing rhythm based on the current robot state
  if (reflexTriggered) {
    // STATE: Emergency Avoidance (Fast Strobe)
    onDuration = 100;
    offDuration = 100;
  } 
  else if (!piConnected) {
    // STATE: Booting / Pi Disconnected (Slow, even pulse)
    onDuration = 1000;
    offDuration = 1000;
  } 
  else if (currentSpdLeft != 0 || currentSpdRight != 0) {
    // STATE: Driving normally (Medium pulse)
    onDuration = 300;
    offDuration = 300;
  } 
  else {
    // STATE: Idle / Connected (Short calm blip every 2 seconds)
    onDuration = 50;
    offDuration = 2000;
  }

  // Toggle the LED state based on the calculated durations
  if (currentMillis - ledTimer >= (ledIsOn ? onDuration : offDuration)) {
    ledTimer = currentMillis;
    ledIsOn = !ledIsOn;
    digitalWrite(STATUS_LED, ledIsOn ? HIGH : LOW);
  }
}

// ==============================================================================
// SENSOR & SAFETY REFLEX LOGIC
// ==============================================================================
float getDistance(int trig, int echo) {
  /* Fires an acoustic ping and calculates the distance in cm */
  digitalWrite(trig, LOW);
  delayMicroseconds(2);
  
  digitalWrite(trig, HIGH);
  delayMicroseconds(10); // 10us pulse triggers the HC-SR04
  
  digitalWrite(trig, LOW);
  
  // Wait up to 15ms for the echo (limits range to ~250cm, speeds up the loop)
  long duration = pulseIn(echo, HIGH, 15000);
  
  if (duration == 0) {
    return 999.0; // Timeout / No obstacle
  }
  
  return (duration * 0.0343) / 2.0;
}

void forceStop(String source) {
  /* Instantly cuts motor power and alerts the Pi to take evasive action */
  setMotor(0, 0);
  currentSpdLeft = 0;
  currentSpdRight = 0;
  reflexTriggered = true;
  
  // Only spam the Serial port every 1.5 seconds to prevent buffer overflow
  if (millis() - lastAvoidSignal > 1500) {
    Serial.print("!AVOID:");
    Serial.println(source);
    lastAvoidSignal = millis();
  }
}

void checkSafety() {
  /* * THE FOUNDATIONAL RULE:
   * Positive math commands from the Pi mathematically mean "Go Forward" ill explain why later, tho its common practice.
   * Therefore, if speeds are > 0, we must check the FRONT ultrasonic sensor.
   */
  if (currentSpdLeft > 0 || currentSpdRight > 0) {
    if (getDistance(FRONT_TRIG, FRONT_ECHO) <= STOP_DISTANCE) {
      forceStop("FRONT");
    }
  } 
  else if (currentSpdLeft < 0 || currentSpdRight < 0) {
    if (getDistance(BACK_TRIG, BACK_ECHO) <= STOP_DISTANCE) {
      forceStop("BACK");
    }
  }
}

// ==============================================================================
// SERIAL COMMAND PARSERS
// ==============================================================================
bool waitForBytes(int numBytes) {
  /* Prevents the Arduino from freezing if the Pi drops a serial packet */
  unsigned long startWait = millis();
  while (Serial.available() < numBytes) {
    // 10ms timeout
    if (millis() - startWait > 10) {
      return false;
    }
  }
  return true;
}

void handleMotor() {
  /* Protocol: 'M' [LeftSpeed] [RightSpeed] */
  if (!waitForBytes(2)) {
    return;
  }
  
  currentSpdLeft  = Serial.read();
  currentSpdRight = Serial.read();
  reflexTriggered = false; // Reset the reflex state once a new valid command arrives
  
  setMotor(currentSpdLeft, currentSpdRight);
}

void handleServo() {
  /* Protocol: 'S' [Channel] [PWM_HighByte] [PWM_LowByte] */
  if (!waitForBytes(3)) {
    return;
  }
  
  uint8_t ch = Serial.read();
  uint16_t pwmVal = (Serial.read() << 8) | Serial.read();
  
  pwm.setPWM(ch, 0, pwmVal);
}

void handleRelease() {
  /* Protocol: 'R' [Channel] -> Cuts PWM signal to relax the servo and stop jitter */
  if (!waitForBytes(1)) {
    return;
  }
  
  uint8_t ch = Serial.read();
  pwm.setPWM(ch, 0, 0);
}

void emergencyStop() {
  /* The absolute panic button. Kills all motors and relaxes all servos. */
  currentSpdLeft = 0;
  currentSpdRight = 0;
  reflexTriggered = false;
  
  setMotor(0, 0);
  
  // Physically pull all motor logic pins LOW
  digitalWrite(INA1, LOW);
  digitalWrite(INA2, LOW);
  digitalWrite(INB1, LOW);
  digitalWrite(INB2, LOW);
  
  // Cut power to all 16 channels on the Servo Shield
  for (int i = 0; i < 16; i++) {
    pwm.setPWM(i, 0, 0);
  }
}

// ==============================================================================
// LOW-LEVEL MOTOR DRIVER CONTROL
// ==============================================================================
void setMotor(int left, int right) {
  setSingle(left, INA1, INA2, PWMA);
  setSingle(right, INB1, INB2, PWMB);
}

void setSingle(int spd, int in1, int in2, int pwmPin) {
  /* * THE SECRET SAUCE:
   * Because my physical DC motors are wired backwards, this function intercepts
   * the math. When the Pi sends a Positive number (+127), this logic cleanly
   * inverts the physical IN1/IN2 pins under the hood, making the tracks spin
   * physically forward, all without having to mess up the math logic above or breaking apart my small robot and changing the wires :' )
   */
  if (spd == 0) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
    analogWrite(pwmPin, 0);
    return;
  }
  
  // The logic inversion:
  digitalWrite(in1, spd < 0); 
  digitalWrite(in2, spd > 0); 
  
  // Send the absolute speed value to the PWM pin
  analogWrite(pwmPin, abs(spd));
}
