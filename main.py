"""Los Angeles Fire Department Help Desk Phone Line Chatbot
AUTHOR: Alex Marrero, University of Southern California, Fall 2024

This application uses Azure Communication Services, Azure Event Grid, and
Flask to handle incoming and outgoing calls, log tickets, and provide an IVR-like
(Interactive Voice Response) experience.

The user interacts via phone call, and the app receives events from Azure
to process user input (speech or DTMF tones), confirm employee details,
collect issue information, and generate a service ticket via email.
"""

from azure.eventgrid import EventGridEvent, SystemEventNames
from flask import Flask, Response, request, json, send_file, render_template, redirect, jsonify
from logging import INFO
from azure.communication.callautomation import (
    CallAutomationClient,
    CallConnectionClient,
    PhoneNumberIdentifier,
    RecognizeInputType,
    MicrosoftTeamsUserIdentifier,
    CallInvite,
    RecognitionChoice,
    DtmfTone,
    TextSource,
)
from azure.core.messaging import CloudEvent
import csv
from azure.communication.email import EmailClient
from word2number import w2n
import time


class Employee:
    """Represents an employee with associated contact and identification details.

    Attributes:
        employee_id (str): The unique employee ID.
        first_name (str): The employee's first name.
        last_name (str): The employee's last name.
        display_name (str): A formatted display name (usually first + last name).
        telephone_number (str): The employee's phone number.
        email_address (str): The employee's email address.
    """

    def __init__(self, employee_id, first_name, last_name, display_name, telephone_number, email_address):
        """Initialize an Employee instance.

        Args:
            employee_id (str): Unique identifier for the employee.
            first_name (str): Employee's first name.
            last_name (str): Employee's last name.
            display_name (str): Employee's display name.
            telephone_number (str): Employee's telephone number.
            email_address (str): Employee's email address.
        """
        self.employee_id = employee_id
        self.first_name = first_name
        self.last_name = last_name
        self.display_name = display_name
        self.telephone_number = telephone_number
        self.email_address = email_address

    def __repr__(self):
        """Return a string representation of the Employee."""
        return (f"Employee ID: {self.employee_id}, First Name: {self.first_name}, "
                f"Last Name: {self.last_name}, Display Name: {self.display_name}, "
                f"Telephone: {self.telephone_number}, Email: {self.email_address}")


class Ticket:
    """Represents a help desk ticket that captures user details and the issue.

    Attributes:
        name (str): Name of the employee who filed the ticket.
        id_num (str): Employee ID number.
        contact_method (str): Preferred contact method (e.g., 'phone', 'email').
        phone_number (str): The phone number to contact.
        email (str): The email address to contact.
        work_mode (str): The employee's work mode (e.g., 'office', 'telework').
        work_address (str): The physical location of the issue.
        urgency (str): Urgency level of the issue ('low', 'medium', 'high').
        issue_description (str): A description of the reported issue.
    """

    def __init__(self, name="", id_num="", contact_method="", phone_number="", email="", work_mode="", work_address="",
                 urgency="", issue_description=""):
        """Initialize a Ticket instance.

        Args:
            name (str): Employee name associated with the ticket.
            id_num (str): Employee ID number.
            contact_method (str): Preferred contact method.
            phone_number (str): Contact phone number.
            email (str): Contact email address.
            work_mode (str): Employee's work mode.
            work_address (str): Physical work address where issue occurs.
            urgency (str): Urgency level of the issue.
            issue_description (str): Description of the issue.
        """
        self.name = name
        self.id_num = id_num
        self.contact_method = contact_method
        self.phone_number = phone_number
        self.email = email
        self.work_mode = work_mode
        self.work_address = work_address
        self.urgency = urgency
        self.issue_description = issue_description

    def __repr__(self):
        return (f"Employee #: {self.id_num.upper()}"
                f"Name: {self.name}"
                f"Best method of contact: {self.contact_method.lower()}"
                f"Phone Number: {self.phone_number}"
                f"Email: {self.email.lower()}"
                f"Work location: {self.work_mode.lower()}"
                f"Work Address: {self.work_address.lower()}"
                f"Urgency tier: {self.urgency.lower()}"
                f"Description of Issue: {self.issue_description}")

    def __str__(self):
        """Return a user-friendly string representation of the Ticket."""
        return (f"Employee #: {self.id_num.upper()}\n"
                f"Name: {self.name}\n"
                f"Best method of contact: {self.contact_method.lower()}\n"
                f"Phone Number: {self.phone_number}\n"
                f"Email: {self.email.lower()}\n"
                f"Work location: {self.work_mode.lower()}\n"
                f"Work Address: {self.work_address.lower()}\n"
                f"Urgency tier: {self.urgency.lower()}\n"
                f"Description of Issue: {self.issue_description}")


