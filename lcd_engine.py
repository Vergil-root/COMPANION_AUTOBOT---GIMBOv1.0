from RPLCD.i2c import CharLCD
import time
import threading
import random
import logging

class LCDEngine:
    """
    Handles the 16x2 I2C Character Display.
    Multiplexes custom 5x8 pixel characters to create animated, 
    expressive faces that run on a non-blocking background thread.
    """
    def __init__(self):
        self.lcd = None
        self.running = True
        
        # State tracking for animations
        self.current_animation = "IDLE"
        self._active_animation = "IDLE" 
        
        # Thread lock to prevent I2C bus collisions
        self.lock = threading.Lock()

        # --- Hardware Setup ---
        try:
            self.lcd = CharLCD(
                i2c_expander='PCF8574',
                address=0x27,
                port=1,
                cols=16,
                rows=2,
                charmap='A02',
                auto_linebreaks=False
            )
            self._setup_custom_chars()
            logging.info("PERIPHERAL: LCD Engine Initialized on I2C.")
        except Exception as e:
            logging.error(f"LCD Error: {e}. Ensure I2C is enabled and address is correct.")

        # --- Start Background Animation Thread ---
        self.anim_thread = threading.Thread(target=self._animation_loop, daemon=True)
        self.anim_thread.start()

    def _setup_custom_chars(self):
        """
        Loads custom 5x8 pixel character maps into the LCD's CGRAM.
        These are the building blocks for the robot's facial expressions.
        """
        if not self.lcd:
            return
            
        chars = {
            0: [0, 0, 0, 0, 2, 1, 0, 0],          # Left Smile Edge
            1: [0, 0, 0, 0, 8, 16, 0, 0],         # Right Smile Edge
            2: [0, 10, 21, 0, 16, 16, 16, 0],     # Tilde / Sad brow
            3: [0, 16, 8, 4, 2, 1, 0, 0],         # Slash
            4: [0, 31, 0, 0, 0, 0, 0, 0],         # Upper lip / Flat mouth
            5: [14, 17, 1, 6, 1, 17, 14, 0],      # Cute '3' Mouth
            6: [0, 14, 21, 21, 14, 0, 0, 0],      # Filled Eye pupil
            7: [4, 14, 31, 0, 0, 0, 0, 0]         # Happy Eye arc
        }
        
        for slot, definition in chars.items():
            self.lcd.create_char(slot, definition)

    def set_animation(self, name):
        """
        Called by the Brain to instantly request a new face animation.
        Thread-safe state update.
        """
        with self.lock:
            if self.current_animation != name:
                self.current_animation = name

    def _write(self, eyes, mouth, thought=""):
        """
        Safely writes a specific frame to the physical I2C display.
        Catches dropped packets (common on Pi Zero) without crashing.
        """
        if not self.lcd:
            return
            
        try:
            with self.lock:
                self.lcd.clear()
                
                # Top Row: Eyes
                self.lcd.cursor_pos = (0, 0)
                self.lcd.write_string(eyes[:8])
                
                # Bottom Row: Mouth
                self.lcd.cursor_pos = (1, 1)
                self.lcd.write_string(mouth[:6])
                
                # Top Row (Right Side): Current Thought/Status
                if thought:
                    self.lcd.cursor_pos = (0, 8)
                    self.lcd.write_string(thought[:8])
                    
        except IOError:
            # Silently ignore dropped I2C packets to prevent loop crashing
            pass

    def _play_sequence(self, frames):
        """
        Plays a list of frames sequentially. 
        Will instantly abort if a new animation is requested by the Brain.
        """
        self._active_animation = self.current_animation
        
        for eyes, mouth, thought, duration in frames:
            # Abort if the animation state changed mid-sequence
            if self.current_animation != self._active_animation:
                break
                
            self._write(eyes, mouth, thought)
            
            # Wait for the duration of the frame, checking for interrupts
            elapsed = 0
            while elapsed < duration:
                if self.current_animation != self._active_animation:
                    break
                time.sleep(0.05)
                elapsed += 0.05

    def _animation_loop(self):
        """
        The core background loop. 
        Continuously generates frames based on the current requested animation.
        """
        while self.running:
            anim = self.current_animation

            # --- Pre-calculate custom character strings ---
            c_mouth_smile = chr(0) + "__" + chr(1)
            c_mouth_cute  = "-" + chr(5) + "-"
            c_mouth_sad   = chr(1) + "--" + chr(0)
            c_mouth_flat  = "____"
            c_eye_pupil   = chr(6)
            c_eye_happy   = chr(7)

            # --- Animation Libraries ---
            if anim == "IDLE":
                seq = [
                    (f"{c_eye_pupil}    {c_eye_pupil}", c_mouth_flat, "Idling", 2.0),
                    ("-    -",                            c_mouth_flat, "Idling", 0.15),
                    (f"{c_eye_pupil}    {c_eye_pupil}", c_mouth_flat, "Idling", 0.5),
                    ("<    <",                            c_mouth_flat, "Idling", 1.5),
                    ("-    -",                            c_mouth_flat, "Idling", 0.15),
                    (">    >",                            c_mouth_flat, "Idling", 1.5),
                ]
                # Occasional random wink
                if random.random() > 0.7:
                    seq.append(("O    -", c_mouth_smile, "Wink! ;)", 1.2))
                    
                self._play_sequence(seq)

            elif anim == "LISTENING":
                seq = [
                    (f"{c_eye_happy}    {c_eye_happy}", c_mouth_smile, "Hello!", 0.3),
                    ("* *",                               c_mouth_cute,  "Hello!", 0.3),
                    (f"{c_eye_happy}    {c_eye_happy}", c_mouth_smile, "Hello!", 0.3),
                    ("O    O",                            c_mouth_cute,  "I hear u", 0.8),
                ]
                self._play_sequence(seq)

            elif anim == "EXPLORING":
                seq = [
                    (">    >", c_mouth_flat, "Scan...", 0.6),
                    ("<    <", c_mouth_flat, "Scan...", 0.6),
                    ("O    O", c_mouth_cute, "Oh?",     1.0),
                    ("-    -", c_mouth_flat, "Oh?",     0.1)
                ]
                self._play_sequence(seq)

            elif anim == "MOVING":
                seq = [
                    ("O    O", c_mouth_cute, "Walking", 0.25),
                    ("o    o", c_mouth_flat, "Walking", 0.25),
                    ("-    -", c_mouth_flat, "Walking", 0.15)
                ]
                self._play_sequence(seq)

            elif anim == "RESTING":
                # Awake but deeply relaxed. Heavy eyelids, static mouth.
                seq = [
                    ("=    =", c_mouth_flat, "Resting.", 2.0),
                    ("-    -", c_mouth_flat, "Resting.", 0.2), # Slow blink
                    ("=    =", c_mouth_flat, "Resting.", 2.0)
                ]
                self._play_sequence(seq)

            elif anim == "SLEEPY":
                # The Mood equivalent for resting.
                seq = [
                    ("=    =", "____", "Yawn...", 1.5),
                    ("-    -", " O  ", "Yawn...", 1.0),
                    ("=    =", "____", "Yawn...", 1.5)
                ]
                self._play_sequence(seq)

            elif anim == "SAD":
                seq = [
                    ("T    T", c_mouth_sad, "Lonely",  2.0),
                    ("-    -", "____",      "Sigh...", 0.5),
                    ("/    \\", c_mouth_sad, "Lonely",  1.5)
                ]
                self._play_sequence(seq)

            elif anim == "SLEEPING":
                seq = [
                    ("-    -", " .. ", "z     ", 1.2),
                    ("-    -", " .. ", "Zz    ", 1.2),
                    ("-    -", " .. ", "ZZz   ", 1.2),
                    ("-    -", " .. ", "snore.", 1.5)
                ]
                self._play_sequence(seq)

            elif anim == "DEAD":
                seq = [
                    ("X    X", "____", "SHUTDOWN", 1.5),
                    ("X    X", "____", "GOODBYE.", 1.5)
                ]
                self._play_sequence(seq)

            else:
                # If an unknown animation is requested, just rest briefly
                time.sleep(0.1)

    def stop(self):
        """Cleanly terminates the display thread and clears the screen."""
        self.running = False
        if self.lcd:
            try:
                self.lcd.clear()
            except IOError:
                pass
