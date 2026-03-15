import cv2
import time
import logging
import threading
import os
from brain_enums import Event, EventType

# Limit OpenCV to 4 threads to prevent it from choking the Pi Zero's CPU
cv2.setNumThreads(4)

# --- Optional Hardware Camera Dependency ---
try:
    from picamera2 import Picamera2
except ImportError:
    logging.warning("VISION: Picamera2 not found. Please install with: sudo apt install python3-picamera2")
    Picamera2 = None

class VisionEngine:
    """
    Handles Computer Vision using the native Raspberry Pi Camera Module.
    Runs a lightweight Haar Cascade face detection model on a background thread.
    Outputs horizontal tracking commands to keep faces centered in the frame.
    """
    def __init__(self, event_queue=None):
        self.event_queue = event_queue
        self.running = True
        
        self.face_cascade = None
        self.picam2 = None

        # --- Vision Tuning Parameters ---
        self.process_fps = 10               # Target frames per second
        self.event_cooldown = 5.0           # Minimum seconds between 'FACE_DETECTED' alerts
        self.last_face_time = 0

        self.target_x_center = 160          # 320px width / 2 = Center
        self.horizontal_tracking_state = "stop"
        self.last_turn_speed = 0

        # --- Initialization ---
        self._init_cascade()
        self._init_camera()

        # Only start the heavy worker thread if both the camera and model loaded successfully
        if self.picam2 and self.face_cascade:
            threading.Thread(target=self._vision_worker, daemon=True).start()
            logging.info("VISION: Engine Online. Pure Horizontal Tracking enabled.")
        else:
            logging.error("VISION FUSE: Engine failed to start.")

    def _init_cascade(self):
        """
        Locates and loads the pre-trained OpenCV face detection model.
        Searches through common standard Linux installation directories.
        """
        cascade_name = 'haarcascade_frontalface_default.xml'
        
        possible_paths = [
            f'/usr/share/opencv4/haarcascades/{cascade_name}',
            f'/usr/share/opencv/haarcascades/{cascade_name}',
            f'/usr/local/share/opencv4/haarcascades/{cascade_name}'
        ]
        
        # Add the Python package directory if cv2.data is available
        if hasattr(cv2, 'data'):
            possible_paths.insert(0, cv2.data.haarcascades + cascade_name)

        # Find the first path that actually exists
        cascade_path = next((p for p in possible_paths if os.path.exists(p)), None)

        if cascade_path:
            self.face_cascade = cv2.CascadeClassifier(cascade_path)
            logging.info(f"VISION: Haar Cascade loaded from {cascade_path}")
        else:
            logging.critical("VISION: Haar Cascade XML not found in any system directories!")

    def _init_camera(self):
        """
        Boots the Picamera2 hardware interface.
        Locks resolution to a tiny 320x240 to maintain high FPS on the Pi Zero 2 W.
        """
        if Picamera2 is None:
            self.picam2 = None
            return

        try:
            logging.info("VISION: Booting Native Picamera2 ISP Interface...")
            self.picam2 = Picamera2()
            
            # 320x240 RGB888 is extremely lightweight for the Haar Cascade
            config = self.picam2.create_video_configuration(main={"size": (320, 240), "format": "RGB888"})
            self.picam2.configure(config)
            self.picam2.start()
            
            logging.info("VISION: SUCCESS! Hardware ISP locked at 320x240.")
            
        except Exception as e:
            logging.error(f"VISION INIT FUSE: {e}")
            self.picam2 = None

    def _vision_worker(self):
        """
        The background thread that constantly captures frames, detects faces, 
        and calculates horizontal tracking maneuvers.
        """
        sleep_time = 1.0 / self.process_fps

        while self.running and self.picam2:
            loop_start = time.time()
            
            try:
                # Capture frame and convert to grayscale for faster processing
                frame = self.picam2.capture_array()
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)

                # Run Face Detection
                faces = self.face_cascade.detectMultiScale(
                    gray, 
                    scaleFactor=1.35, 
                    minNeighbors=5, 
                    minSize=(35, 35)
                )

                if len(faces) > 0:
                    # If multiple faces, track the largest one (closest to camera)
                    largest_face = max(faces, key=lambda rect: rect[2] * rect[3])
                    x, y, w, h = largest_face
                    face_cx = x + (w // 2)

                    # Calculate how far off-center the face is
                    error_x = face_cx - self.target_x_center
                    new_h_state = "stop"
                    turn_speed = 0

                    # --- Proportional Turning Logic ---
                    # The further the face is from the center, the faster the robot turns.
                    # Deadzone is +/- 40 pixels to prevent jittering when perfectly centered.
                    
                    if error_x < -40:
                        new_h_state = "left"
                        # Base speed 80 + proportional multiplier (max speed 110)
                        turn_speed = min(110, 80 + abs(error_x) * 0.2)
                        
                    elif error_x > 40:
                        new_h_state = "right"
                        turn_speed = min(110, 80 + abs(error_x) * 0.2)

                    turn_speed = int(turn_speed)
                    speed_delta = abs(self.last_turn_speed - turn_speed)

                    # Only send a new drive command if the direction changed OR 
                    # the required speed changed by a significant margin (> 10).
                    # This prevents spamming the serial port.
                    if new_h_state != self.horizontal_tracking_state or (new_h_state != "stop" and speed_delta > 10):
                        self.horizontal_tracking_state = new_h_state
                        self.last_turn_speed = turn_speed
                        
                        if self.event_queue:
                            self.event_queue.put(Event(EventType.DRIVE_COMMAND, (new_h_state, turn_speed)))

                    # --- Event Alerting ---
                    # Tell the Brain we saw a face so it can react emotionally
                    now = time.time()
                    if now - self.last_face_time > self.event_cooldown:
                        logging.info(f"VISION: Tracking face (X err:{error_x})")
                        self.last_face_time = now
                        
                        if self.event_queue:
                            self.event_queue.put(Event(EventType.FACE_DETECTED))

                else:
                    # No faces detected. Stop tracking.
                    if self.horizontal_tracking_state != "stop":
                        self.horizontal_tracking_state = "stop"
                        self.last_turn_speed = 0
                        
                        if self.event_queue:
                            self.event_queue.put(Event(EventType.DRIVE_COMMAND, ("stop", 0)))

                # Enforce FPS limit to save CPU cycles i.e keep CPU usage under control
                processing_time = time.time() - loop_start
                if processing_time < sleep_time:
                    time.sleep(sleep_time - processing_time)

            except Exception as e:
                logging.error(f"VISION WORKER FUSE: {e}")
                time.sleep(1.0)

    def stop(self):
        """Cleanly releases the camera hardware."""
        self.running = False
        if self.picam2:
            try:
                self.picam2.stop()
                self.picam2.close()
            except Exception as e:
                logging.error(f"VISION CLEANUP FUSE: {e}")
                
        logging.info("VISION: Camera safely released.")
