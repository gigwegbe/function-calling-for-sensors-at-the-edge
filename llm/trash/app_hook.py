# from fastapi import FastAPI, Request
# import json
# import asyncio
# import httpx

# app = FastAPI()

# @app.post("/api/thingsboard-webhook")
# async def thingsboard_webhook(request: Request):
#     data = await request.json()
#     message = f"ThingsBoard Update: \n```json\n{json.dumps(data, indent=2)}\n```"

#     # Send this to your running Chainlit app (assuming it's listening for it)
#     async with httpx.AsyncClient() as client:
#         await client.post("http://localhost:8000/chainlit-message", json={"content": message})

#     return {"status": "success"}


from fastapi import FastAPI, Request
import json
import uvicorn
from llm.trash.http_chain import queue  # direct import (can also use Redis or db if running separately)

app = FastAPI()

@app.post("/api/thingsboard-webhook")
async def thingsboard_webhook(request: Request):
    data = await request.json()
    msg = f"ThingsBoard Update:\n```json\n{json.dumps(data, indent=2)}\n```"
    queue.append(msg)
    return {"status": "queued"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)

# {
#   "deviceId": "temp-01",
#   "entityName": "device",
#   "telemetry": "temperature",
#   "timestamp": "23-903",
#   "additionalInfo": "meta"
# }