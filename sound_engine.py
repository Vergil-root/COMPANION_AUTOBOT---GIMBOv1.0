import subprocess
import os
import logging

class SoundEngine:
    """
    Handles non-blocking audio playback using ALSA's 'aplay' command.
    Routes audio specifically to a connected Bluetooth speaker via PulseAudio.
    """
    # audio_dir can be anything, like any folder you chose to store the pre loaded audio .wav files 
    def __init__(self, audio_dir="/home/[USERNAME]/[YOUR FOLDER]/sounds(or name anything, like sounddir or something like that)"):
        self.audio_dir = audio_dir
        self.proc = None

        # Verify the audio directory exists on the system
        if not os.path.exists(self.audio_dir):
            logging.warning(f"SOUND WARNING: Audio directory {self.audio_dir} does not exist. Creating it.")
            try:
                os.makedirs(self.audio_dir)
            except Exception as e:
                logging.error(f"SOUND INIT ERROR: Could not create directory: {e}")

        logging.info("PERIPHERAL: Sound Engine Initialized (ALSA Popen Mode).")

    def play(self, sound_name):
        """
        Non-blocking audio playback. 
        Instantly interrupts any currently playing sound before starting the new one.
        """
        path = os.path.join(self.audio_dir, f"{sound_name}.wav")
        
        # Validate file existence before attempting to play
        if not os.path.exists(path):
            logging.error(f"SOUND ERROR: {sound_name}.wav not found at {path}")
            return

        try:
            # Interrupt any currently playing sound
            self.stop() 

            # Spawn a background process to play the audio.
            # Using '-D pulse' forces ALSA to route through PulseAudio (e.g., for Bluetooth).
            # '-q' runs it quietly so it doesn't spam the terminal.
            self.proc = subprocess.Popen(
                ["aplay", "-D", "pulse", "-q", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logging.debug(f"SOUND: Playing {sound_name}.wav")

        except FileNotFoundError:
            logging.error("SOUND FUSE TRIPPED: 'aplay' command not found. Is ALSA installed?")
        except Exception as e:
            logging.error(f"SOUND FUSE TRIPPED: {e}")

    def stop(self):
        """
        Safely kills the audio background process and cleans up any zombie processes.
        """
        if self.proc is not None:
            try:
                # poll() returns None if the process is still actively running
                if self.proc.poll() is None:
                    self.proc.terminate()
                    
                    # Wait up to 1 second for the process to close gracefully
                    # This prevents Linux 'Zombie' processes from eating up RAM
                    self.proc.wait(timeout=1.0)
                    
            except subprocess.TimeoutExpired:
                # If the process refuses to terminate gently, force kill it
                self.proc.kill()
                self.proc.wait()
                
            except Exception as e:
                logging.debug(f"SOUND STOP ERROR: {e}")
                
            finally:
                # Always clear the process variable so the engine knows it is free
                self.proc = None

    def is_playing(self):
        """
        Returns True if the audio process is currently running.
        Used by the main brain to implement Echo Cancellation (ignoring its own voice).
        """
        if self.proc is not None:
            # poll() returns None if the process hasn't finished yet
            if self.proc.poll() is None:
                return True
            else:
                # The process finished organically on its own. Clean up the variable.
                self.proc = None
                
        return False
