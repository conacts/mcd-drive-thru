import pygame
import os
import openai
import time
import wave
import contextlib
import datetime
import google.cloud.texttospeech as tts
import json
import sounddevice as sd
import wavio as wv

freq = 44100
duration = 5

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

pygame.init()


def record_audio():
    filename = "audio/order.mp3"
    recording = sd.rec(int(duration * freq), samplerate=freq, channels=1)
    print("Recording Audio\n")
    sd.wait()
    wv.write(filename, recording, freq, sampwidth=2)
    return filename


def transcribe_audio(audio_file):
    audio_file = open(audio_file, "rb")
    transcript = openai.Audio.transcribe("whisper-1", audio_file).text
    return transcript


def place_mcdonalds_order(order, json_file=None):
    """Place an order at McDonald's and return the order details"""
    j = json.dumps(order, indent=2)
    print(j)
    # speak out loud 'I am placing your order right now'
    filename = text_to_wav(
        "en-US-Wavenet-F", "I am placing your order right now")
    audio_time = get_audio_length(filename)
    play_wav_file(filename)
    time.sleep(audio_time)
    return j


def get_audio_length(fname):
    with contextlib.closing(wave.open(fname, 'r')) as f:
        frames = f.getnframes()
        rate = f.getframerate()
        duration = frames / float(rate)
        return duration


def speak_text(text):
    filename = text_to_wav("en-US-Wavenet-F", text)
    audio_time = get_audio_length(filename)
    play_wav_file(filename)
    time.sleep(audio_time)


def end_order(json_file, order=None):
    speak_text("Thank you, please pull forward to the first window")
    exit("Order complete")


def append_chat_message(messages, role, user_input, function_name=None):
    if function_name:
        messages.append(
            {"role": role, "content": user_input, "name": function_name}
        )
    else:
        messages.append({"role": role, "content": user_input})
    return messages


def text_to_wav(voice_name: str, text: str):
    language_code = "-".join(voice_name.split("-")[:2])
    text_input = tts.SynthesisInput(text=text)
    voice_params = tts.VoiceSelectionParams(
        language_code=language_code, name=voice_name
    )
    audio_config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16)

    client = tts.TextToSpeechClient()
    response = client.synthesize_speech(
        input=text_input,
        voice=voice_params,
        audio_config=audio_config,
    )

    filename = f"audio/{voice_name}+{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    with open(filename, "wb") as out:
        out.write(response.audio_content)
        print(f'LOG: Generated speech saved to "{filename}"\n')
    return filename


def play_wav_file(filename):
    sound = pygame.mixer.Sound(filename)
    sound.play()
    pygame.mixer.music.stop()


def run_conversation(messages):
    # Step 1: send the conversation and available functions to GPT
    functions = [
        {
            "name": "place_mcdonalds_order",
            "description": "Place an order at McDonald's and return the order details. Only call this when the user has finalized their order and in your final response read them the price of their order as well.",
            "parameters": {
                    "type": "object",
                    "properties": {
                        "order": {
                            "type": "string",
                            "description": """The json format of the McDonald's order. It should include the items and customizations. The structure of the parameter 'order' is a json format including these elements:
{
    "order": {
        "customer vehicle": "Toyota Camry",
        "items": [
            "item 1": {
            "Item Name": "Big Mac",
            "Quantity": 1,
            "customizations": [
                "customization": "No Pickles"
                ],
            },
            "item 2": {
                "Item Name": "Fries",
                "Quantity": 1,
                "size": "Large",
                customizations: [
                    "customization": "Lots of salt"
                ],
            }
        ],
                            """,
                        },
                    },
                "required": ["order"],
            },
        },
        {
            "name": "end_order",
            "description": "Call this function after you confirm the customer's order. This will end the conversation.",
            "parameters": {
                    "type": "object",
                    "properties": {
                        "json_file": {
                            "type": "string",
                            "description": "The json format of the McDonald's order. It should include the items and customizations.",
                        },
                    },
                "required": ["json_file"],
            },
        },
    ]
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0613",
        messages=messages,
        functions=functions,
        function_call="auto",
    )
    response_message = response["choices"][0]["message"]

    # Step 2: check if GPT wanted to call a function
    if response_message.get("function_call"):

        # Step 3: call the function
        # Note: the JSON response may not always be valid; be sure to handle errors
        available_functions = {
            "place_mcdonalds_order": place_mcdonalds_order,
            "end_order": end_order,
        }
        function_name = response_message["function_call"]["name"]
        function_to_call = available_functions[function_name]
        print("Function called: " + function_name)
        function_args = json.loads(
            response_message["function_call"]["arguments"]
        )
        function_response = function_to_call(
            order=function_args.get("order"),
            json_file=function_args.get("json_file"),
        )

        # Step 4: send the info on the function call and function response to GPT
        # extend conversation with assistant's reply
        messages.append(response_message)
        append_chat_message(messages, "function",
                            function_response, function_name)
        print("FUNCTION CALLED: SUCCESS")
        second_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo-0613",
            messages=messages,
        )
        messages.append(second_response["choices"][0]["message"])
        # print(second_response["choices"][0]["message"].content)
        response_message = second_response["choices"][0]["message"]
    else:
        append_chat_message(messages, "assistant",
                            response_message.content)
        # print(response_message.content)
    return response_message, messages, True


transcript = transcribe_audio("audio/order.mp3")
messages = [
    {"role":
     "system", "content": "You are a helpful, drive through McDonald's assistant. Your goal is to take a customer's food order from items only on the McDonald's menu. Your goal is to have a short conversation with the customer and after you take their order, you will call the function to 'place_mcdonalds_order' where you will finalize the user's purchase. You must only talk about ordering food, item menu prices and nutritional information. Do not output nutrition information unless the customer explicitly asks about it. The camera also notes that they are driving a 2010 toyota camry, which must be noted on the order."
     },
    # {"role": "user", "content": transcript}
]

continue_conversation = True
while continue_conversation:
    audio = transcribe_audio(record_audio())
    print("You:", audio)
    append_chat_message(messages, "user", audio)
    response_message, messages, continue_conversation = run_conversation(
        messages)
    print("Assistant:", response_message.content)
    speak_text(response_message.content)

    '''
    continue_conversation = input(
        "Continue conversation? (y/n): ").lower()
    if continue_conversation == 'n':
        continue_conversation = False
    '''