class RetryObject:
    """Keeps track of retries for speech/choice recognition attempts during IVR interactions.

    Attributes:
        context (str): The current context or operation for which recognition is being attempted.
        choices (list): A list of RecognitionChoice objects or similar choices for the user.
        mode (str): The mode of input expected (e.g., 'speech', 'choices', 'speech_or_dtmf').
        counter (int): How many retries have been attempted.
    """

    def __int__(self, context="", choices=[], mode="", counter=0):
        """Initialize a RetryObject instance.

        Args:
            context (str): The current recognition context.
            choices (list): A list of choices to present to the user again if retries occur.
            mode (str): The mode of recognition ('speech', 'choices', 'speech_or_dtmf').
            counter (int): Retry attempt counter.
        """
        self.context = context
        self.choices = choices
        self.mode = mode
        self.counter = counter

    def __repr__(self):
        """Return a string representation of the RetryObject."""
        return (f"Retry Context = {self.context},"
                f"Mode: {self.mode}")

    def reset(self):
        """Reset the retry parameters to their initial values."""
        self.counter = 0
        self.mode = ""
        self.context = ""
        self.choices = []


# Employee data loading
employee_dict = {}
with open('EmployeeInfo/Employee_Information.csv', mode='r') as file:
    csv_reader = csv.DictReader(file)
    for row in csv_reader:
        employee = Employee(
            employee_id=row["ID"],
            first_name=row["FirstName"],
            last_name=row["LastName"],
            display_name=row["DisplayName"],
            telephone_number=row["TelephoneNumber"],
            email_address=row["EmailAddress"],
        )
        employee_dict[employee.employee_id] = employee

# Global variables for ticket processing and call handling
employee_ids = list(employee_dict.keys())
current_employee: Employee = None
new_phone_number = None
current_ticket = Ticket()
retry_object = RetryObject()

# PATH FOR FRONT-END PAGE
TEMPLATE_FILES_PATH = "template"

ACS_CONNECTION_STRING = "ENTER ACS CONNECTION STRING HERE"
ACS_PHONE_NUMBER = "ENTER ACS PHONE NUMBER HERE"
CALLER_PHONE_NUMBER = ""
CALLBACK_URI_HOST = "ENTER CALLBACK URL HERE"
CALLBACK_EVENTS_URI = CALLBACK_URI_HOST + "/api/callbacks"
COGNITIVE_SERVICES_ENDPOINT = "ENTER AZURE AI MULTI SERVICE RESOURCE ENDPOINT HERE"
SENDER_ADDRESS = "ENTER AZURE EMAIL RESOURCE MAIL-FROM ADDRESS HERE"
RECIPIENT_ADDRESS = "www.tech.footprints@fire.lacounty.gov"

# Prompts and constants
SPEECH_TO_TEXT_VOICE = "en-US-AvaMultilingualNeural"
MAIN_MENU = "Hello! Welcome to the Los Angeles Fire Department Help Desk Phone Line. ..."
CUSTOMER_QUERY_TIMEOUT = "I’m sorry I didn’t receive a response, please try again."
NO_RESPONSE = "I didn't receive an input ..."
INVALID_AUDIO = "I’m sorry, I didn’t understand your response, please try again."
CONFIRM_CHOICE_LABEL = "Confirm"
CANCEL_CHOICE_LABEL = "No"
TICKET_CHOICE_LABEL = "Ticket"
MCU_CHOICE_LABEL = "MCU"
RETRY_CONTEXT = "retry"
GOODBYE = "Goodbye for now!"
FATAL_ERROR_MESSAGE = "I apologize, but there was a systematic error in the call. Please call again."

call_automation_client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)

app = Flask(__name__, template_folder=TEMPLATE_FILES_PATH)


def get_menu_choices():
    """Get the set of RecognitionChoice options for the main menu.

    Returns:
        list: A list of RecognitionChoice objects for the main menu.
    """
    choices = [
        RecognitionChoice(label=TICKET_CHOICE_LABEL, phrases=["File ticket"], tone=DtmfTone.ONE),
        RecognitionChoice(label=MCU_CHOICE_LABEL,
                          phrases=["Speak to radio", "Speak to a person", "Speak to radio controlled unit",
                                   "Transfer to person"], tone=DtmfTone.ZERO),
    ]
    return choices


def get_confirm_choices():
    """Get the set of RecognitionChoice options for confirmation questions (yes/no).

    Returns:
        list: A list of RecognitionChoice objects for yes/no confirmation.
    """
    choices = [
        RecognitionChoice(label=CONFIRM_CHOICE_LABEL, phrases=["Yes", "First", "One"], tone=DtmfTone.ONE),
        RecognitionChoice(label=CANCEL_CHOICE_LABEL, phrases=["No", "Second", "Two"], tone=DtmfTone.TWO),
        RecognitionChoice(label=MCU_CHOICE_LABEL,
                          phrases=["Speak to radio", "Speak to a person", "Speak to radio controlled unit",
                                   "Transfer to person"], tone=DtmfTone.ZERO),
    ]
    return choices


