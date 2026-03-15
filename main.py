import threading
import time
import sys
import signal
import logging
import queue
import psutil
import numpy as np
import sounddevice as sd

from brain import PetRobotBrain
from lcd_engine import LCDEngine
from sound_engine import SoundEngine
from stt_engine import STTEngine
from motion_engine import MotionEngine
from vision_engine import VisionEngine
from sensor_engine import SensorEngine
from brain_enums import Event, EventType

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
audio_queue = queue.Queue(maxsize=30)

def main():
    logging.info("CORE: Starting Deployment on Pi Zero 2 W...")

    # Initialize hardware components to None
    lcd = sound = motion = ears = brain = vision = sensors = None

    def signal_handler(sig, frame):
        logging.info("SYSTEM: Received termination signal.")
        if brain:
            brain.running = False

    # Register shutdown signals
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 1. Initialize Engines
        lcd = LCDEngine()
        sound = SoundEngine()
        motion = MotionEngine()
        ears = STTEngine()

        brain = PetRobotBrain(lcd, sound, motion)

        # Link event queues
        motion.event_queue = brain.event_queue
        vision = VisionEngine(event_queue=brain.event_queue)
        sensors = SensorEngine(event_queue=brain.event_queue)

        # 2. Define Background Workers
        def telemetry_worker():
            """Monitors system vitals and biological states."""
            while brain.running:
                cpu = psutil.cpu_percent(interval=1)
                ram = psutil.virtual_memory().percent
                temp = 0.0
                
                try:
                    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                        temp = float(f.read()) / 1000.0
                except Exception:
                    pass
                
                logging.info(f"TELEMETRY: CPU: {cpu}% | RAM: {ram}% | TEMP: {temp:.1f}C | STAMINA: {brain.stamina:.1f}% | BATTERY: {brain.battery_level:.1f}%")
                time.sleep(10)

        def ears_worker():
            """Processes raw audio for voice commands."""
            last_audio_playback_time = 0
            
            while brain.running:
                try:
                    indata = audio_queue.get(timeout=1)

                    # Audio processing and downsampling
                    audio_mono = indata.mean(axis=1)
                    audio_16k = audio_mono[::3]
                    audio_16bit = (audio_16k.astype(np.int32) >> 16).astype(np.int16)

                    # Echo cancellation check
                    if hasattr(sound, 'is_playing') and sound.is_playing():
                        last_audio_playback_time = time.time()

                    command = ears.get_command(audio_16bit.tobytes())
                    
                    if command:
                        # Ignore self-voice
                        if time.time() - last_audio_playback_time < 2.0:
                            continue

                        # TRUE REVERSION: The Bulletproof Ghost Filter
                        # Since vocab only has multi-word phrases, a single word is mechanical noise.
                        word_count = len(command.split())

                        if word_count >= 2:
                            brain.event_queue.put(Event(EventType.VOICE_COMMAND, command))
                        else:
                            logging.warning(f"GHOST FILTER: Blocked mechanical false-positive -> '{command}'")

                except queue.Empty:
                    continue
                except Exception as e:
                    logging.error(f"EARS WORKER FUSE: {e}")

        def audio_callback(indata, frames, time_info, status):
            """Feeds the live microphone data into the processing queue."""
            try:
                audio_queue.put_nowait(indata.copy())
            except queue.Full:
                pass

        # 3. Start Background Threads
        threading.Thread(target=brain.run, daemon=True).start()
        threading.Thread(target=ears_worker, daemon=True).start()
        threading.Thread(target=telemetry_worker, daemon=True).start()

        # 4. Main Live Loop
        with sd.InputStream(device=0, channels=2, samplerate=48000, dtype='int32', blocksize=4096, callback=audio_callback):
            logging.info("SYSTEM LIVE. Monitoring Stats & Audio.")
            
            while brain.running:
                motion.update()
                time.sleep(0.015)

    except Exception as e:
        logging.critical(f"SYSTEM HALTED: {e}", exc_info=True)
        
    finally:
        # 5. Safe Shutdown Sequence
        logging.info("SHUTDOWN: Cleaning hardware...")
        
        if motion:
            motion.emergency_stop()
        if sound:
            sound.stop()
        if vision:
            vision.stop()
        if sensors:
            sensors.stop()
            
        if lcd:
            try:
                lcd.lcd.clear()
                lcd.lcd.write_string("SYSTEM OFFLINE")
            except Exception:
                pass
                
        sys.exit(0)

if __name__ == "__main__":
    main()
