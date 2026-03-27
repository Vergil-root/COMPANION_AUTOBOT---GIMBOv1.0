Hello guys,

All system files are included and i have edited the code to be more readable and easy to understand, also there are a few things you people should know:

1. the sound directory in the audio_dir is made by me using a code given by chatGPT to directly make pre loaded .wav sound files and include them in the brain by their name ex "good morning" or mom and dad or sister to address my family members too. you have to download the dir via the pi zero command line "wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx" and "wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx.json" into a pre made folder by yourself, can be named anything but remember to put the directory name same as the folder you downloaded the onnx and json files above. after that run the code piper_preloaded.py in the pi itself and make as many .wav sounds as you want (with the same file directory as above).

2. the motors are reversed in my robot as i wired them in the wrong order lol, taken care in the software i have mentioned it too, in the motion_engine.py

3. you have to download the vosk model too, which can be downloaded via the command line same as the piper model, but remember to use the exact same directories where you are storing all these models for STT and TTS, using "wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip" to download the zip and "unzip vosk-model-small-en-us-0.15.zip" to unzip it inside your pre made folder. 

4. thats it i guess for now ; ) you can make your own changes in the files are you have downloaded them. 

5. keep all the pi .py files inside a folder, name it anything you want but keep in mind to USE THIS FOLDERS NAME IN THE DIRECTORY GIVEN TO PIPER AND VOSK MODEL, or simply put the models inside this main robot folder, then you can just start the robot using "python3 main.py" in the command line when inside this robot folder. i have written them as your folder everywhere.

6. port='/dev/arduino_uno' this is /dev/ttyACM0 in the pi, i just made a custom directory for it to access, but remember not to plug in and out the arduino while the pi is ON, else the directory will change its name and you will get errors with serial communication.

7. while playing with arduino and pi type MCUs in a hybrid enviorment you have to be very careful, because one operates in a 5V domain and the latter operates in 3.3V, a single mistake can cost you your pi, or result in reboots and crashes. use level shifter ICs or resistor divider circuits when connecting both, or in my case i have used direct USB serial over UART comms. 