def get_urgency_choices():
    """Get the set of RecognitionChoice options for selecting the urgency level.

    Returns:
        list: A list of RecognitionChoice objects for urgency selection.
    """
    choices = [
        RecognitionChoice(label="Low", phrases=["Low", "First", "One"], tone=DtmfTone.ONE),
        RecognitionChoice(label="Medium", phrases=["Medium", "Second", "Two"], tone=DtmfTone.TWO),
        RecognitionChoice(label="High", phrases=["High", "Third", "Three"], tone=DtmfTone.THREE)
    ]
    return choices


def get_workmode_choices():
    """Get the set of RecognitionChoice options for selecting the work mode (office/telework).

    Returns:
        list: A list of RecognitionChoice objects for work mode selection.
    """
    choices = [
        RecognitionChoice(label="Office", phrases=["Office", "In office", "On site", "On location", "First", "One"],
                          tone=DtmfTone.ONE),
        RecognitionChoice(label="Telework", phrases=["Telework", "Work from home", "Remote", "Second", "Two"],
                          tone=DtmfTone.TWO),
    ]
    return choices


def get_contact_method_choices():
    """Get the set of RecognitionChoice options for selecting the contact method (phone/email).

    Returns:
        list: A list of RecognitionChoice objects for contact method selection.
    """
    choices = [
        RecognitionChoice(label="Phone",
                          phrases=["Phone", "Telephone", "Call", "By phone", "By telephone", "First", "One"],
                          tone=DtmfTone.ONE),
        RecognitionChoice(label="Email", phrases=["Email", "By email", "Two"], tone=DtmfTone.TWO),
    ]
    return choices


def get_additional_request_choices():
    """Get the set of RecognitionChoice options for asking if user has additional requests.

    Returns:
        list: A list of RecognitionChoice objects for additional request confirmation.
    """
    choices = [
        RecognitionChoice(label="Yes",
                          phrases=["Yes", "Additional request", "Another ticket", "Additional ticket", "First", "One"],
                          tone=DtmfTone.ONE),
        RecognitionChoice(label="No", phrases=["No", "End call", "Finish", "Hang up", "Second", "Two"],
                          tone=DtmfTone.TWO),
    ]
    return choices


def get_media_recognize_choice_options(call_connection_client: CallConnectionClient, text_to_play: str,
                                       target_participant: str, choices: list, context: str):
    """Prompt the user with a set of menu choices (DTMF or speech).

    Args:
        call_connection_client (CallConnectionClient): The call connection client to send recognition requests.
        text_to_play (str): The prompt text to play to the user.
        target_participant (str): The participant's phone number or identifier.
        choices (list): A list of RecognitionChoice options.
        context (str): The operation context for this recognition attempt.
    """
    retry_object.context = context
    retry_object.mode = "choices"
    retry_object.choices = choices
    app.logger.info("Bot Dialogue: '%s'", text_to_play)
    play_source = TextSource(text=text_to_play, voice_name=SPEECH_TO_TEXT_VOICE)
    call_connection_client.start_recognizing_media(
        input_type=RecognizeInputType.CHOICES,
        target_participant=target_participant,
        choices=choices,
        play_prompt=play_source,
        interrupt_prompt=False,
        initial_silence_timeout=30,
        end_silence_timeout=2,
        operation_context=context
    )


def handle_play(call_connection_client: CallConnectionClient, text_to_play: str, operation_context: str = None):
    """Play a text-to-speech prompt to the user.

    Args:
        call_connection_client (CallConnectionClient): The call connection client.
        text_to_play (str): The message to play to the user.
        operation_context (str, optional): The context associated with this playback operation.
    """
    play_source = TextSource(text=text_to_play, voice_name=SPEECH_TO_TEXT_VOICE)
    call_connection_client.play_media(play_source, operation_context=operation_context)


def get_media_recognize_speech_input(call_connection_client: CallConnectionClient, text_to_play: str,
                                     target_participant: str, context: str):
    """Prompt the user for speech input only.

    Args:
        call_connection_client (CallConnectionClient): The call connection client.
        text_to_play (str): The prompt to the user.
        target_participant (str): The participant's identifier.
        context (str): The recognition context.
    """
    retry_object.context = context
    retry_object.mode = "speech"
    play_source = TextSource(text=text_to_play, voice_name=SPEECH_TO_TEXT_VOICE)
    call_connection_client.start_recognizing_media(
        input_type=RecognizeInputType.SPEECH,
        target_participant=target_participant,
        play_prompt=play_source,
        interrupt_prompt=False,
        end_silence_timeout=2,
        initial_silence_timeout=30,
        operation_context=context
    )
    app.logger.info("Start recognizing speech input")


