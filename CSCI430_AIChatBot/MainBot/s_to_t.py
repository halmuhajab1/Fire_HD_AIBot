import os
import azure.cognitiveservices.speech as speechsdk

speech_config = speechsdk.SpeechConfig('1K56b3rNYfXDpBCojVjDxspS9nljqelMOVRejP2poiv3vfZhXfIpJQQJ99AKAC4f1cMXJ3w3AAAYACOGKNLZ', 'westus')
speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config)
print("Speak into your microphone.")
speech_recognition_result = speech_recognizer.recognize_once_async().get()
print(speech_recognition_result.text)