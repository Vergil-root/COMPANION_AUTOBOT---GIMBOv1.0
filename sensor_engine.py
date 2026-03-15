# NOTE: this program is optional, you can include your sensor logic into the brain directly, i made this file as its easy to debug lol :)
import RPi.GPIO as GPIO
import time
import threading
import logging
from brain_enums import Event, EventType

# --- Optional I2C Dependency Check ---
try:
    import smbus
    HAS_SMBUS = True
except ImportError:
    logging.warning("SENSORS: python3-smbus missing. Battery monitoring disabled.")
    HAS_SMBUS = False

class SensorEngine:
    """
    Handles all external physical environment sensors.
    Runs background threads to continuously monitor HC-SR04 Ultrasonic 
    sensors (for peripheral vision) and the ADS1115 ADC (for battery biology).
    """
    def __init__(self, event_queue):
        self.event_queue = event_queue
        self.running = True

        # --- Ultrasonic Pin Definitions (BCM Mode) ---
        self.LEFT_TRIG = 23
        self.LEFT_ECHO = 24
        
        self.RIGHT_TRIG = 27
        self.RIGHT_ECHO = 22

        # --- GPIO Setup ---
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        GPIO.setup(self.LEFT_TRIG, GPIO.OUT)
        GPIO.setup(self.LEFT_ECHO, GPIO.IN)
        
        GPIO.setup(self.RIGHT_TRIG, GPIO.OUT)
        GPIO.setup(self.RIGHT_ECHO, GPIO.IN)

        # Settle triggers to LOW
        GPIO.output(self.LEFT_TRIG, False)
        GPIO.output(self.RIGHT_TRIG, False)

        # --- ADS1115 Battery Monitor Setup ---
        self.has_ads = False
        self.bus = None
        self.ADS_ADDRESS = 0x48
        self.VOLTAGE_MULTIPLIER = 4.0

        if HAS_SMBUS:
            try:
                self.bus = smbus.SMBus(1)
                # Test connection by attempting to read from the address
                self.bus.read_byte(self.ADS_ADDRESS)
                self.has_ads = True
                logging.info("SENSORS: Native ADS1115 I2C Monitor Online.")
            except Exception as e:
                # Silently fail if not connected, HAS_SMBUS remains False logically
                pass

        # Allow hardware to settle before starting read loops
        time.sleep(1)
        
        # Start background monitoring threads
        threading.Thread(target=self._sonic_worker, daemon=True).start()
        threading.Thread(target=self._battery_worker, daemon=True).start()

    # ================= ULTRASONIC LOGIC =================

    def get_raw_distance(self, trig_pin, echo_pin):
        """Fires a single physical acoustic ping and measures the echo time."""
        # Send 10 microsecond pulse to trigger
        GPIO.output(trig_pin, True)
        time.sleep(0.00001)
        GPIO.output(trig_pin, False)

        start_time = time.time()
        stop_time = time.time()
        
        # 40ms timeout prevents infinite loops if a sensor wire disconnects
        timeout = start_time + 0.04

        # Wait for the Echo pin to go HIGH (Start of ping)
        while GPIO.input(echo_pin) == 0:
            start_time = time.time()
            if start_time > timeout:
                return -1.0

        # Wait for the Echo pin to go LOW (End of ping)
        while GPIO.input(echo_pin) == 1:
            stop_time = time.time()
            if stop_time > timeout:
                return -2.0

        elapsed_time = stop_time - start_time
        
        # Sonic speed is 34300 cm/s. Divide by 2 for the round trip.
        return (elapsed_time * 34300) / 2.0

    def get_stable_distance(self, trig_pin, echo_pin):
        """
        Median filter.
        Takes 3 rapid readings and drops outliers caused by OS CPU thread interruptions.
        """
        readings = []
        
        for _ in range(3):
            d = self.get_raw_distance(trig_pin, echo_pin)
            # Ignore physically impossible readings (hardware glitches)
            if 2.0 < d < 400.0:
                readings.append(d)
            time.sleep(0.02)

        if len(readings) >= 2:
            readings.sort()
            # Return the median (middle) value
            return readings[len(readings) // 2]
            
        return 999.0

    # ================= ADC / BATTERY LOGIC =================

    def _read_ads1115(self, channel):
        """Reads a specific multiplexer channel from the ADS1115 ADC."""
        if not self.has_ads:
            return 0.0
            
        # Select the correct I2C configuration bytes based on requested channel
        if channel == 0:
            config = [0xC3, 0x83]
        elif channel == 1:
            config = [0xD3, 0x83]
        elif channel == 2:
            config = [0xE3, 0x83]
        else:
            return 0.0

        try:
            # Write config to the configuration register (0x01)
            self.bus.write_i2c_block_data(self.ADS_ADDRESS, 0x01, config)
            time.sleep(0.02) # Wait for conversion to complete
            
            # Read 2 bytes from the conversion register (0x00)
            data = self.bus.read_i2c_block_data(self.ADS_ADDRESS, 0x00, 2)
            
            # Reconstruct the 16-bit integer
            raw_val = (data[0] << 8) | data[1]
            
            # Convert 2's complement negative numbers
            if raw_val > 32767:
                raw_val -= 65535
                
            # Return voltage (Assuming +/- 4.096V Gain setting)
            return raw_val * (4.096 / 32768.0)
            
        except Exception:
            return 0.0

    # ================= BACKGROUND WORKERS =================

    def _sonic_worker(self):
        """Background thread continuously scanning left and right flanks."""
        left_strikes = 0
        right_strikes = 0

        while self.running:
            try:
                # Retrieve filtered distance readings
                d_left = self.get_stable_distance(self.LEFT_TRIG, self.LEFT_ECHO)
                d_right = self.get_stable_distance(self.RIGHT_TRIG, self.RIGHT_ECHO)

                # --- Left Confidence Tracking ---
                if d_left < 15.0:
                    left_strikes += 1
                else:
                    left_strikes = 0

                # --- Right Confidence Tracking ---
                if d_right < 15.0:
                    right_strikes += 1
                else:
                    right_strikes = 0

                # --- Event Triggering ---
                # A flank obstacle requires 2 consecutive strikes to trigger
                if left_strikes >= 2:
                    self.event_queue.put(Event(EventType.OBSTACLE, "LEFT"))
                    left_strikes = 0
                    time.sleep(1.0) # Hardware cooldown after detection
                    
                elif right_strikes >= 2:
                    self.event_queue.put(Event(EventType.OBSTACLE, "RIGHT"))
                    right_strikes = 0
                    time.sleep(1.0) # Hardware cooldown after detection
                    
                else:
                    # Give CPU thread back to the rest of the system
                    time.sleep(0.1)

            except Exception as e:
                if self.running:
                    logging.error(f"PI SENSOR FUSE: {e}")
                time.sleep(1.0)

    def _battery_worker(self):
        """Background thread monitoring the 3S Li-ion pack via ADC."""
        while self.running:
            if self.has_ads:
                try:
                    # Read cell group voltages
                    v_mcu = self._read_ads1115(0) * self.VOLTAGE_MULTIPLIER
                    v_arm = self._read_ads1115(1) * self.VOLTAGE_MULTIPLIER
                    v_leg = self._read_ads1115(2) * self.VOLTAGE_MULTIPLIER

                    # Determine overall pack health by the lowest cell
                    lowest_voltage = min(v_mcu, v_arm, v_leg)
                    
                    # Convert to 0-100% percentage (Assumes 3S pack: 12.6V Max, 9.6V Dead)
                    pct = ((lowest_voltage - 9.6) / (12.6 - 9.6)) * 100.0
                    
                    # Clamp values between 0 and 100
                    pct = max(0.0, min(100.0, pct))

                    self.event_queue.put(Event(EventType.BATTERY_UPDATE, pct))
                    
                except Exception as e:
                    if self.running:
                        logging.error(f"ADS1115 READ ERROR: {e}")
                        
            # Only poll battery every 5 seconds to save I2C bandwidth
            time.sleep(5.0)

    # ================= CLEANUP =================

    def stop(self):
        """Safely halts threads and releases GPIO pins."""
        self.running = False
        time.sleep(0.2)
        try:
            GPIO.cleanup()
        except Exception:
            pass