def get_media_recognize_speech_or_dtmf_input(call_connection_client: CallConnectionClient, text_to_play: str,
                                             target_participant: str, context: str):
    """Prompt the user for speech or DTMF input.

    Args:
        call_connection_client (CallConnectionClient): The call connection client.
        text_to_play (str): The prompt to the user.
        target_participant (str): The participant's identifier.
        context (str): The recognition context.
    """
    retry_object.context = context
    retry_object.mode = "speech_or_dtmf"
    play_source = TextSource(text=text_to_play, voice_name=SPEECH_TO_TEXT_VOICE)

    # Determine max tones depending on context
    if context == "provide_eid":
        MAX_TONES = 6
    else:
        MAX_TONES = 10

    call_connection_client.start_recognizing_media(
        dtmf_max_tones_to_collect=MAX_TONES,
        input_type=RecognizeInputType.SPEECH_OR_DTMF,
        target_participant=target_participant,
        end_silence_timeout=2,
        play_prompt=play_source,
        initial_silence_timeout=30,
        interrupt_prompt=False,
        operation_context=context
    )
    app.logger.info("Start recognizing speech or DTMF input")


def modify_current_employee(employee: Employee):
    """Set the current employee under consideration.

    Args:
        employee (Employee): The employee object.
    """
    global current_employee
    current_employee = employee


def modify_new_phone_number(num: str):
    """Set a new phone number that was captured from the user.

    Args:
        num (str): The new phone number provided by the user.
    """
    global new_phone_number
    new_phone_number = num


def get_employee_by_id(employee_id: str):
    """Retrieve an Employee instance by its ID.

    Args:
        employee_id (str): The employee ID to look up.

    Returns:
        Employee or str: The Employee object if found, or "Employee not found." if not found.
    """
    return employee_dict.get(employee_id, "Employee not found.")


def reset_ticket():
    """Reset the global ticket to a new, empty Ticket."""
    global current_ticket
    current_ticket = Ticket()


def set_target_number(new_num: str):
    """Set the target phone number to dial or transfer the call.

    Args:
        new_num (str): A new phone number to target for the call.
    """
    global TARGET_PHONE_NUMBER
    TARGET_PHONE_NUMBER = new_num


def send_email(ticket=None):
    """Send an email with the current ticket details.

    Uses Azure Communication Services EmailClient to send the ticket information.

    Args:
        ticket (Ticket): The ticket object to send via email. Defaults to current_ticket.
    """
    global current_ticket
    if ticket is None:
        ticket = current_ticket

    retry_object.reset()
    POLLER_WAIT_TIME = 5
    message = {
        "senderAddress": SENDER_ADDRESS,
        "recipients": {
            "to": [{"address": RECIPIENT_ADDRESS}],
        },
        "content": {
            "subject": "Help desk ticket",
            "plainText": str(ticket),
        }
    }

    try:
        client = EmailClient.from_connection_string(ACS_CONNECTION_STRING)
        poller = client.begin_send(message)
        time_elapsed = 0
        while not poller.done():
            app.logger.info("Email send poller status: " + poller.status())
            poller.wait(POLLER_WAIT_TIME)
            time_elapsed += POLLER_WAIT_TIME

            if time_elapsed > 18 * POLLER_WAIT_TIME:
                raise RuntimeError("Polling timed out.")

        if poller.result()["status"] == "Succeeded":
            app.logger.info(f"Successfully sent the email (operation id: {poller.result()['id']})")
        else:
            raise RuntimeError(str(poller.result()["error"]))

    except Exception as ex:
        app.logger.info(ex)


@app.route('/outboundCall')
def outbound_call_handler():
    """Handle outbound call initiation.

    Creates a call to the TARGET_PHONE_NUMBER and sets up callbacks for further interaction.

    Returns:
        A Flask redirect response to the root endpoint.
    """
    target_participant = PhoneNumberIdentifier(TARGET_PHONE_NUMBER)
    source_caller = PhoneNumberIdentifier(ACS_PHONE_NUMBER)
    call_connection_properties = call_automation_client.create_call(
        target_participant,
        CALLBACK_EVENTS_URI,
        cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT,
        source_caller_id_number=source_caller
    )
    app.logger.info("Created call with connection id: %s", call_connection_properties.call_connection_id)
    return redirect("/")


