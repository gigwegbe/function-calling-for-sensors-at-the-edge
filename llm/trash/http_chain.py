import chainlit as cl
# from chainlit.server import app as chainlit_fastapi_app  # if needed for mounting

queue = ["ad","sf", "dsf"]

@cl.on_message
async def on_message(message: cl.Message):
    if queue:
        print(queue)
        content = queue.pop(0)

        await cl.Message(content=content).send()
    else:
        await cl.Message(content="Waiting for ThingsBoard updates...").send()


if __name__ == "__main__":
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)

# import chainlit as cl
# from fastapi import FastAPI, Request
# import json

# # Shared message queue
# queue = []

# # Get the FastAPI app from Chainlit
# app = cl.app()

# # ThingsBoard Webhook endpoint
# @app.post("/api/thingsboard-webhook")
# async def thingsboard_webhook(request: Request):
#     data = await request.json()
#     formatted = f"ThingsBoard Update:\n```json\n{json.dumps(data, indent=2)}\n```"

#     # Append to the queue so Chainlit can access it
#     queue.append(formatted)

#     return {"status": "queued"}

# # Chainlit UI message handler
# @cl.on_message
# async def on_message(message: cl.Message):
#     if queue:
#         content = queue.pop(0)
#         await cl.Message(content=content).send()
#     else:
#         await cl.Message(content="Waiting for ThingsBoard updates...").send()
