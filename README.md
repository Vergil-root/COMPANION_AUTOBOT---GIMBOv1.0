Hello guys,

so all the files are included and i have used chatGPT to make the code more readable and easy to understand, also there are a few things you people should know:

1. the sound directory in the audio_dir is made by me using a code given by chatGPT to directly make pre loaded .wav sound files and include them in the brain by their name ex "good morning" or mom and dad or sister to address my family members too. you have to download the dir via the pi zero command line "wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx" and "wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx.json" into a pre made folder by yourself, can be named anything but remember to put the directory name same as the folder you downloaded the onnx and json files above. after that run the code piper_preloaded.py in the pi itself and make as many .wav sounds as you want (with the same file directory as above).

2. the motors are reversed in my robot as i wired them in the wrong order lol, taken care in the software i have mentioned it too, in the motion_engine.py

3. you have to download the vosk model too, which can be downloaded via the command line same as the piper model, but remember to use the exact same directories where you are storing all these models for STT and TTS, using "wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip" to download the zip and "unzip vosk-model-small-en-us-0.15.zip" to unzip it inside your pre made folder. 

4. thats it i guess for now ; ) you can make your own changes in the files are you have downloaded them. 