@app.route('/inboundCall', methods=['POST'])
def inbound_call_handler():
    """Handle inbound calls from Azure Event Grid.

    This endpoint receives events indicating incoming calls (and validation events).
    On a SubscriptionValidationEvent, it returns the validation code.
    On an IncomingCall event, it answers the call and sets the caller as the target.

    Returns:
        A Flask redirect response after processing the event.
    """
    events = request.get_json()
    app.logger.info("Received Event: %s", events)

    for event in events:
        event_type = event.get('eventType')
        event_data = event.get('data', {})

        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            validation_code = event_data.get('validationCode')
            app.logger.info("Validation Code: %s", validation_code)
            return jsonify({"validationResponse": validation_code}), 200

        elif event_type == "Microsoft.Communication.IncomingCall":
            incoming_call_context = event_data.get('incomingCallContext')
            caller_id = event_data.get('from', {}).get('phoneNumber', 'Unknown').get('value', 'Unknown')
            set_target_number(caller_id)
            app.logger.info("Incoming call from: %s", caller_id)

            call_connection_properties = call_automation_client.answer_call(
                incoming_call_context,
                CALLBACK_EVENTS_URI,
                cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT
            )

            app.logger.info("Created call with connection id: %s", call_connection_properties.call_connection_id)

    return redirect("/")


