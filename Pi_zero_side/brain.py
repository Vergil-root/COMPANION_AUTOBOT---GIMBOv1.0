import time
import random
import logging
import os
from queue import Queue, Empty
from brain_enums import LifeState, ActivityState, Mood, EventType, Event

class PetRobotBrain:
    """
    The Central Biological State Machine.
    Handles decision making, mood transitions, energy/stamina tracking,
    and sequence timing for both LCD faces and physical servos.
    """
    def __init__(self, lcd, sound, motion):
        # Hardware Engines
        self.lcd = lcd
        self.sound = sound
        self.motion = motion

        # --- Core States ---
        self.life_state = LifeState.AWAKE
        self.activity_state = ActivityState.IDLE
        self.mood = Mood.CURIOUS
        self.running = True

        # --- Biological Energy System ---
        self.battery_level = 100.0
        self.stamina = 100.0
        self.boredom = 0.0
        self.low_battery_played = False

        # --- Timers & Cooldowns ---
        self.last_update_time = time.time()
        self.state_start_time = time.time()
        self.last_interaction_time = time.time()
        self.last_idle_anim_time = time.time()
        self.explore_change_time = 0
        self.explore_duration = 0
        self.sleep_start_time = 0

        self.activity_locked_until = 0.0
        self.last_face_change_time = time.time()
        self.face_hold_duration = 0.0

        # --- Maneuver & Event Queues ---
        self.base_sequence = []
        self.base_seq_end_time = 0
        self.event_queue = Queue()

        # --- Servo Shortcuts & Resting Poses ---
        self.SL = motion.SHOULDER_LEFT
        self.EL = motion.ELBOW_LEFT
        self.BL = motion.BASE_LEFT
        self.SR = motion.SHOULDER_RIGHT
        self.ER = motion.ELBOW_RIGHT
        self.BR = motion.BASE_RIGHT
        self.REST = motion.REST_POS

        # --- Boot Sequence ---
        logging.info("BRAIN: Initialization complete. Biological HFSM Online.")
        self.sound.play("greeting")
        
        # Pick a random startup animation
        anim_func = random.choices(
            [self.get_right_hand_wave, self.get_excited, self.get_idle_animation1], 
            weights=[0.6, 0.3, 0.1]
        )[0]
        
        self.motion.load_expression(anim_func())
        self.sync_display()

    # ================= CORE COGNITIVE LOOP =================

    def run(self):
        """Main loop that constantly consumes events and ticks biology."""
        while self.running:
            try:
                # Process all events in the queue immediately
                while not self.event_queue.empty():
                    event = self.event_queue.get_nowait()
                    
                    if self.life_state == LifeState.AWAKE:
                        self._handle_awake_logic(event)
                    elif self.life_state == LifeState.SLEEPING:
                        self._handle_sleep_logic(event)
                        
            except Empty:
                pass
            except Exception as e:
                logging.error(f"BRAIN EVENT LOOP FUSE: {e}")

            # Tick biological functions
            self.update_internal_states()
            time.sleep(0.05) # 20Hz Cognitive Tick

    # ================= STATE TRANSITIONS =================

    def sync_display(self):
        """Forces the LCD to match the current critical hardware state."""
        try:
            if self.life_state == LifeState.SHUTDOWN:
                return self.lcd.set_animation("DEAD")
            if self.life_state == LifeState.SLEEPING:
                return self.lcd.set_animation("SLEEPING")
            if self.battery_level < 15:
                return self.lcd.set_animation("DEAD")
                
            self.face_hold_duration = 0.0
        except Exception as e:
            logging.error(f"LCD SYNC FUSE: {e}")

    def load_base_sequence(self, sequence):
        """Loads a sequence of drive commands (e.g., evasion maneuvers)."""
        self.base_sequence = list(sequence)
        self.base_seq_end_time = 0

    def transition_life(self, new_state: LifeState):
        if self.life_state != new_state:
            logging.info(f"LIFE STATE: {self.life_state.name} -> {new_state.name}")
            self.life_state = new_state

            if new_state == LifeState.SLEEPING:
                self.sleep_start_time = time.time()
                self.sound.play("sleepy")
                self.base_sequence = []
                self.motion.emergency_stop()
                self.motion.load_expression([(2.0, self.REST)])
            elif new_state == LifeState.AWAKE:
                self.stamina = self.battery_level
                self.boredom = 0.0
                
            self.sync_display()

    def transition_activity(self, new_state: ActivityState):
        if self.activity_state != new_state:
            logging.info(f"ACTIVITY: {self.activity_state.name} -> {new_state.name}")
            prev_state = self.activity_state
            self.activity_state = new_state
            self.state_start_time = time.time()

            # Clear any ongoing physical sequences
            self.base_sequence = []
            self.base_seq_end_time = 0

            if prev_state == ActivityState.INTERACTING:
                self.motion.set_drive_mode("stop")
                
            if new_state in [ActivityState.IDLE, ActivityState.RESTING, ActivityState.EVADING]:
                self.motion.set_drive_mode("stop")
            elif new_state == ActivityState.EXPLORING:
                self.explore_change_time = 0
                
            self.sync_display()

    def set_mood(self, new_mood: Mood, mute_sound=False):
        if self.mood != new_mood:
            logging.info(f"MOOD: {self.mood.name} -> {new_mood.name}")
            self.mood = new_mood
            
            if not mute_sound:
                if new_mood == Mood.HAPPY:
                    self.sound.play("happy")
                elif new_mood == Mood.SAD:
                    self.sound.play("sad")
                elif new_mood == Mood.ANGRY:
                    self.sound.play("angry")
                elif new_mood == Mood.CURIOUS:
                    self.sound.play("curious")
                elif new_mood == Mood.SLEEPY:
                    self.sound.play("sleepy")
                    
            self.sync_display()

    # ================= EVENT HANDLERS =================

    def _handle_awake_logic(self, event: Event):
        """Processes sensor and voice events when the robot is awake."""
        now = time.time()
        self.last_interaction_time = now

        try:
            if event.type == EventType.BATTERY_UPDATE:
                self.battery_level = event.data

            # --- HARDWARE REFLEX AVOIDANCE ---
            elif event.type == EventType.OBSTACLE:
                # Do not interrupt if we are already evading
                if self.activity_state == ActivityState.EVADING:
                    return

                logging.warning(f"PI AVOIDANCE: Evading {event.data} obstacle!")
                self.boredom = min(100.0, self.boredom + 10)
                self.transition_activity(ActivityState.EVADING)

                turn = random.choice(["left", "right"])
                turn_dur = random.uniform(0.8, 1.1)

                # Execute sharp 90-degree pivots at max speed (127)
                if event.data == "FRONT":
                    self.load_base_sequence([
                        (0.6, "backward", 120), (0.2, "stop", 0), 
                        (turn_dur, turn, 127), (0.2, "stop", 0)
                    ])
                elif event.data == "BACK":
                    self.load_base_sequence([
                        (0.6, "forward", 120), (0.2, "stop", 0), 
                        (turn_dur, turn, 127), (0.2, "stop", 0)
                    ])
                elif event.data == "LEFT":
                    self.load_base_sequence([
                        (0.5, "backward", 120), (0.2, "stop", 0), 
                        (turn_dur, "right", 127), (0.2, "stop", 0)
                    ])
                elif event.data == "RIGHT":
                    self.load_base_sequence([
                        (0.5, "backward", 120), (0.2, "stop", 0), 
                        (turn_dur, "left", 127), (0.2, "stop", 0)
                    ])

            # --- COMPUTER VISION: FACES ---
            elif event.type == EventType.FACE_DETECTED:
                self.boredom = 0.0
                
                # Cheer up if it sees a human
                if self.mood in [Mood.SAD, Mood.SLEEPY] and self.stamina > 40:
                    self.set_mood(Mood.HAPPY, mute_sound=True)

                if self.activity_state != ActivityState.INTERACTING:
                    self.transition_activity(ActivityState.INTERACTING)

                    if self.mood in [Mood.HAPPY, Mood.CURIOUS]:
                        self.sound.play("greeting")
                        anim = random.choices(
                            [self.get_right_hand_wave, self.get_casual_wave, self.get_excited, self.get_cute_motion],
                            weights=[0.6, 0.15, 0.15, 0.1]
                        )[0]
                        self.motion.load_expression(anim())
                        
                        # Random happy wiggle
                        if random.random() > 0.4:
                            self.load_base_sequence([
                                (0.25, "left", 110), 
                                (0.5, "right", 110), 
                                (0.25, "left", 110)
                            ])
                            
                    elif self.mood in [Mood.SAD, Mood.SLEEPY]:
                        self.sound.play("sleepy")
                        self.motion.load_expression(self.get_sad_droop())
                        
                    elif self.mood == Mood.ANGRY:
                        self.sound.play("angry")
                        anim = random.choices([self.get_flexing, self.get_flexing2], weights=[0.8, 0.2])[0]
                        self.motion.load_expression(anim())
                        self.load_base_sequence([
                            (0.15, "left", 120), 
                            (0.3, "right", 120), 
                            (0.15, "left", 120)
                        ])

            # --- VOICE COMMANDS ---
            elif event.type == EventType.VOICE_COMMAND:
                self.boredom = 0
                self.process_voice_command(event.data.lower())

            # --- DRIVE COMMANDS (From Vision Engine) ---
            elif event.type == EventType.DRIVE_COMMAND:
                mode, speed = event.data
                if self.activity_state == ActivityState.INTERACTING and not self.base_sequence:
                    if self.mood in [Mood.HAPPY, Mood.CURIOUS]:
                        self.motion.set_drive_mode(mode, speed=speed)
                    else:
                        self.motion.set_drive_mode("stop")

        except Exception as e:
            logging.error(f"BRAIN AWAKE FUSE: {e}")

    def _handle_sleep_logic(self, event: Event):
        """Processes events allowed to wake the robot up."""
        if event.type == EventType.VOICE_COMMAND:
            words = event.data.lower().split()
            
            if "morning" in words or "wake" in words:
                self.transition_life(LifeState.AWAKE)
                self.set_mood(Mood.HAPPY)
                anim = random.choices([self.get_excited, self.get_idle_animation2], weights=[0.7, 0.3])[0]
                self.motion.load_expression(anim())
                
            elif "shutdown" in words:
                self.transition_life(LifeState.SHUTDOWN)
                time.sleep(1.0)
                os.system("sudo shutdown now")

    # ================= VOICE COMMAND PROCESSING =================

    def process_voice_command(self, cmd_string):
        words = cmd_string.split()
        now = time.time()

        if "shutdown" in words:
            self.transition_life(LifeState.SHUTDOWN)
            self.sound.play("sleepy")
            self.motion.emergency_stop()
            self.motion.load_expression([(2.0, self.REST)])
            time.sleep(2.5)
            os.system("sudo shutdown now")
            
        elif "morning" in words:
            self.set_mood(Mood.HAPPY)
            self.activity_locked_until = now + 1800
            anim = random.choices(
                [self.get_excited, self.get_right_hand_wave, self.get_idle_animation2], 
                weights=[0.5, 0.3, 0.2]
            )[0]
            self.motion.load_expression(anim())
            self.load_base_sequence([(0.3, "left", 110), (0.6, "right", 110), (0.3, "left", 110)])
            
        elif any(w in words for w in ["sleep", "goodnight"]):
            self.transition_life(LifeState.SLEEPING)
            
        elif "rest" in words:
            self.transition_activity(ActivityState.RESTING)
            self.activity_locked_until = now + 3600
            self.set_mood(Mood.SLEEPY)
            self.motion.load_expression(self.get_resting_posture())
            
        elif any(w in words for w in ["stop", "halt"]):
            self.transition_activity(ActivityState.IDLE)
            self.activity_locked_until = now + 3600
            
        elif "mom" in words or "dad" in words or "sister" in words:
            self.transition_activity(ActivityState.INTERACTING)
            self.set_mood(Mood.HAPPY, mute_sound=True)
            
            if "mom" in words:
                self.sound.play("mom")
            elif "dad" in words:
                self.sound.play("dad")
            elif "sister" in words:
                self.sound.play("sister")
                
            anim = random.choices(
                [self.get_excited, self.get_cute_motion, self.get_excited2, self.get_cute_motion2], 
                weights=[0.4, 0.4, 0.1, 0.1]
            )[0]
            self.motion.load_expression(anim())
            self.load_base_sequence([(0.3, "left", 110), (0.6, "right", 110), (0.3, "left", 110)])
            
        elif "hello" in words or "greetings" in words:
            self.transition_activity(ActivityState.INTERACTING)
            self.set_mood(Mood.HAPPY, mute_sound=True)
            self.sound.play("greeting")
            anim = random.choices(
                [self.get_right_hand_wave, self.get_casual_wave, self.get_excited], 
                weights=[0.7, 0.2, 0.1]
            )[0]
            self.motion.load_expression(anim())
            self.load_base_sequence([(0.2, "left", 100), (0.4, "right", 100), (0.2, "left", 100)])
            
        elif "explore" in words or "walk" in words:
            if self.stamina < 25.0:
                self.set_mood(Mood.SLEEPY)
                self.sound.play("sleepy")
                self.motion.load_expression(self.get_sad_droop())
            else:
                self.activity_locked_until = now + 3600
                self.transition_activity(ActivityState.EXPLORING)
                
        elif "run" in words:
            if self.stamina < 30.0:
                self.set_mood(Mood.SLEEPY)
                self.sound.play("sleepy")
                self.motion.load_expression(self.get_sad_droop())
            else:
                self.activity_locked_until = now + 3600
                self.transition_activity(ActivityState.MOVING)
                self.motion.set_drive_mode("forward", speed=125)
                
        elif "angry" in words or "bad" in words or "no" in words or "exercise" in words:
            self.set_mood(Mood.ANGRY)
            anim = random.choices([self.get_flexing, self.get_flexing2], weights=[0.8, 0.2])[0]
            self.motion.load_expression(anim())
            self.load_base_sequence([(0.15, "left", 125), (0.3, "right", 125), (0.15, "left", 125)])
            
        else:
            anim = random.choices(
                [self.get_cute_motion, self.get_idle_animation1, self.get_cute_motion2], 
                weights=[0.5, 0.3, 0.2]
            )[0]
            self.motion.load_expression(anim())

    # ================= BIOLOGICAL TIMERS & UPDATES =================

    def update_internal_states(self):
        """Constantly updates the math for stamina, boredom, and faces."""
        now = time.time()
        dt = now - self.last_update_time
        self.last_update_time = now

        if self.life_state == LifeState.AWAKE:
            # Energy consumption math
            if self.activity_state == ActivityState.RESTING:
                self.stamina = min(self.battery_level, self.stamina + 0.15 * dt)
                self.boredom = max(0.0, self.boredom - 0.2 * dt)
            else:
                self.stamina = max(0.0, self.stamina - 0.05 * dt)
                self.boredom = min(100.0, self.boredom + 1.5 * dt)

            # Auto-Sleep if dead
            if self.battery_level <= 5.0 or self.stamina <= 0.0:
                self.transition_life(LifeState.SLEEPING)
                return

            if self.battery_level < 20.0 and not self.low_battery_played:
                self.sound.play("low_battery")
                self.low_battery_played = True

            # Biological mood shifts
            if self.stamina < 25 and self.mood != Mood.SLEEPY:
                self.set_mood(Mood.SLEEPY)
            elif self.boredom > 75 and self.mood not in [Mood.SAD, Mood.ANGRY]:
                self.set_mood(Mood.SAD)
            elif self.boredom < 30 and self.stamina > 40 and self.mood in [Mood.SAD, Mood.SLEEPY]:
                self.set_mood(Mood.CURIOUS)

            # Update visuals and continuous logic
            self._update_face(now)
            self._process_base_sequence(now)

            # Route to behavior sub-loops
            if self.activity_state == ActivityState.IDLE:
                self._behavior_idle(now)
            elif self.activity_state == ActivityState.EXPLORING:
                self._behavior_explore(now)
            elif self.activity_state == ActivityState.RESTING:
                self._behavior_resting(now)
            elif self.activity_state == ActivityState.INTERACTING:
                if (now - self.last_interaction_time) > 15:
                    self.transition_activity(ActivityState.IDLE)
            elif self.activity_state == ActivityState.EVADING:
                if not self.base_sequence:
                    self.transition_activity(ActivityState.IDLE)

        elif self.life_state == LifeState.SLEEPING:
            # Auto-wake after 1 hour if battery is safe
            if now - self.sleep_start_time > 3600 and self.battery_level > 20:
                self.transition_life(LifeState.AWAKE)
                self.motion.load_expression(self.get_flexing2())
                self.set_mood(Mood.HAPPY)

    def _process_base_sequence(self, now):
        """Processes the queued array of drive maneuvers (e.g., pivots)."""
        if self.base_sequence:
            if now >= self.base_seq_end_time:
                duration, mode, speed = self.base_sequence.pop(0)
                self.motion.set_drive_mode(mode, speed)
                self.base_seq_end_time = now + duration
                
        elif self.base_seq_end_time > 0 and now >= self.base_seq_end_time:
            if self.activity_state != ActivityState.EXPLORING:
                self.motion.set_drive_mode("stop")
            self.base_seq_end_time = 0

    def _update_face(self, now):
        """Dynamic LCD Face Multiplexer based on Activity and Mood."""
        if self.life_state != LifeState.AWAKE or self.battery_level < 15:
            return
            
        if now - self.last_face_change_time > self.face_hold_duration:
            self.last_face_change_time = now
            current_mood_str = self.mood.name

            # Decide which face animations to pick from based on current state
            if self.activity_state == ActivityState.INTERACTING:
                choices = [current_mood_str, "LISTENING"]
                weights = [0.8, 0.2]
                self.face_hold_duration = random.uniform(2.0, 5.0)
                
            elif self.activity_state == ActivityState.EXPLORING:
                choices = [current_mood_str, "EXPLORING"]
                weights = [0.4, 0.6]
                self.face_hold_duration = random.uniform(1.5, 3.5)
                
            elif self.activity_state == ActivityState.MOVING:
                choices = [current_mood_str, "MOVING"]
                weights = [0.3, 0.7]
                self.face_hold_duration = random.uniform(1.0, 2.5)
                
            elif self.activity_state == ActivityState.RESTING:
                choices = [current_mood_str, "RESTING"]
                weights = [0.3, 0.7]
                self.face_hold_duration = random.uniform(2.0, 5.0)
                
            elif self.activity_state == ActivityState.EVADING:
                choices = ["ANGRY", "EXPLORING"]
                weights = [0.7, 0.3]
                self.face_hold_duration = random.uniform(1.0, 2.0)
                
            else:
                choices = [current_mood_str, "IDLE"]
                weights = [0.7, 0.3]
                self.face_hold_duration = random.uniform(3.0, 6.0)

            try:
                chosen_face = random.choices(choices, weights=weights)[0]
                self.lcd.set_animation(chosen_face)
            except Exception:
                pass

    # ================= SUB-BEHAVIOR LOOPS =================

    def _behavior_idle(self, now):
        # Auto-explore if highly bored
        if self.boredom > 80 and self.stamina > 30 and now > self.activity_locked_until:
            self.transition_activity(ActivityState.EXPLORING)
            return

        # Random fidgets and noises
        if (now - self.last_idle_anim_time) > random.uniform(3.0, 8.0):
            if random.random() < 0.3:
                self.sound.play(random.choice(["idle1", "idle2", "idle3"]))

            # Choose animation pools based on mood
            if self.mood == Mood.HAPPY:
                pool = [self.get_excited, self.get_cute_motion, self.get_right_hand_wave, self.get_excited2, self.get_casual_wave, self.get_cute_motion2]
                weights = [0.3, 0.25, 0.2, 0.1, 0.05, 0.1]
            elif self.mood == Mood.SAD:
                pool = [self.get_sad_droop, self.get_idle_animation3]
                weights = [0.8, 0.2]
            elif self.mood == Mood.ANGRY:
                pool = [self.get_flexing, self.get_idle_animation4, self.get_flexing2]
                weights = [0.6, 0.2, 0.2]
            else:
                pool = [self.get_idle_animation1, self.get_idle_animation2, self.get_idle_animation3, self.get_idle_animation4, self.get_cute_motion]
                weights = [0.4, 0.2, 0.15, 0.1, 0.15]

            anim_func = random.choices(pool, weights=weights)[0]
            self.motion.load_expression(anim_func())
            self.last_idle_anim_time = now

    def _behavior_explore(self, now):
        # Time to stop exploring?
        if (self.boredom < 10 and (now - self.state_start_time) > 45 and now > self.activity_locked_until) or self.stamina < 25:
            self.transition_activity(ActivityState.IDLE)
            return

        # Next wandering step
        if (now - self.explore_change_time) > self.explore_duration:
            actions = [
                ("forward", 100, random.uniform(2.0, 4.0)), 
                ("left", 90, random.uniform(0.5, 1.2)), 
                ("right", 90, random.uniform(0.5, 1.2)), 
                ("stop", 0, random.uniform(2.0, 5.0))
            ]
            cmd, speed, duration = random.choices(actions, weights=[0.4, 0.2, 0.2, 0.2])[0]

            if cmd == "stop":
                self.motion.emergency_stop()
                if random.random() < 0.5:
                    anim = random.choices([self.get_idle_animation1, self.get_idle_animation4], weights=[0.7, 0.3])[0]
                    self.motion.load_expression(anim())
            else:
                self.motion.set_drive_mode(cmd, speed=speed)

            self.explore_change_time = now
            self.explore_duration = duration
            
    def _behavior_resting(self, now):
        # Fully charged?
        if self.stamina >= (self.battery_level - 1.0) and now > self.activity_locked_until:
            self.transition_activity(ActivityState.IDLE)
            self.set_mood(Mood.CURIOUS, mute_sound=True)
            self.motion.load_expression(self.get_idle_animation1())
            return
            
        if (now - self.last_idle_anim_time) > random.uniform(6.0, 10.0):
            self.motion.load_expression(self.get_resting_posture())
            self.last_idle_anim_time = now

    # ================= ANIMATION LIBRARIES =================

    def repeat_sequence(self, frames, n):
        """Helper to loop an animation snippet 'n' times."""
        res = []
        for _ in range(n):
            res.extend(frames)
        return res

    def get_excited(self):
        return [
            (0.3, {self.BL: 40, self.BR: 40, self.SL: 60, self.SR: 60, self.EL: 120, self.ER: 120}),
            *self.repeat_sequence([
                (0.2, {self.BL: 30, self.BR: 50, self.SL: 70, self.SR: 50, self.EL: 90, self.ER: 110}),
                (0.2, {self.BL: 50, self.BR: 30, self.SL: 50, self.SR: 70, self.EL: 110, self.ER: 90})
            ], 8),
            (0.5, {self.BL: 20, self.BR: 20, self.SL: 10, self.SR: 10, self.EL: 150, self.ER: 150}),
            (1.5, self.REST)
        ]

    def get_excited2(self):
        return [
            (0.6, {self.SL: 70, self.SR: 70, self.EL: 130, self.ER: 130, self.BL: 60, self.BR: 120}),
            (0.4, {self.SL: 50, self.SR: 50, self.EL: 160, self.ER: 160, self.BL: 90, self.BR: 90}),
            (0.6, {self.SL: 70, self.SR: 70, self.EL: 130, self.ER: 130, self.BL: 110, self.BR: 60}),
            (1.5, self.REST)
        ]

    def get_flexing(self):
        return [
            (1.0, {self.BL: 20, self.BR: 20}),
            (1.0, {self.SL: 80, self.SR: 80}),
            *self.repeat_sequence([
                (0.5, {self.EL: 100, self.ER: 100}),
                (0.5, {self.EL: 170, self.ER: 170})
            ], 4),
            (1.5, self.REST)
        ]

    def get_flexing2(self):
        if random.choice([True, False]):
            return [
                (1.2, {self.SL: 90, self.EL: 90, self.BL: 70}),
                (0.8, {self.SL: 110, self.EL: 50}),
                (1.5, self.REST)
            ]
        else:
            return [
                (1.2, {self.SR: 90, self.ER: 90, self.BR: 130}),
                (0.8, {self.SR: 110, self.ER: 50}),
                (1.5, self.REST)
            ]

    def get_right_hand_wave(self):
        return [
            (1.0, {self.BR: 20, self.SR: 45, self.ER: 170}),
            *self.repeat_sequence([
                (0.4, {self.SR: 70, self.ER: 100}),
                (0.2, {self.SR: 20, self.ER: 160})
            ], 5),
            (1.0, self.REST)
        ]

    def get_casual_wave(self):
        if random.choice([True, False]):
            return [
                (0.8, {self.SL: 70, self.EL: 100}),
                *self.repeat_sequence([
                    (0.6, {self.SL: 80}),
                    (0.6, {self.SL: 60})
                ], 2),
                (1.2, self.REST)
            ]
        else:
            return [
                (0.8, {self.SR: 70, self.ER: 100}),
                *self.repeat_sequence([
                    (0.6, {self.SR: 80}),
                    (0.6, {self.SR: 60})
                ], 2),
                (1.2, self.REST)
            ]

    def get_cute_motion(self):
        return [
            (1.2, {self.BL: 20, self.BR: 20, self.EL: 100, self.ER: 100}),
            *self.repeat_sequence([
                (0.4, {self.SL: 20, self.SR: 20}),
                (0.4, {self.SL: 100, self.SR: 100})
            ], 6),
            (1.5, self.REST)
        ]

    def get_cute_motion2(self):
        return [
            (1.5, {self.SL: 80, self.SR: 80, self.EL: 80, self.ER: 80, self.BL: 60, self.BR: 140}),
            (1.0, {self.BL: 100, self.BR: 80}),
            (1.5, self.REST)
        ]

    def get_idle_animation1(self):
        return self.repeat_sequence([
            (1.5, {self.BL: 70, self.BR: 90, self.SL: 35, self.SR: 55}),
            (2.0, self.REST)
        ], 2)

    def get_idle_animation2(self):
        return [
            (1.0, {self.BL: 80, self.BR: 80, self.SL: 50, self.SR: 50, self.EL: 160, self.ER: 160}),
            (1.2, {self.BL: 60, self.BR: 95, self.SL: 55, self.SR: 45}),
            (1.5, self.REST)
        ]

    def get_idle_animation3(self):
        if random.choice([True, False]):
            return [
                (2.0, {self.SL: 45, self.EL: 155, self.BL: 80}),
                (1.5, self.REST)
            ]
        else:
            return [
                (2.0, {self.SR: 45, self.ER: 155, self.BR: 120}),
                (1.5, self.REST)
            ]

    def get_idle_animation4(self):
        return [
            (2.0, {self.BL: 120, self.BR: 60, self.SL: 50, self.SR: 50}),
            (1.0, {self.BL: 120, self.BR: 60}),
            (3.0, {self.BL: 60, self.BR: 120, self.SL: 60, self.SR: 60}),
            (1.0, {self.BL: 60, self.BR: 120}),
            (2.0, self.REST)
        ]

    def get_sad_droop(self):
        return [
            (2.0, {self.SL: 30, self.SR: 30, self.EL: 120, self.ER: 120}),
            (1.5, {self.SL: 25, self.SR: 25}),
            (2.0, self.REST)
        ]

    def get_resting_posture(self):
        return [
            (1.5, {self.BL: 80, self.BR: 80, self.SL: 35, self.SR: 35, self.EL: 150, self.ER: 150}),
            (1.0, {self.SL: 45, self.SR: 45}),
            (1.5, {self.SL: 35, self.SR: 35}),
            (1.0, self.REST)
        ]
