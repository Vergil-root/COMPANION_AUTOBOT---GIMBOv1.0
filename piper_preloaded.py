import subprocess
import os
import logging

# Set up basic clean logging for the terminal output
logging.basicConfig(level=logging.INFO, format='%(message)s')

# ==============================================================================
# DIRECTORY & PATH CONFIGURATION
# ==============================================================================
# This is the folder where the Piper binary and models live
BASE_DIR = "/home/[USERNAME]/[your folder]"

# Specific file paths
PIPER_BIN = os.path.join(BASE_DIR, "piper")
MODEL_PATH = os.path.join(BASE_DIR, "en_US-kusal-medium.onnx") #you can download any model as your liking, just search them up, i liked kusals voice it was less pitchy and calm hence used it 
OUTPUT_DIR = "/home/[USERNAME]/[your folder]"

# Ensure the output directory exists before generating audio
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# ==============================================================================
# MOOD & VOICE PROFILES
# ==============================================================================
# Parameters:
# 'ls' (length_scale): Controls speed. Higher = slower, Lower = faster.
# 'ns' (noise_scale): Controls phoneme variance. Affects emotion and rhythm.
# use any sentence inside the "text": "[YOUR TEXT]"
# ==============================================================================
MOODS = {
    "idle1": {
        "ls": 1.20, 
        "ns": 0.8, 
        "text": "Well, I got to do something, but I like walking and exploring."
    },
    "idle2": {
        "ls": 1.20, 
        "ns": 0.8, 
        "text": "Feeling a little lively, mate."
    },
    "idle3": {
        "ls": 1.20, 
        "ns": 0.8, 
        "text": "The weather is so nice and quiet, I like peace."
    },
    "greeting": {
        "ls": 1.00, 
        "ns": 0.9, 
        "text": "Oh hello [CREATOR_NAME]! I hope you are fine."
    },
    "happy": {
        "ls": 1.00, 
        "ns": 0.9, 
        "text": "I'm feeling so happy and lively!"
    },
    "sad": {
        "ls": 1.50, 
        "ns": 0.6, 
        "text": "Feeling kinda alone, mate."
    },
    "curious": {
        "ls": 1.40, 
        "ns": 1.1, 
        "text": "Ooh I got to move a little bit, these wires are all feeling so weak."
    },
    "angry": {
        "ls": 1.00, 
        "ns": 1.2, 
        "text": "Hey! Don't make me angry!"
    },
    "sleepy": {
        "ls": 1.60, 
        "ns": 0.5, 
        "text": "Okay I will sleep now. Good night."
    },
    "low_battery": {
        "ls": 1.60, 
        "ns": 0.5, 
        "text": "I am feeling tired, can you check my batteries please?"
    },
    "hey mom": {
        "ls": 1.60, 
        "ns": 0.5, 
        "text": "Oh hello [MOM_NAME]!"
    },
    "hey dad": {
        "ls": 1.60, 
        "ns": 0.5, 
        "text": "Oh hello [DAD_NAME]!"
    },
    "hey sister": {
        "ls": 1.60, 
        "ns": 0.5, 
        "text": "Oh hello [SISTER_NAME]!"
    },
}

# ==============================================================================
# AUDIO GENERATION ENGINE
# ==============================================================================
def generate_voice_library():
    """
    Iterates through the MOODS dictionary to generate raw WAV files using Piper TTS.
    Afterward, it uses FFmpeg to upscale the audio to match the robot's hardware specs.
    """
    # Crucial: LD_LIBRARY_PATH tells piper to look in BASE_DIR for the .so library files
    env_config = f"export LD_LIBRARY_PATH={BASE_DIR}:$LD_LIBRARY_PATH && "

    logging.info("--- Starting Raw Piper TTS Generation ---")
    
    for name, params in MOODS.items():
        output_file = os.path.join(OUTPUT_DIR, f"{name}.wav")

        # Construct the terminal command
        command = (
            f'{env_config} echo "{params["text"]}" | '
            f'"{PIPER_BIN}" --model "{MODEL_PATH}" '
            f'--length_scale {params["ls"]} '
            f'--noise_scale {params["ns"]} '
            f'--output_file "{output_file}"'
        )

        logging.info(f"Generating: {name}...")
        
        # Execute the TTS generation
        result = subprocess.run(command, shell=True, capture_output=True, text=True)

        if result.returncode != 0:
            logging.error(f"ERROR on {name}: {result.stderr}")

    logging.info("\n--- Upscaling to Final Product Specs (48kHz 32-bit LE Stereo) ---")
    
    for filename in os.listdir(OUTPUT_DIR):
        if filename.endswith(".wav"):
            filepath = os.path.join(OUTPUT_DIR, filename)
            temp_filepath = os.path.join(OUTPUT_DIR, f"temp_{filename}")
            
            # FFmpeg conversion to your strict hardware audio requirements
            # Uses a temporary file to avoid corruption, then overwrites the original
            ffmpeg_cmd = f'ffmpeg -y -loglevel error -i "{filepath}" -c:a pcm_s32le -ar 48000 -ac 2 "{temp_filepath}" && mv "{temp_filepath}" "{filepath}"'
            
            upscale_result = subprocess.run(ffmpeg_cmd, shell=True)
            
            if upscale_result.returncode == 0:
                logging.info(f"Finalized: {filename}")
            else:
                logging.error(f"Failed to finalize: {filename}")

# ==============================================================================
# EXECUTION
# ==============================================================================
if __name__ == "__main__":
    try:
        # Ensure the Piper binary has the required execute permissions
        os.chmod(PIPER_BIN, 0o755)
        
        # Start the generation pipeline
        generate_voice_library()
        
        logging.info("\nVoice Deployment Library Complete.")
        
    except Exception as e:
        logging.error(f"Critical Script Error: {e}")
