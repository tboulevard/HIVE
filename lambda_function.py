from __future__ import print_function  # Python 2/3 compatibility
import boto3
from botocore.exceptions import ClientError
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.utils import is_request_type, is_intent_name

dynamoDB = boto3.resource('dynamodb', region_name='us-west-2')
dynamoTable = dynamoDB.Table('hiveDB')

SKILL_NAME = "PEA Hive"
HELP_MESSAGE = "Welcome to Hive, you can start by asking hive to run your devices in eco mode, energy saving tips, " \
               "and track your energy usage in comparison to people living in your area. "
HELP_REPROMPT = "Help reprompt"
STOP_MESSAGE = "Thanks for using Hive."
FALLBACK_MESSAGE = "Fallback message"
FALLBACK_REPROMPT = 'Fallback reprompt'

sb = SkillBuilder()

state_slot = "State"


@sb.global_request_interceptor()
def request_logger(handler_input):
    print("Request received: {}".format(handler_input.request_envelope.request))


@sb.request_handler(can_handle_func=is_request_type("LaunchRequest"))
def launch_request_handler(handler_input):
    print("HANDLER INPUT HERE:" + handler_input)
    # Handler for Skill Launch
    speech = "Welcome to the Hive using Ask SDK."

    handler_input.response_builder.speak(
        speech + " " + HELP_MESSAGE).ask(HELP_MESSAGE)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("StateChange"))
def statechange_intent_handler(handler_input):
    state = handler_input.request_envelope.request.intent.slots[state_slot].value
    speech_output = "inside get state change intent response, but no state match"
    eco_mode_on = get_eco_mode_status("1")

    if "on" in state or "activate" in state:
        if eco_mode_on:
            speech_output = "Eco mode is already on."
        else:
            toggle_eco_mode_status("1", True)
            speech_output = "Ok, turning on Eco mode."
    elif "off" in state or "deactivate" in state:
        if not eco_mode_on:
            speech_output = "Eco mode is already off."
        else:
            toggle_eco_mode_status("1", False)
            speech_output = "Ok, turning off Eco mode."

    handler_input.response_builder.speak(speech_output).ask("Reprompt here.")
    return handler_input.response_builder.response

    # return response(speech_response_with_card("StateChange", speech_output, "Intent input:" + state, True))


@sb.request_handler(can_handle_func=is_intent_name("RequestInformation"))
def get_request_information_intent_response(information):
    speech_output = "Hive can't find the requested information. Try asking about suggestions, or your tier status."
    end_session = True

    print("HANDLER INPUT HERE:" + information)

    if "tip" in information or "suggestion" in information:
        speech_output = "Have you tried washing your clothes with cold water instead of hot? Using warm or hot water " \
                        "takes about 4.5 kilowatt hours per load while using cold water takes about 0.3 kilowatt " \
                        "hours per load. Would you like to hear more? "
        end_session = False
    elif "notification" in information:
        speech_output = "You have 1 notification: Your weekly energy report is ready. Would you like you hear it?"
        end_session = False
    elif "total" in information or "energy save" in information:
        speech_output = "Your total energy saved using eco mode is 2 kilowatt hours. This is equivalent to leaving a " \
                        "standard 60 watt lightbulb on for 1 day. "
    elif "tier" in information or "tear" in information:
        speech_output = "You are currently a Platinum tier energy saver. With 2 kilowatt hours saved in total, " \
                        "this puts you in the top 3% of energy savers in your area. "
    elif "eco mode" in information or "session" in information:
        if get_eco_mode_status("1") is True:
            speech_output = "Eco mode is on. Would you like to turn it off?"
            end_session = False
        else:
            speech_output = "Eco mode is off. Would you like to turn it on?"
            end_session = False

    information.response_builder.speak(speech_output)
    return information.response_builder.response

    # return response(speech_response_with_card("Request", speech_output, "Intent input:" + information, end_session))


@sb.request_handler(can_handle_func=is_intent_name("AMAZON.HelpIntent"))
def help_intent_handler(handler_input):
    # Handler for Help Intent
    handler_input.response_builder.speak(HELP_MESSAGE).ask(HELP_MESSAGE)
    return handler_input.response_builder.response


@sb.request_handler(
    can_handle_func=lambda input:
    is_intent_name("AMAZON.CancelIntent")(input) or
    is_intent_name("AMAZON.StopIntent")(input))
def cancel_and_stop_intent_handler(handler_input):
    # Single handler for Cancel and Stop Intent
    speech_text = "Goodbye!"

    return handler_input.response_builder.speak(speech_text).response


@sb.exception_handler(can_handle_func=lambda i, e: True)
def all_exception_handler(handler_input, exception):
    # Catch all exception handler, log exception and
    # respond with custom message
    print("Encountered following exception: {}".format(exception))

    speech = "Sorry, there was some problem. Please try again."
    handler_input.response_builder.speak(speech).ask(speech)

    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_request_type("SessionEndedRequest"))
def session_ended_request_handler(handler_input):
    # Handler for Session End
    return handler_input.response_builder.response


def get_eco_mode_status(userId):
    try:
        response = dynamoTable.get_item(
            Key={
                'UserId': userId
            }
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        return response['Item']['EcoModeOn']


def toggle_eco_mode_status(userId, toggle):
    response = dynamoTable.update_item(
        Key={
            'UserId': userId
        },
        UpdateExpression="set EcoModeOn = :e",
        ExpressionAttributeValues={
            ':e': toggle
        },
        ReturnValues="UPDATED_NEW"
    )


#    for x in response:
#        print (x)
#        for y in response[x]:
#            print (y,':',response[x][y])

# -------Refactor


# Handler to be provided in lambda console.
handler = sb.lambda_handler()
