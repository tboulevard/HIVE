# coding=utf-8
from __future__ import print_function  # Python 2/3 compatibility
import boto3
from botocore.exceptions import ClientError
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_model import ui
from decimal import Decimal
import time
import random
import requests

dynamoDB = boto3.resource('dynamodb', region_name='us-west-2')
dynamoTable = dynamoDB.Table('hiveDB')

# -- Constants -- #
SKILL_NAME = "Hive"

# Speech output
HELP_MESSAGE_VERBOSE = (
        "You can start by asking to run your devices in ECO mode, by saying 'turn on eco mode'. %s will "
        "automatically track your total energy saved, all you need to do is ask 'How am I doing' to hear it" % SKILL_NAME)
LAUNCH_MESSAGE = ("Welcome to %s." % SKILL_NAME)
HELP_REPROMPT_MESSAGE = "You can try asking HIVE to turn on eco mode, ask how am I doing, what's my tier status, " \
                        "or simply ask for energy saving tips "
STOP_CANCEL_MESSAGE = ("Thanks for using %s." % SKILL_NAME)
EXCEPTION_MESSAGE = ("Sorry, there was some problem with %s. Please try again." % SKILL_NAME)

# Re-prompts
RE_PROMPTS = [
    "You can try asking about your current eco mode session.",
    "Try asking for an energy saving suggestion.",
    ("Ask, 'How am I doing' to get a summary of your energy usage since you started using %s" % SKILL_NAME)
]

# Intents / Slots
STATE_SLOT = "State"
MODE_SLOT = "Mode"
INFORMATION_SLOT = "InformationCategory"

# Conversion Rates
INCANDESCENT_LIGHTBULB_KWH_DAY = Decimal(1.44)
INCANDESCENT_LIGHTBULB_KWH_HOUR = Decimal(0.06)
INCANDESCENT_LIGHTBULB_KWH_MINUTE = Decimal(0.001)

# Session slot keys
CURR_INTENT_SLOT_KEY = "summary_intent_key"
SUMMARY_SLOT_VALUE = "summary"
TIPS_SLOT_VALUE = "tips"
ECO_SLOT_VALUE = "eco"

# API
API_TOKEN = "Token f5315ad7ca5b2d2637de37732d47c139b21eb4fc"

# Energy Saving Tips
ENERGY_SAVING_TIPS = [
    "Air dry dishes instead of using your dishwasher’s drying cycle. Just open the door after the rinse cycle and let "
    "Mother Nature do the rest. If you run your dishes in the evening, you can wake up to dry dishes without a single "
    "kilowatt being used. Doing this can cut dishwasher energy use 15-50%, depending on the machine.",

    "Lower the thermostat on your water heater to 120°F. The potential annual savings for every 10ºF you reduce the "
    "temperature is 12 to 30 dollars.",

    "Wash only full loads of dishes and clothes. Use cold water instead of hot or warm to save even more energy.",

    "Insulate heating ducts. In a typical house 20-30% of the air moving through the duct system is lost due to leaks.",

    "Plug home electronics into power strips and turn the power strips off when the plugged in equipment is not in use.",

    "Install low-flow showerheads. For maximum water efficiency, select a showerhead with a flow rate of less than "
    "2.5 gpm.",

    "Use Energy Star-qualified CFL and LED bulbs. These LEDs and CFLs use 20-25% of the energy of traditional "
    "incandescent bulbs.",

    "Turn off incandescent lights when you are not in the room. 90% of the energy they use is given off as heat, "
    "and only about 10% results in light.",

    "Install a programmable thermostat to lower utility bills and manage your heating and cooling systems "
    "efficiently. Turning your thermostat back 10°-15° for 8 hours can save 5%-15% a year on your heating bill.",

    "Sealing air leaks can result in up to 30% energy savings, according to energy.gov.",

    "Add an insulating blanket to older water heaters. This could reduce standby heat losses by 25%–45% and save "
    "about 4%–9% in water heating costs.",

    "Older appliances are often less energy efficient. Replace them with ENERGY STAR products.",

    "Use microwaves and toaster ovens to cook or warm leftovers. You’ll use less energy than cooking with a "
    "conventional oven.",

    "Clean/replace filters in furnace. Energy.gov recommends changing the filter every 3 months. A dirty filter slows "
    "down air flow and makes the system work harder.",

    "Avoid using the rinse hold setting on your dishwasher. This feature uses 3-7 more gallons of hot water per use.",

    "Take shorter showers. A typical shower head spits out an average of 2.5 gallons per minute. Reducing your shower "
    "time by 4 minutes per day may save 3650 gallons annually if you shower once a day."]

