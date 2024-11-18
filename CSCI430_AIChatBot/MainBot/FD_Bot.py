import os
import azure.cognitiveservices.speech as speechsdk
import time
import csv
from azure.core.credentials import AzureKeyCredential
from azure.ai.language.conversations import ConversationAnalysisClient


class Employee:
    def __init__(self, employee_id, first_name, last_name, display_name, telephone_number, email_address):
        self.employee_id = employee_id
        self.first_name = first_name
        self.last_name = last_name
        self.display_name = display_name
        self.telephone_number = telephone_number
        self.email_address = email_address

    def __repr__(self):
        return (f"Employee(ID: {self.employee_id}, First Name: {self.first_name}, "
                f"Last Name: {self.last_name}, Display Name: {self.display_name}, "
                f"Telephone: {self.telephone_number}, Email: {self.email_address})")


# REPLACE KEY, REGION, VOICE PARAMETERS WITH AZURE CREDENTIALS FOR DEV / PROD PURPOSES
def get_speech_config(key='1K56b3rNYfXDpBCojVjDxspS9nljqelMOVRejP2poiv3vfZhXfIpJQQJ99AKAC4f1cMXJ3w3AAAYACOGKNLZ',
                      region='westus', voice='en-US-AvaMultilingualNeural'):
    speech_con = speechsdk.SpeechConfig(key, region)
    speech_con.speech_synthesis_voice_name = voice
    return speech_con


# REPLACE DEFAULT SPEAKER SETTING WITH CUSTOM SETTINGS. DOCUMENTATION TO COME
def get_audio_config():
    audio = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
    return audio


def get_speech_synthesizer(speech_con, audio_con):
    speech_synth = speechsdk.SpeechSynthesizer(speech_con, audio_con)
    return speech_synth


def get_speech_recognizer(speech_con):
    speech_rec = speechsdk.SpeechRecognizer(speech_con)
    return speech_rec


def get_ai_intent(text):
    key = "19d25483b1944f17a89f4273f89decbe"
    endpoint = "https://team-11-fd-aichatbot.cognitiveservices.azure.com/"
    deployment = "ChatBot_Model_1"
    project = "Team-11-FD-AIChatBot"

    clu_endpoint = os.environ["AZURE_CONVERSATIONS_ENDPOINT"]
    clu_key = os.environ["AZURE_CONVERSATIONS_KEY"]
    project_name = os.environ["AZURE_CONVERSATIONS_PROJECT_NAME"]
    deployment_name = os.environ["AZURE_CONVERSATIONS_DEPLOYMENT_NAME"]

    client = ConversationAnalysisClient(clu_endpoint, AzureKeyCredential(clu_key))
    with client:
        query = text
        result = client.analyze_conversation(
            task={
                "kind": "Conversation",
                "analysisInput": {
                    "conversationItem": {
                        "participantId": "1",
                        "id": "1",
                        "modality": "text",
                        "language": "en",
                        "text": query
                    },
                    "isLoggingEnabled": False
                },
                "parameters": {
                    "projectName": project_name,
                    "deploymentName": deployment_name,
                    "verbose": True
                }
            }
        )

        try:
            top_intent = result['result']['prediction']['topIntent']
            entities = result['result']['prediction']['entities']
            return top_intent.strip(), entities

        except KeyError as e:
            raise ValueError(f"Missing key in the provided result: {e}")


# GLOBALS
speech_config = get_speech_config()
audio_config = get_audio_config()
speech_synthesizer = get_speech_synthesizer(speech_config, audio_config)
speech_recognizer = get_speech_recognizer(speech_config)
employee_dict = {}
current_employee = None


def human_response():
    speech_recognition_result = speech_recognizer.recognize_once_async().get()
    text_buffer = speech_recognition_result.text.lower()
    print("HUMAN: " + text_buffer)
    return text_buffer