# POST endpoint to handle callback events
@app.route('/api/callbacks', methods=['POST'])
def callback_events_handler():
    """Handle callback events from Azure Communication Services.

    This endpoint processes various events (Connected, RecognizeCompleted, RecognizeFailed, etc.)
    and orchestrates the IVR logic, prompting the user for inputs, confirming details,
    and logging the ticket.

    Returns:
        flask.Response: A 200 OK response after handling the events.
    """
    for event_dict in request.json:
        # Parsing callback events
        event = CloudEvent.from_dict(event_dict)
        call_connection_id = event.data['callConnectionId']
        app.logger.info("%s event received for call connection id: %s", event.type, call_connection_id)
        call_connection_client = call_automation_client.get_call_connection(call_connection_id)
        target_participant = PhoneNumberIdentifier(TARGET_PHONE_NUMBER)
        if event.type == "Microsoft.Communication.CallConnected":
            reset_ticket()
            app.logger.info("Starting recognize")
            get_media_recognize_choice_options(
                call_connection_client=call_connection_client,
                text_to_play=MAIN_MENU,
                target_participant=target_participant,
                choices=get_menu_choices(), context="main_menu")

        # Perform different actions based on DTMF tone received from RecognizeCompleted event
        elif event.type == "Microsoft.Communication.RecognizeCompleted":
            app.logger.info("Recognize completed: data=%s", event.data)
            retry_object.counter = 0
            # RECOGNIZED CHOICES INPUT
            if event.data['recognitionType'] == "choices":
                label_detected = event.data['choiceResult']['label'];
                if 'recognizedPhrase' in event.data['choiceResult']:
                    phraseDetected = event.data['choiceResult']['recognizedPhrase']
                else:
                    phraseDetected = label_detected

                app.logger.info("Recognition completed, labelDetected=%s, phraseDetected=%s, context=%s",
                                label_detected, phraseDetected, event.data.get('operationContext'))
                # MENU CONTEXTS HERE
                if event.data['operationContext'] == "main_menu":

                    if label_detected == TICKET_CHOICE_LABEL:
                        text_to_play = "Got it. You'd like to file a ticket. Is that correct?"
                        get_media_recognize_choice_options(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            choices=get_confirm_choices(), context="ticket")

                    elif label_detected == MCU_CHOICE_LABEL:
                        text_to_play = "Got it. You'd like to be transferred to a radio controlled unit. Is that " \
                                       "correct? "
                        get_media_recognize_choice_options(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            choices=get_confirm_choices(), context="transfer_to_mcu")

                if event.data['operationContext'] == "transfer_to_mcu":

                    if label_detected == CONFIRM_CHOICE_LABEL:
                        text_to_play = "This feature is currently in production still. Let's start again. How can I " \
                                       "help you today?. Please say 'file " \
                                       "ticket', if you would like to file a service ticket, or say 'radio' to be " \
                                       "connected to a live agent. Alternatively, you can press 'one' to file a " \
                                       "ticket, or press 'zero' to speak to an agent "

                        get_media_recognize_choice_options(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            choices=get_menu_choices(), context="main_menu")

                    else:
                        text_to_play = "Hmm. Okay. Let's start again. How can I help you today?. Please say 'file " \
                                       "ticket', if you would like to file a service ticket, or say 'radio' to be " \
                                       "connected to a live agent. Alternatively, you can press 'one' to file a " \
                                       "ticket, or press 'zero' to speak to an agent "
                        get_media_recognize_choice_options(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            choices=get_menu_choices(), context="main_menu")

                if event.data['operationContext'] == "ticket":
                    if label_detected == CONFIRM_CHOICE_LABEL:
                        text_to_play = "Great. Can you provide your employee ID number?"
                        get_media_recognize_speech_or_dtmf_input(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            context="provide_eid")
                    else:
                        text_to_play = "Hmm. Okay. Let's start again. How can I help you today?. Please say 'file " \
                                       "ticket', if you would like to file a service ticket, or say 'radio' to be " \
                                       "connected to a live agent. Alternatively, you can press 'one' to file a " \
                                       "ticket, or press 'zero' to speak to an agent "
                        get_media_recognize_choice_options(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            choices=get_menu_choices(), context="main_menu")

                if event.data['operationContext'] == "mcu":
                    if label_detected == CONFIRM_CHOICE_LABEL:
                        text_to_play = "Please hold while we connect you to the M.C.U.?"
                        # LOGIC TO TRANSFER TO M.C.U. number

                    else:
                        text_to_play = "Hmm. Okay. Let's start again. How can I help you today?"
                        get_media_recognize_choice_options(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            choices=get_menu_choices(), context="main_menu")

                if event.data['operationContext'] == "confirm_name":
                    if label_detected == CONFIRM_CHOICE_LABEL:
                        id_number = current_employee.employee_id
                        current_ticket.id_num = id_number
                        phone_number = current_employee.telephone_number
                        current_ticket.name = current_employee.display_name
                        if phone_number != "":
                            text_to_play = "Okay. I have a phone number here for you pulled from the employee " \
                                           "directory. Is this still " \
                                           "the best way to contact you? "
                            get_media_recognize_choice_options(
                                call_connection_client=call_connection_client,
                                text_to_play=text_to_play,
                                target_participant=target_participant,
                                choices=get_confirm_choices(), context="confirm_phone_number")
                        else:
                            text_to_play = "Okay. The employee directory does not have a phone number listed for you. " \
                                           "Can you say your phone number, or enter it on the dial pad? "
                            get_media_recognize_speech_or_dtmf_input(
                                call_connection_client=call_connection_client,
                                text_to_play=text_to_play,
                                target_participant=target_participant,
                                context="provide_new_phone_number")

                    else:
                        text_to_play = "Ah. It looks like you may have provided another employee's ID number. Let's " \
                                       "try again. Can you please say your employee ID number?"
                        get_media_recognize_speech_input(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            context="provide_eid")

                if event.data['operationContext'] == "confirm_phone_number":
                    if label_detected == CONFIRM_CHOICE_LABEL:
                        phone_number = current_employee.telephone_number
                        current_ticket.phone_number = phone_number
                        text_to_play = "Okay. I also have your email address on file from the directory. Is this " \
                                       "still the best email to reach you at? "
                        get_media_recognize_choice_options(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            choices=get_confirm_choices(),
                            context="confirm_email_on_file")

                    else:
                        text_to_play = "Okay. What is the best phone number for you?"
                        get_media_recognize_speech_or_dtmf_input(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            context="provide_new_phone_number")

                if event.data['operationContext'] == "confirm_new_phone_number":
                    if label_detected == CONFIRM_CHOICE_LABEL:
                        current_ticket.phone_number = new_phone_number
                        app.logger.info("Current ticket new phone number: " + current_ticket.phone_number)
                        if current_employee.email_address != "":
                            text_to_play = "Okay. I also have your email address on file from the directory. Is this " \
                                           "still the best email to reach you at?"
                            get_media_recognize_choice_options(
                                call_connection_client=call_connection_client,
                                text_to_play=text_to_play,
                                target_participant=target_participant,
                                choices=get_confirm_choices(),
                                context="confirm_email_on_file")

                        else:
                            text_to_play = "Okay. THe employee directory does not have an email address listed for " \
                                           "you. Can you please provide your email address now? "
                            get_media_recognize_speech_input(
                                call_connection_client=call_connection_client,
                                text_to_play=text_to_play,
                                target_participant=target_participant,
                                context="provide_new_email_address")

                    else:
                        text_to_play = "Hmm. Okay. Let's try that again. What is the best phone number for you?"
                        get_media_recognize_speech_or_dtmf_input(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            context="provide_new_phone_number")

                if event.data['operationContext'] == "confirm_email_on_file":
                    if label_detected == CONFIRM_CHOICE_LABEL:
                        current_ticket.email = current_employee.email_address
                        text_to_play = "Okay. Now, where are you working from? Say 'office' if you are working from an on " \
                                       "site location, or say 'telework' if you are working from a remote location, " \
                                       "or press 'one' for in-office, or 'two' for telework. "
                        get_media_recognize_choice_options(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            choices=get_workmode_choices(), context="confirm_work_location")

                    else:
                        text_to_play = "Okay. What is the best email address for you?"
                        get_media_recognize_speech_input(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            context="provide_new_email_address")

                if event.data['operationContext'] == "confirm_work_location":
                    work_mode = label_detected
                    current_ticket.work_mode = work_mode
                    text_to_play = "Okay. Now, What is the best way to contact you? Say 'email' if you would " \
                                   "like to be contacted via email, " \
                                   " or say 'phone' if you would like to be contacted via phone call. " \
                                   "Or, press 'one' for email, or press 'two' for phone. "
                    get_media_recognize_choice_options(
                        call_connection_client=call_connection_client,
                        text_to_play=text_to_play,
                        target_participant=target_participant,
                        choices=get_contact_method_choices(), context="confirm_contact_method")

                if event.data['operationContext'] == "confirm_contact_method":
                    contact_method = label_detected
                    current_ticket.contact_method = contact_method
                    text_to_play = "Okay. Almost done. Now, what is the physical address where the issue is occurring?"
                    get_media_recognize_speech_input(
                        call_connection_client=call_connection_client,
                        text_to_play=text_to_play,
                        target_participant=target_participant,
                        context="provide_work_address")

                if event.data['operationContext'] == "confirm_urgency":
                    urgency = label_detected
                    current_ticket.urgency = urgency
                    text_to_play = "Great. Now, can you clearly and succinctly desribe the issue that you are dealing " \
                                   "with today? "
                    get_media_recognize_speech_input(
                        call_connection_client=call_connection_client,
                        text_to_play=text_to_play,
                        target_participant=target_participant,
                        context="capture_issue")

                if event.data['operationContext'] == "confirm_additional_request":
                    if label_detected == "Yes":
                        send_email(current_ticket)
                        text_to_play = MAIN_MENU
                        get_media_recognize_choice_options(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            context="main_menu")

                    else:
                        handle_play(call_connection_client, GOODBYE, "end_call_log_ticket")

            # SPEECH INPUT RECOGNIZED
            elif event.data['recognitionType'] == "speech":
                text = event.data['speechResult']['speech'];
                app.logger.info("Recognition completed, text=%s, context=%s", text,
                                event.data.get('operationContext'));

                if event.data['operationContext'] == "provide_eid":
                    text = text.lower()
                    no_spaces_text = text.replace(" ", "")
                    final_id_num = no_spaces_text.replace(".", "")
                    temp_employee = get_employee_by_id(final_id_num)

                    if isinstance(temp_employee, Employee):
                        modify_current_employee(temp_employee)
                        text_to_play = 'Great. Give me a moment while I look up your information... Is your name ' + \
                                       current_employee.first_name + '?'
                        get_media_recognize_choice_options(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            choices=get_confirm_choices(), context="confirm_name")

                    else:
                        text_to_play = "I couldn't find an employee under that I.D. number. Let's try one more time. " \
                                       "Can you please say your employee ID number? "
                        get_media_recognize_speech_or_dtmf_input(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            context="provide_eid")

                if event.data['operationContext'] == "provide_new_phone_number":
                    num = text.replace(" ", "")
                    modify_new_phone_number(num)
                    app.logger.info("Phone number to confirm: " + num)
                    text_to_play = "You said " + new_phone_number + ". Is this correct?"
                    get_media_recognize_choice_options(
                        call_connection_client=call_connection_client,
                        text_to_play=text_to_play,
                        target_participant=target_participant,
                        choices=get_confirm_choices(), context="confirm_phone_number")

                if event.data['operationContext'] == "provide_new_email_address":
                    new_email_address = text
                    current_ticket.email = new_email_address
                    text_to_play = "Okay. Now, where are you working from? Say 'office' if you are working from an on " \
                                   "site location, or say 'telework' if you are working from a remote location, " \
                                   "or press 'one' for in-office, or 'two' for telework. "
                    get_media_recognize_choice_options(
                        call_connection_client=call_connection_client,
                        text_to_play=text_to_play,
                        target_participant=target_participant,
                        choices=get_workmode_choices(), context="confirm_work_location")

                if event.data['operationContext'] == "provide_work_address":
                    current_ticket.work_address = text
                    text_to_play = "Okay. Lastly, what is the urgency of this issue? Please say 'low', 'medium', " \
                                   "or 'high', or press 'one' for low, press 'two' for medium, or press 'three' for " \
                                   "high. Please note, when filing a high urgency ticket, the issue will be escalated " \
                                   "in the ticket queue. Please choose accordingly. "
                    get_media_recognize_choice_options(
                        call_connection_client=call_connection_client,
                        text_to_play=text_to_play,
                        target_participant=target_participant,
                        choices=get_urgency_choices(),
                        context="confirm_urgency")

                if event.data['operationContext'] == "capture_issue":
                    issue_description = text
                    current_ticket.issue_description = issue_description
                    text_to_play = "I understand. Sorry to hear that your dealing with that today. Ive logged this " \
                                   "issue successfully." \
                                   " Someone should be reaching out to you shortly, " \
                                   "via your provided best contact method. We look forward to getting this issue " \
                                   "resolved for you. Now, is there anything else I can assist you with? Say 'yes', " \
                                   "or feel free to hang up "
                    get_media_recognize_choice_options(
                        call_connection_client=call_connection_client,
                        text_to_play=text_to_play,
                        target_participant=target_participant,
                        choices=get_additional_request_choices(),
                        context="confirm_additional_request")
                    send_email(current_ticket)

            elif event.data['recognitionType'] == "dtmf":
                tones = event.data['dtmfResult']['tones']
                app.logger.info("Recognition completed, tones=%s, context=%s", tones,
                                event.data.get('operationContext'))
                num_string = ""

                if event.data['operationContext'] == "provide_eid" and len(tones) != 6:
                    text_to_play = "Employee ID numbers should have 6 digits. Let's try again. " \
                                   "Can you please say or enter your employee ID number? "
                    get_media_recognize_speech_or_dtmf_input(
                        call_connection_client=call_connection_client,
                        text_to_play=text_to_play,
                        target_participant=target_participant,
                        context="provide_eid")

                for tone in tones:
                    if tone == "pound" or tone == "asterick":
                        text_to_play = "You entered an invalid character. Employee ID numbers should consist of six " \
                                       "numerical digits. Let's try again. " \
                                       "Can you please say or enter your employee ID number? "
                        get_media_recognize_speech_or_dtmf_input(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            context="provide_eid")
                        break

                for tone in tones:
                    num_string += str(w2n.word_to_num(tone))

                if event.data['operationContext'] == "provide_eid":
                    id_raw = num_string.replace(" ", "")
                    id_no_periods = id_raw.replace(".", "")
                    final_id_num = "e" + id_no_periods
                    temp_employee = get_employee_by_id(final_id_num)

                    if isinstance(temp_employee, Employee):
                        modify_current_employee(temp_employee)
                        text_to_play = 'Great. Give me a moment while I look up your information... Is your name ' + \
                                       current_employee.first_name + '?'
                        get_media_recognize_choice_options(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            choices=get_confirm_choices(), context="confirm_name")

                    else:
                        text_to_play = "I couldn't find an employee under that I.D. number. Let's try one more time. " \
                                       "Can you please say your employee ID number? "
                        get_media_recognize_speech_or_dtmf_input(
                            call_connection_client=call_connection_client,
                            text_to_play=text_to_play,
                            target_participant=target_participant,
                            context="provide_eid")

                elif event.data['operationContext'] == "provide_new_phone_number":
                    modify_new_phone_number(num_string)
                    app.logger.info("Phone number to confirm: " + num_string)
                    text_to_play = "You said " + new_phone_number + ". Is this correct?"
                    get_media_recognize_choice_options(
                        call_connection_client=call_connection_client,
                        text_to_play=text_to_play,
                        target_participant=target_participant,
                        choices=get_confirm_choices(), context="confirm_new_phone_number")

            # FALL THROUGH
            else:
                handle_play(call_connection_client=call_connection_client, text_to_play=FATAL_ERROR_MESSAGE)

        elif event.type == "Microsoft.Communication.RecognizeFailed":
            retry_object.counter += 1
            if retry_object.counter > 2:
                handle_play(call_connection_client, "I apologize. It looks like we are having an issue understanding "
                                                    "each other. Let me connect you to a live agent. Goodbye for "
                                                    "now!", "retry_count_reached")

            failedContext = event.data['operationContext']
            if failedContext:
                speech_result = event.data.get('speechResult')
                if speech_result:
                    app.logger.info("Speech-to-Text Result: %s", speech_result)
                else:
                    app.logger.info("No speech result available in the event.")

                resultInformation = event.data['resultInformation']
                app.logger.info("Encountered error during recognize, message=%s, code=%s, subCode=%s",
                                resultInformation['message'],
                                resultInformation['code'],
                                resultInformation['subCode'])
                if (resultInformation['subCode'] in [8510, 8510]):
                    textToPlay = CUSTOMER_QUERY_TIMEOUT
                else:
                    textToPlay = INVALID_AUDIO

                if retry_object.mode == "choices":
                    get_media_recognize_choice_options(
                        call_connection_client=call_connection_client,
                        text_to_play=textToPlay,
                        target_participant=target_participant,
                        choices=retry_object.choices, context=retry_object.context)
                elif retry_object.mode == "speech":
                    get_media_recognize_speech_input(
                        call_connection_client=call_connection_client,
                        text_to_play=textToPlay,
                        target_participant=target_participant,
                        context=retry_object.context)

                else:
                    handle_play(call_connection_client,
                                FATAL_ERROR_MESSAGE,
                                "fatal_error")

        elif event.type in ["Microsoft.Communication.PlayCompleted", "Microsoft.Communication.PlayFailed"]:
            if event.type == "Microsoft.Communication.PlayFailed":
                handle_play(call_connection_client,
                            FATAL_ERROR_MESSAGE,
                            "fatal_error")
            app.logger.info("Terminating call")
            call_connection_client.hang_up(is_for_everyone=True)

        return Response(status=200)


# GET endpoint to render the menus
@app.route('/')
def index_handler():
    """Render the main index page.

    Returns:
        A rendered HTML template for the index page.
    """
    return render_template("index.html")


if __name__ == '__main__':
    app.logger.setLevel(INFO)
    app.run(port=8080)

