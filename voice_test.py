import pyttsx3

voice = pyttsx3.init("sapi5")
voice.setProperty("rate", 170)
voice.say("Good evening, sir. Systems online.")
voice.runAndWait()