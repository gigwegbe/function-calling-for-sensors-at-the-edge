# # chainlit_app.py
# import chainlit as cl
# from fastapi import Request
# from chainlit.server import app as fastapi_app



# # This list will act like a message queue for simplicity
# incoming_messages = []

# @fastapi_app.post("/incoming-payload")
# async def receive_payload(request: Request):
#     data = await request.json()
#     incoming_messages.append(data)
#     return {"status": "received"}

# @cl.on_message
# async def handle_message(message: cl.Message):
#     await cl.Message(content=f"You said: {message.content}").send()

# @cl.step
# async def display_incoming():
#     if incoming_messages:
#         payload = incoming_messages.pop(0)
#         content = f"📩 Incoming JSON payload:\n```json\n{payload}\n```"
#         await cl.Message(content=content).send()

# chainlit_app.py
import chainlit as cl
from fastapi import Request
from datetime import datetime
from chainlit.server import app as fastapi_app

# Shared message queue
incoming_messages = []

# This route receives the JSON payload from Flask
@fastapi_app.post("/incoming-payload")
async def receive_payload(request: Request):
    data = await request.json()
    incoming_messages.append(data)
    return {"status": "received"}

# Chat session starts here
@cl.on_chat_start
async def start():
    await cl.Message(content="✅ Chat session started. Waiting for payload...").send()

    # Check every few seconds for new messages
    while True:
        if incoming_messages:
            data = incoming_messages.pop(0)
            

            device = data["text"]["originatorName"]
            sensor = data["text"]["originatorLabel"]
            alarm_type = data["text"]["name"]
            threshold = data["text"]["details"]["threshold"]
            value = data["text"]["details"]["value"]
            timestamp = data["text"]["details"]["timestamp"]

            # Create the message string
            message = f'🚨 Alarm triggered by {device} ({sensor}) at {timestamp}. Alarm type: "{alarm_type}", current value: {value}, exceeds threshold: {threshold}.'
            

            print(message)

            await cl.Message(
                content=message
            ).send()
        await cl.sleep(2)  # Poll every 2 seconds