# -- Variables -- #
sb = SkillBuilder()


@sb.global_request_interceptor()
def request_logger(handler_input):
    print("global_response_interceptor {}".format(handler_input.request_envelope.request))


@sb.request_handler(can_handle_func=is_request_type("LaunchRequest"))
def launch_request_handler(handler_input):
    print("launch_request_handler {}".format(handler_input.request_envelope.request))

    response_builder = handler_input.response_builder

    total_energy = get_hive_table_item("1").get('TotalEnergySaved')
    energy_usage_info = get_energy_usage_information(total_energy)

    response_builder.set_card(
        ui.StandardCard(
            title=SKILL_NAME,
            text=LAUNCH_MESSAGE + " Here's your energy report:\n\n Your total energy saved is " + energy_usage_info
        )
    )

    response_builder.speak(LAUNCH_MESSAGE).ask(get_random_reprompt())
    return response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("StateChange"))
def statechange_intent_handler(handler_input):
    print("statechange_intent_handler {}".format(handler_input.request_envelope.request))

    state = \
        handler_input.request_envelope.request.intent.slots[STATE_SLOT].resolutions.resolutions_per_authority[0].values[
            0].value.id
    response_builder = handler_input.response_builder
    eco_mode_status = get_hive_table_item("1")

    speech_output = (
            "%s can't find the requested information. Try asking about suggestions, or your tier status." % SKILL_NAME)

    if "ON" == state:
        if eco_mode_status.get('EcoModeOn'):
            speech_output = "Eco mode is already on."
        else:
            toggle_eco_mode(True, 0)
            speech_output = "Ok, turning on Eco mode."
    elif "OFF" == state:
        if not eco_mode_status.get('EcoModeOn'):
            speech_output = "Eco mode is already off."
        else:
            elapsed_time = get_eco_mode_running_time(eco_mode_status.get('LastEcoModeActivation'))
            total_energy_saved = calculate_total_energy_saved(elapsed_time)
            toggle_eco_mode(False, total_energy_saved)

            m, s = divmod(elapsed_time, 60)
            h, m = divmod(m, 60)
            speech_output = (
                "Ok, turning off Eco mode. It ran for {} {} {}, saving a total of {:.2f} kilowatt hours.".format(
                    str(h) + " hours, " if h > 0 else "", str(m) + " minutes and" if m > 0 else "",
                    str(s) + " seconds" if s > 0 else "", total_energy_saved))

    response_builder.set_card(
        ui.StandardCard(
            title=SKILL_NAME,
            text=speech_output
        )
    )

    response_builder.speak(speech_output).ask(get_random_reprompt())
    return response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("RequestInformation"))
