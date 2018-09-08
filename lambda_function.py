from __future__ import print_function  # Python 2/3 compatibility
import boto3
from botocore.exceptions import ClientError
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_model import ui
from decimal import Decimal
import time

dynamoDB = boto3.resource('dynamodb', region_name='us-west-2')
dynamoTable = dynamoDB.Table('hiveDB')

# -- Constants -- #
SKILL_NAME = "Hive"

# Speech output
HELP_MESSAGE_VERBOSE = (
        "Welcome to %s, you can start by asking to run your devices in eco mode, energy saving tips, "
        "and track your energy usage in comparison to people living in your area. " % SKILL_NAME)
HELP_MESSAGE = ("Welcome to the %s." % SKILL_NAME)
HELP_REPROMPT = "Help re-prompt"
STOP_CANCEL_MESSAGE = ("Thanks for using %s." % SKILL_NAME)
EXCEPTION_MESSAGE = ("Sorry, there was some problem with %s. Please try again." % SKILL_NAME)
FALLBACK_MESSAGE = "Fallback message"
FALLBACK_REPROMPT = "Fallback re-prompt"

# Intents / Slots
STATE_SLOT = "State"
INFORMATION_SLOT = "InformationCategory"

# -- Variables -- #
sb = SkillBuilder()


@sb.global_request_interceptor()
def request_logger(handler_input):
    print("global_response_interceptor {}".format(handler_input.request_envelope.request))


@sb.request_handler(can_handle_func=is_request_type("LaunchRequest"))
def launch_request_handler(handler_input):
    print("launch_request_handler {}".format(handler_input.request_envelope.request))

    # Handler for Skill Launch
    speech = ("Welcome to the %s." % SKILL_NAME)

    handler_input.response_builder.speak(
        speech + " " + HELP_MESSAGE).ask(HELP_MESSAGE)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("StateChange"))
def statechange_intent_handler(handler_input):
    print("statechange_intent_handler {}".format(handler_input.request_envelope.request))

    state = handler_input.request_envelope.request.intent.slots[STATE_SLOT].value
    response_builder = handler_input.response_builder
    eco_mode_on = get_eco_mode_status("1")

    speech_output = (
            "%s can't find the requested information. Try asking about suggestions, or your tier status." % SKILL_NAME)

    if "on" in state or "activate" in state:
        if eco_mode_on:
            speech_output = "Eco mode is already on."
        else:
            toggle_eco_mode_status("1", True)
            record_start_time("1")
            speech_output = "Ok, turning on Eco mode."
    elif "off" in state or "deactivate" in state:
        if not eco_mode_on:
            speech_output = "Eco mode is already off."
        else:
            toggle_eco_mode_status("1", False)
            elapsed_time = get_eco_mode_running_time("1")
            #TODO: Calculate this from API
            total_energy_saved = 0.00187470492884 * elapsed_time
            increment_total_energy_saved("1", total_energy_saved)
            m, s = divmod(elapsed_time, 60)
            h, m = divmod(m, 60)
            speech_output = (
                    "Ok, turning off Eco mode. It ran for {} {} {}, saving a total of {:.2f} kilowatt hours.".format(str(h) + " hours, " if h > 0 else "", str(m) + " minutes and" if m > 0 else "", str(s) + " seconds" if s > 0 else "", total_energy_saved))

    response_builder.set_card(
        ui.StandardCard(
            title=SKILL_NAME,
            text=speech_output  # ,
            # TODO: image=ui.Image(
            #    small_image_url="<Small Image URL>",
            #    large_image_url="<Large Image URL>"
            # )
        )
    )

    response_builder.speak(speech_output).ask("Reprompt here.")
    return response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("RequestInformation"))
