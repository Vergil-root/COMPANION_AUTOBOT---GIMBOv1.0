import serial
import time
import logging
from brain_enums import Event, EventType

class MotionEngine:
    """
    Handles all physical movement for the robot. 
    Communicates with the Arduino over Serial to drive DC motors and I2C PCA9685 servos.
    """
    def __init__(self, port='/dev/arduino_uno', baud=115200, event_queue=None):
        self.event_queue = event_queue

        # --- Servo Channel Assignments ---
        self.SHOULDER_LEFT = 0
        self.ELBOW_LEFT = 3
        self.BASE_LEFT = 7
        
        self.BASE_RIGHT = 8
        self.ELBOW_RIGHT = 12
        self.SHOULDER_RIGHT = 15

        # --- Calibration Data ---
        # Format: channel: (angle_min, angle_max, pwm_min, pwm_max)
        self.CAL = {
            0:  (10, 125, 190, 400), 
            7:  (20, 170, 105, 540), 
            3:  (34, 170, 180, 515),
            15: (10, 125, 520, 260), 
            8:  (20, 170, 540, 105), 
            12: (34, 170, 500, 200),
        }
        
        # Default resting angles for each servo
        self.REST_POS = {
            0: 45, 
            15: 45, 
            7: 86, 
            8: 110, 
            3: 170, 
            12: 170
        }

        # --- State Variables ---
        self.ser = None
        self.serial_buffer = ""
        
        self.motion_queue = []
        self.active_frame = None
        self.current_frame_end = 0
        
        self.motor_state = {
            "current_l": 0, 
            "current_r": 0, 
            "target_l": 0, 
            "target_r": 0, 
            "speed": 100
        }

        self.servo = {}
        self.last_servo_tx_time = 0
        self.last_sent_pwm = {ch: -1 for ch in self.CAL.keys()}

        # --- Initialize Serial Connection ---
        try:
            self.ser = serial.Serial(port, baud, timeout=0)
            time.sleep(2.0)  # Give the Arduino time to reset
            logging.info("PERIPHERAL: Motion Engine & Arduino Online.")
        except Exception as e:
            logging.error(f"MOTION FUSE: Arduino not found on {port}. Error: {e}")

        # --- Initialize Servo States ---
        for ch, (amin, amax, pmin, pmax) in self.CAL.items():
            init_angle = self.REST_POS.get(ch, amin)
            self.servo[ch] = {
                "pos": init_angle, 
                "start": init_angle, 
                "target": init_angle,
                "t0": time.monotonic(), 
                "dur": 1.0, 
                "amin": amin, 
                "amax": amax,
                "pmin": pmin, 
                "pmax": pmax, 
                "moving": False
            }

    # ================= MATH HELPERS =================
    
    def map_range(self, x, a, b, c, d):
        """Maps a value 'x' from range a-b to range c-d."""
        if a == b: 
            return c
        return int((float(x) - a) * (d - c) / (b - a) + c)

    def smoothstep(self, t):
        """Creates a smooth acceleration/deceleration curve (Ease In/Out)."""
        return t * t * (3 - 2 * t)

    # ================= DRIVE COMMANDS =================

    def drive_robot(self, left, right):
        """Formats the raw motor speeds into a byte array for the Arduino."""
        l = max(-127, min(127, int(left)))
        r = max(-127, min(127, int(right)))
        return bytearray([ord('M'), l & 0xFF, r & 0xFF])

    def set_drive_mode(self, mode, speed=None):
        """Sets the target motor speeds based on the requested direction."""
        if speed is not None:
            self.motor_state["speed"] = speed

        s = self.motor_state["speed"]

        # EXACT ORIGINAL LOGIC: Positive speed mathematically means Forward.
        if mode == "forward":
            self.motor_state["target_l"] = s
            self.motor_state["target_r"] = s
        elif mode == "backward":
            self.motor_state["target_l"] = -s
            self.motor_state["target_r"] = -s
        elif mode == "left":
            self.motor_state["target_l"] = -s
            self.motor_state["target_r"] = s
        elif mode == "right":
            self.motor_state["target_l"] = s
            self.motor_state["target_r"] = -s
        else:
            self.motor_state["target_l"] = 0
            self.motor_state["target_r"] = 0

    def load_expression(self, frames):
        """Loads a sequence of servo movements (an animation) into the queue."""
        self.motion_queue = list(frames)
        self.active_frame = None

    def emergency_stop(self):
        """Instantly kills all motor power and sends a hardware stop command."""
        self.set_drive_mode("stop")
        self.motor_state["current_l"] = 0
        self.motor_state["current_r"] = 0
        
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(b'X')
            except serial.SerialException:
                pass

    # ================= MAIN UPDATE LOOP =================

    def update(self):
        """
        The main heartbeat of the Motion Engine. 
        Must be called continuously to process serial data and glide servos.
        """
        now = time.monotonic()
        tx_payload = bytearray()

        # ---------------------------------------------------------
        # 1. Read Incoming Serial Data (Check for Reflexes)
        # ---------------------------------------------------------
        if self.ser and self.ser.in_waiting > 0:
            try:
                raw_data = self.ser.read(self.ser.in_waiting).decode('utf-8', errors='ignore')
                self.serial_buffer += raw_data

                while '\n' in self.serial_buffer:
                    line, self.serial_buffer = self.serial_buffer.split('\n', 1)
                    line = line.strip()
                    
                    # PI AVOIDANCE HANDOFF: Catches the hardware trigger from Arduino
                    if "!AVOID:" in line:
                        source = line.split(":", 1)[1]
                        logging.warning(f"MOTION: Hardware Avoidance Triggered by {source}!")
                        self.emergency_stop()
                        
                        if self.event_queue:
                            self.event_queue.put(Event(type=EventType.OBSTACLE, data=source))
                            
            except serial.SerialException as e:
                logging.error(f"MOTION COMMS DROP: {e}")
                self.ser = None

        # ---------------------------------------------------------
        # 2. Update DC Motors
        # ---------------------------------------------------------
        if (self.motor_state["current_l"] != self.motor_state["target_l"] or
            self.motor_state["current_r"] != self.motor_state["target_r"]):
            
            self.motor_state["current_l"] = self.motor_state["target_l"]
            self.motor_state["current_r"] = self.motor_state["target_r"]
            
            tx_payload.extend(self.drive_robot(self.motor_state["current_l"], self.motor_state["current_r"]))

        # ---------------------------------------------------------
        # 3. Load the Next Servo Animation Frame
        # ---------------------------------------------------------
        if self.active_frame is None and self.motion_queue:
            duration, joints = self.motion_queue.pop(0)
            self.active_frame = (duration, joints)
            self.current_frame_end = now + duration
            
            for ch, angles in joints.items():
                s = self.servo[ch]
                frm, to = (angles if isinstance(angles, tuple) else (s["pos"], angles))
                
                s["start"] = frm
                s["pos"] = frm
                s["target"] = to
                s["t0"] = now
                s["dur"] = max(0.05, duration)
                s["moving"] = True

        # Clear the active frame if it has finished playing
        if self.active_frame and now >= self.current_frame_end:
            self.active_frame = None

        # ---------------------------------------------------------
        # 4. Calculate and Send Servo PWM Updates (25Hz / 40ms)
        # ---------------------------------------------------------
        if now - self.last_servo_tx_time >= 0.04:
            self.last_servo_tx_time = now
            
            for ch, s in self.servo.items():
                if not s["moving"]: 
                    continue

                t = (now - s["t0"]) / s["dur"]
                
                # If the movement is complete
                if t >= 1.0:
                    s["pos"] = s["target"]
                    s["moving"] = False
                    
                    pwm = self.map_range(s["pos"], s["amin"], s["amax"], s["pmin"], s["pmax"])
                    tx_payload.extend([ord('S'), ch, (pwm >> 8) & 0xFF, pwm & 0xFF])
                    tx_payload.extend([ord('R'), ch]) # Send release command to relax servo
                
                # If the movement is still in progress (Interpolating)
                else:
                    s["pos"] = s["start"] + self.smoothstep(t) * (s["target"] - s["start"])
                    pwm = self.map_range(s["pos"], s["amin"], s["amax"], s["pmin"], s["pmax"])
                    
                    # Clamp the PWM to absolute safe limits
                    min_p, max_p = min(s["pmin"], s["pmax"]), max(s["pmin"], s["pmax"])
                    pwm = int(max(min_p, min(max_p, pwm)))

                    # Only send data if the PWM actually changed to save serial bandwidth
                    if pwm != self.last_sent_pwm[ch]:
                        tx_payload.extend([ord('S'), ch, (pwm >> 8) & 0xFF, pwm & 0xFF])
                        self.last_sent_pwm[ch] = pwm

        # ---------------------------------------------------------
        # 5. Transmit Everything to Arduino
        # ---------------------------------------------------------
        if tx_payload and self.ser and self.ser.is_open:
            try:
                self.ser.write(tx_payload)
            except serial.SerialException:
                pass