def request_information_intent_handler(handler_input):
    print("request_information_intent_handler {}".format(handler_input.request_envelope.request))

    information_category_id = \
        handler_input.request_envelope.request.intent.slots[INFORMATION_SLOT].resolutions.resolutions_per_authority[
            0].values[0].value.id
    response_builder = handler_input.response_builder

    speech_output = (
            "%s can't find the requested information." % SKILL_NAME)

    if information_category_id == "TIP":
        speech_output = get_random_energy_saving_tip()
    elif information_category_id == "SAVED":
        total_energy = get_hive_table_item("1").get('TotalEnergySaved')
        speech_output = "Your total energy saved is " + get_energy_usage_information(total_energy)
    elif information_category_id == "TIER":
        speech_output = "You are currently a Platinum tier energy saver. With 2 kilowatt hours saved in total, " \
                        "this puts you in the top 3% of energy savers in your area. "
    elif information_category_id == "ECO":
        if get_hive_table_item("1").get('EcoModeOn') is True:

            eco_mode_status = get_hive_table_item("1")
            elapsed_time = get_eco_mode_running_time(eco_mode_status.get('LastEcoModeActivation'))
            total_energy_saved = calculate_total_energy_saved(elapsed_time)
            energy_saved_info = get_energy_usage_information(total_energy_saved)

            m, s = divmod(elapsed_time, 60)
            h, m = divmod(m, 60)
            run_time_info = (
                "Eco mode is on. It has been running for {} {} {}, saving a total of".format(
                    str(h) + " hours, " if h > 0 else "", str(m) + " minutes and" if m > 0 else "",
                    str(s) + " seconds" if s > 0 else ""))
            speech_output = run_time_info + " " + energy_saved_info
        else:
            speech_output = "Eco mode is off. Would you like to turn it on?"
            handler_input.attributes_manager.session_attributes[CURR_INTENT_SLOT_KEY] = ECO_SLOT_VALUE
    elif information_category_id == "POW":
        current_power_usage = Decimal(send_get_powermeter_request()) / 1000
        speech_output = "You are currently using {:.2f} kilowatt hours".format(current_power_usage)

    response_builder.set_card(
        ui.StandardCard(
            title=SKILL_NAME,
            text=speech_output
        )
    )

    response_builder.speak(speech_output).ask(get_random_reprompt())
    return response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("Summary"))
def summary_intent_handler(handler_input):
    print("summary_intent_handler {}".format(handler_input.request_envelope.request))

    response_builder = handler_input.response_builder

    total_energy = get_hive_table_item("1").get('TotalEnergySaved')
    energy_usage_info = get_energy_usage_information(total_energy)

    handler_input.attributes_manager.session_attributes[CURR_INTENT_SLOT_KEY] = SUMMARY_SLOT_VALUE

    speech_output = "Your total energy saved is " + energy_usage_info + "Would you like to hear more?"

    response_builder.set_card(
        ui.StandardCard(
            title=SKILL_NAME,
            text=speech_output
        )
    )

    response_builder.speak(speech_output).ask("Would you like to hear more? If you're done, you can just say quit.")
    return response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("YesIntent"))
def yes_intent_handler(handler_input):
    print("yes_intent_handler {}".format(handler_input.request_envelope.request))

    response_builder = handler_input.response_builder

    speech_output = ("Sorry, %s couldn't fulfill your request. Please try again." % SKILL_NAME)
    reprompt = HELP_REPROMPT_MESSAGE

    if CURR_INTENT_SLOT_KEY in handler_input.attributes_manager.session_attributes:
        last_intent = handler_input.attributes_manager.session_attributes[CURR_INTENT_SLOT_KEY]
        if last_intent == SUMMARY_SLOT_VALUE:
            speech_output = "Last week you used 3.1 kilowatt hours, this week you used 2.8 kilowatt hours. Would you " \
                            "like a suggestion to help you reduce your energy usage? "
            handler_input.attributes_manager.session_attributes[CURR_INTENT_SLOT_KEY] = TIPS_SLOT_VALUE
        elif last_intent == TIPS_SLOT_VALUE:
            speech_output = get_random_energy_saving_tip()
        elif last_intent == ECO_SLOT_VALUE:
            toggle_eco_mode(True, 0)
            speech_output = "Ok, turning on Eco mode."

    response_builder.set_card(
        ui.StandardCard(
            title=SKILL_NAME,
            text=speech_output
        )
    )

    response_builder.speak(speech_output).ask(reprompt)
    return response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("NoIntent"))