def request_information_intent_handler(handler_input):
    print("request_information_intent_handler {}".format(handler_input.request_envelope.request))

    information = handler_input.request_envelope.request.intent.slots[INFORMATION_SLOT].value
    response_builder = handler_input.response_builder

    speech_output = (
            "%s can't find the requested information. Try asking about suggestions, or your tier status." % SKILL_NAME)

    if "tip" in information or "suggestion" in information:
        speech_output = "Try washing your clothes with cold water. Using warm or hot water " \
                        "takes about 4.5 kilowatt hours per load while using cold water takes about 0.3 kilowatt " \
                        "hours per load. Would you like to hear more? "
    elif "notification" in information:
        speech_output = "You have 1 notification: Your weekly energy report is ready. Would you like you hear it?"
    elif "total" in information or "energy save" in information:
        total_energy = get_total_energy_saved("1")
        speech_output = "Your total energy saved using eco mode is {:.2f} kilowatt hours. That's equivalent to leaving a" \
                        "standard 60 watt light bulb on for 3 days. ".format(total_energy)
    elif "tier" in information or "tear" in information:
        speech_output = "You are currently a Platinum tier energy saver. With 2 kilowatt hours saved in total, " \
                        "this puts you in the top 3% of energy savers in your area. "
    elif "eco mode" in information or "session" in information:
        if get_eco_mode_status("1") is True:
            speech_output = "Eco mode is on. Would you like to turn it off?"
        else:
            speech_output = "Eco mode is off. Would you like to turn it on?"

    response_builder.set_card(
        ui.StandardCard(
            title=SKILL_NAME,
            text=speech_output  # ,
            # TODO: image=ui.Image(
            #    small_image_url="<Small Image URL>",
            #    large_image_url="<Large Image URL>"
            # )
        )
    )

    response_builder.speak(speech_output).ask("Reprompt here.")
    return response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("AMAZON.HelpIntent"))
def help_intent_handler(handler_input):
    print("help_intent_handler {}".format(handler_input.request_envelope.request))

    handler_input.response_builder.speak(HELP_MESSAGE).ask(HELP_MESSAGE)
    return handler_input.response_builder.response


@sb.request_handler(
    can_handle_func=lambda input:
    is_intent_name("AMAZON.CancelIntent")(input) or
    is_intent_name("AMAZON.StopIntent")(input))
def cancel_and_stop_intent_handler(handler_input):
    print("cancel_and_stop_intent_handler {}".format(handler_input.request_envelope.request))

    return handler_input.response_builder.speak(STOP_CANCEL_MESSAGE).response


@sb.exception_handler(can_handle_func=lambda i, e: True)
def all_exception_handler(handler_input, exception):
    print("Encountered following exception: {}".format(exception))

    handler_input.response_builder.speak(EXCEPTION_MESSAGE).ask(EXCEPTION_MESSAGE)

    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_request_type("SessionEndedRequest"))
def session_ended_request_handler(handler_input):
    print("session_ended_request_handler {}".format(handler_input.request_envelope.request))

    return handler_input.response_builder.response


# Handler to be provided in lambda console.
handler = sb.lambda_handler()


# Custom function definitions
def get_eco_mode_status(userid):
    try:
        response = dynamoTable.get_item(
            Key={
                'UserId': userid
            }
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        return response['Item']['EcoModeOn']


def toggle_eco_mode_status(userid, toggle):
    response = dynamoTable.update_item(
        Key={
            'UserId': userid
        },
        UpdateExpression="set EcoModeOn = :e",
        ExpressionAttributeValues={
            ':e': toggle
        },
        ReturnValues="UPDATED_NEW"
    )


def record_start_time(userid):
    current_epoch = int(time.time())

    response = dynamoTable.update_item(
        Key={
            'UserId': userid
        },
        UpdateExpression="set LastEcoModeActivation = :e",
        ExpressionAttributeValues={
            ':e': current_epoch
        },
        ReturnValues="UPDATED_NEW"
    )


def get_eco_mode_running_time(userid):
    current_epoch = time.time()
    last_activation = 0

    try:
        response = dynamoTable.get_item(
            Key={
                'UserId': userid
            }
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        last_activation = response['Item']['LastEcoModeActivation']

    elapsed_time = int(current_epoch) - int(last_activation)
    return elapsed_time

def get_total_energy_saved(userid):
    try:
        response = dynamoTable.get_item(
            Key={
                'UserId': userid
            }
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        return response['Item']['TotalEnergySaved']


def increment_total_energy_saved(userid, energy_saved):
    # Hack because dynamoDB doesn't like floats
    formatted_energy_saved = Decimal(str(round(energy_saved, 2)))

    response = dynamoTable.update_item(
        Key={
            'UserId': userid
        },
        UpdateExpression="set TotalEnergySaved = TotalEnergySaved + :e",
        ExpressionAttributeValues={
            ':e': formatted_energy_saved
        },
        ReturnValues="UPDATED_NEW"
    )

#    for x in response:
#        print (x)
#        for y in response[x]:
#            print (y,':',response[x][y])

# -------Refactor