def bot_speak(text):
    speech_synthesis_result = speech_synthesizer.speak_text_async(text).get()
    print("BOT: " + text)
    time.sleep(.5)


def confirmation(text):
    bot_speak(text)
    response = human_response()
    if 'yes' in response:
        return True
    elif 'no' in response:
        return False
    else:
        return False


def bot_sorry(text=""):
    phrase = text + "Sorry about that. Let's try again."
    bot_speak(phrase)


def get_employee_by_id(employee_id):
    return employee_dict.get(employee_id, "Employee not found.")


def request_employee_id(text=""):
    running = True
    while running:
        phrase = 'Can you please provide your employee I.D. number?'
        bot_speak(phrase)
        id_num = human_response()
        dotted_id_num = ". ".join(str(id_num))
        no_spaces_text = id_num.replace(" ", "")
        final_id_num = no_spaces_text.replace(".", "")
        print(final_id_num)
        text = 'You said: ' + dotted_id_num + '. Is this correct?'
        flag = confirmation(text)
        if flag:
            text = 'Okay. Give me a moment to look up your employee information'
            bot_speak(text)
            employee = get_employee_by_id(final_id_num)
            text = 'Is your name ' + employee.first_name + '?'
            if confirmation(text):
                return employee
            else:
                text = "Ah. Lets try again."
                bot_speak(text)
                continue
        else:
            text = "Ah. Lets try again."
            bot_speak(text)


def request_issue_description(text=""):
    text = 'Great! I have your employee information pulled up here. Now, can you describe the ' \
           'issue that your having today? '
    bot_speak(text)
    issue = human_response()
    return issue


def issue_affirmation(issue):
    with open('issue_description.txt', 'w') as file:
        file.write(issue)

    text = 'I understand. Sorry to hear that your dealing with that today. Ive logged this issue ' \
           'successfully. Additionally, I have exported the issue description as a file for your ' \
           'convenience. Someone should be reaching out to you shortly, via your current LA ' \
           'County employee e-mail address. We look forward to getting this issue resolved for ' \
           'you. Thanks for calling! Goodbye for now!'

    bot_speak(text)


def modify_current_employee(employee):
    global current_employee
    current_employee = employee


def connect_to_rcu():
    text = "Please hold while we connect you to the R C U. "
    bot_speak(text)


def get_menu_selection():
    running = True
    while running:
        bot_speak("How can I help you?")
        selection_text = human_response()
        if 'ticket' in selection_text:
            text = "Got it. You'd like to file a ticket. Is that correct?"
            if confirmation(text):
                return 1
            else:
                bot_speak("Okay, let's try that again.")
                continue

        elif 'radio' in selection_text:
            text = "Okay. You'd like to speak to a radio controlled unit. Is that correct?"
            if confirmation(text):
                return 0
            else:
                bot_speak("Okay, let's try that again.")
                continue

        elif 'quit' or 'exit' or 'hang up' in selection_text:
            return 2
        else:
            bot_speak("I didn't hear a valid option. Let's try again.")
            continue


def main():
    with open('../EmployeeInfo/Employee_Information.csv', mode='r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            employee = Employee(
                employee_id=row["ID"],
                first_name=row["FirstName"],
                last_name=row["LastName"],
                display_name=row["DisplayName"],
                telephone_number=row["TelephoneNumber"],
                email_address=row["EmailAddress"]
            )
            employee_dict[employee.employee_id] = employee

    running = True
    text = 'Hello! Welcome to the Los Angeles Fire Department Help Desk Phone Line.'
    while running:
        bot_speak(text)
        selection = get_menu_selection()
        if selection == 2:
            running = False
            bot_speak('Goodbye!')

        elif selection == 1:
            employee = request_employee_id()
            modify_current_employee(employee)
            print(current_employee)
            issue_text = request_issue_description()
            issue_affirmation(issue_text)
            running = False

        elif selection == 0:
            connect_to_rcu()
            running = False


if __name__ == "__main__":
    main()