def no_intent_handler(handler_input):
    print("no_intent_handler {}".format(handler_input.request_envelope.request))

    response_builder = handler_input.response_builder

    speech_output = ("Sorry, %s couldn't fulfill your request. Please try again." % SKILL_NAME)

    if CURR_INTENT_SLOT_KEY in handler_input.attributes_manager.session_attributes:
        speech_output = "Ok. Thanks for using Hive."
        response_builder.set_should_end_session(True)
        response_builder.speak(speech_output)
    else:
        response_builder.speak(speech_output).ask(get_random_reprompt())

    return response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("AMAZON.HelpIntent"))
def help_intent_handler(handler_input):
    print("help_intent_handler {}".format(handler_input.request_envelope.request))

    handler_input.response_builder.speak(HELP_MESSAGE_VERBOSE).ask(HELP_REPROMPT_MESSAGE)
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

    handler_input.response_builder.speak(EXCEPTION_MESSAGE)

    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_request_type("SessionEndedRequest"))
def session_ended_request_handler(handler_input):
    print("session_ended_request_handler {}".format(handler_input.request_envelope.request))

    return handler_input.response_builder.speak(STOP_CANCEL_MESSAGE).response


# Handler to be provided in lambda console.
handler = sb.lambda_handler()


# DynamoDB data retrieval/updating
def get_hive_table_item(userid):
    try:
        response = dynamoTable.get_item(
            Key={
                'UserId': userid
            }
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        ret = {
            'CurrentEnergyUsage': response['Item']['CurrentEnergyUsage'],
            'CurrentTier': response['Item']['CurrentTier'],
            'EcoModeOn': response['Item']['EcoModeOn'],
            'LastEcoModeActivation': response['Item']['LastEcoModeActivation'],
            'TotalEnergySaved': response['Item']['TotalEnergySaved']

        }
        return ret


def update_hive_table_item(userid, eco_mode_toggle, current_time, energy_saved):
    if current_time == 0 and energy_saved == 0:
        update_expression = "set EcoModeOn = :e"
        expression_attrs = {
            ':e': eco_mode_toggle
        }
    else:
        update_expression = "set EcoModeOn = :e, LastEcoModeActivation = :f, TotalEnergySaved = " \
                            "TotalEnergySaved + :g "
        expression_attrs = {
            ':e': eco_mode_toggle,
            ':f': current_time,
            ':g': energy_saved
        }

    response = dynamoTable.update_item(
        Key={
            'UserId': userid
        },
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_attrs,
        ReturnValues="UPDATED_NEW"
    )


# Helper functions
def toggle_eco_mode(eco_mode_state, total_energy_saved):
    # TODO: Make actual call to API to toggle state
    if eco_mode_state:
        update_hive_table_item("1", eco_mode_state, int(time.time()), 0)
    else:
        update_hive_table_item("1", eco_mode_state, 0, Decimal(str(round(total_energy_saved, 2))))


def get_eco_mode_running_time(last_activation):
    current_epoch = time.time()
    elapsed_time = int(current_epoch) - int(last_activation)
    return elapsed_time


def calculate_total_energy_saved(elapsed_time):
    # TODO: Calculate this from API
    return 0.00187470492884 * elapsed_time


def get_random_energy_saving_tip():
    random_index = random.randint(0, 15)
    return "From blog.constellation.com: " + ENERGY_SAVING_TIPS[random_index]


def get_random_reprompt():
    return RE_PROMPTS[random.randint(0, 2)]


def get_energy_usage_information(total_energy):
    total_energy = Decimal(total_energy)

    days_energy_saved = 0
    hours_energy_saved = 0
    minutes_energy_saved = 0

    # Could've used divmod here too ¯\_(ツ)_/¯
    if total_energy > INCANDESCENT_LIGHTBULB_KWH_DAY:
        days_energy_saved = Decimal(total_energy / INCANDESCENT_LIGHTBULB_KWH_DAY)
        days_remainder = Decimal(total_energy % INCANDESCENT_LIGHTBULB_KWH_DAY)

        hours_remainder = 0
        if days_remainder > INCANDESCENT_LIGHTBULB_KWH_HOUR:
            hours_energy_saved = Decimal(days_remainder / INCANDESCENT_LIGHTBULB_KWH_HOUR)
            hours_remainder = Decimal(days_remainder % INCANDESCENT_LIGHTBULB_KWH_HOUR)
        if hours_remainder > INCANDESCENT_LIGHTBULB_KWH_MINUTE:
            minutes_energy_saved = Decimal(hours_remainder / INCANDESCENT_LIGHTBULB_KWH_MINUTE)

    elif total_energy > INCANDESCENT_LIGHTBULB_KWH_HOUR:
        hours_energy_saved = Decimal(total_energy / INCANDESCENT_LIGHTBULB_KWH_HOUR)
        hours_remainder = Decimal(total_energy % INCANDESCENT_LIGHTBULB_KWH_HOUR)

        if hours_remainder > INCANDESCENT_LIGHTBULB_KWH_MINUTE:
            minutes_energy_saved = Decimal(hours_remainder / INCANDESCENT_LIGHTBULB_KWH_MINUTE)

    elif total_energy > INCANDESCENT_LIGHTBULB_KWH_MINUTE:
        minutes_energy_saved = Decimal(total_energy / INCANDESCENT_LIGHTBULB_KWH_MINUTE)

    if total_energy < 0.01:
        return "You haven't saved enough energy for us to track it just yet. Keep saving!"
    else:
        days_energy_saved = int(days_energy_saved)
        hours_energy_saved = int(hours_energy_saved)
        minutes_energy_saved = int(minutes_energy_saved)

        day_quantifier = "day"
        hour_quantifier = "hour"
        minute_quantifier = "minute"

        if days_energy_saved == 1:
            day_quantifier = "day"
            hours_energy_saved = 0
            minutes_energy_saved = 0
        elif days_energy_saved > 1:
            day_quantifier = "days"
            hours_energy_saved = 0
            minutes_energy_saved = 0

        if hours_energy_saved == 1:
            hour_quantifier = "hour"
            minutes_energy_saved = 0
        elif hours_energy_saved > 1:
            hour_quantifier = "hours"
            minutes_energy_saved = 0

        if minutes_energy_saved == 1:
            minute_quantifier = "minute"
        elif minutes_energy_saved > 1:
            minute_quantifier = "minutes"

        return "{:.2f} kilowatt hours. That's like leaving a " \
               "60 watt light bulb on for {}{}{}. ".format(total_energy,
                                                           str(
                                                               days_energy_saved) + " " + day_quantifier if days_energy_saved > 0 else "",
                                                           str(

                                                               hours_energy_saved) + " " + hour_quantifier if hours_energy_saved > 0 else "",
                                                           str(

                                                               minutes_energy_saved) + " " + minute_quantifier if minutes_energy_saved > 0 else "")


# API Requests
def send_get_powermeter_request():
    try:
        response = requests.get(
            url="https://peahivemobilebackends.azurewebsites.net/api/v2.0/devices/powermeter/",
            headers={
                "Authorization": API_TOKEN,
                "Cookie": "ARRAffinity=ed046e026d44c6574298f9d5b1427792d762e4003b0fb8dca735c275a2959304",
            },
        )
        print('Response HTTP Status Code: {status_code}'.format(
            status_code=response.status_code))
        print('Response HTTP Response Body: {content}'.format(
            content=response.content))
        return response.json().get('powermeters')[0].get('grid_activepower')
    except requests.exceptions.RequestException:
        print('HTTP Request failed')
