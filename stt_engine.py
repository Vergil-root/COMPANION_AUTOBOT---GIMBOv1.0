import json
import logging
from vosk import Model, KaldiRecognizer

class STTEngine:
    """
    Speech-to-Text Engine using Vosk.
    Operates entirely offline, processing audio frames in real-time.
    Features strict vocabulary locking, confidence tracking, and memory-leak prevention.
    """
    # model path can be any folder directory you chose to store the vosk model file folder 
    def __init__(self, model_path="/home/[USERNAME]/vosk_model/vosk-model-small-en-us-0.15"):
        try:
            logging.info("STT: Loading Vosk Model...")
            self.model = Model(model_path)

            # Strict vocabulary to force the model to ONLY recognize specific phrases,
            # drastically reducing false positives from mechanical noise.
            self.vocab = (
                '['
                '"hello buddy", '
                '"can you shutdown now", '
                '"walk forward buddy", '
                '"run my friend", '
                '"stop right now", '
                '"rest now my friend", '
                '"goodnight buddy", '
                '"good morning buddy", '
                '"go explore the place", '
                '"go to sleep buddy", '
                '"[unk]"'
                ']'
            )
            
            self.rec = KaldiRecognizer(self.model, 16000, self.vocab)
            self.rec.SetWords(True)
            
            logging.info("STT: Engine initialized offline with Confidence Tracking.")
            
        except Exception as e:
            logging.error(f"STT INITIALIZATION ERROR: {e}")
            raise

    def get_command(self, audio_bytes):
        """
        Consumes pre-processed 16-bit 16kHz Mono bytes directly from main.py.
        Returns the recognized command string if confidence is high enough, else None.
        """
        try:
            # AcceptWaveform returns True when silence is detected (a full phrase is complete)
            if self.rec.AcceptWaveform(audio_bytes):
                res = json.loads(self.rec.Result())

                # Ensure we actually have a text result that isn't empty or unknown
                if "result" in res and res.get("text", "") not in ["", "[unk]"]:
                    command = res["text"].strip()

                    # Calculate the Average Confidence of the spoken phrase
                    confidences = [word["conf"] for word in res["result"]]
                    avg_conf = sum(confidences) / len(confidences)

                    # Threshold Check: 65% confidence required to pass
                    if avg_conf >= 0.65:
                        logging.info(f"STT ACCEPTED: '{command}' (Confidence: {avg_conf:.2f})")
                        return command
                    else:
                        logging.info(f"STT REJECTED (Ghost Noise): '{command}' (Confidence: {avg_conf:.2f})")
            
            # If still actively listening (no silence detected yet)
            else:
                # =======================================================
                # FIX 3: THE VOSK RAM LEAK WATCHDOG
                # =======================================================
                # If there is constant ambient noise (like a fan), AcceptWaveform never
                # detects silence, so it never returns True. The internal Kaldi lattice
                # keeps eating RAM indefinitely until the Pi Zero crashes.
                # We check the length of the string to see if the buffer is getting too large.
                if len(self.rec.PartialResult()) > 150:
                    logging.debug("STT: Background noise buffer filled. Flushing RAM Lattice.")
                    self.rec.Reset()

            return None

        except Exception as e:
            logging.error(f"STT FUSE TRIPPED: Audio processing error: {e}")
            return None
