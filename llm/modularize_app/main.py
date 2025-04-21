# main.py
import chainlit as cl
from langchain_core.messages import HumanMessage, AIMessage
from langchain.schema.runnable.config import RunnableConfig
from langgraph_supervisor import create_supervisor
from langchain_openai import ChatOpenAI
from sensor_extraction_agent import sensor_extraction_agent
from weather_agent import weather_agent
from alert_agent import alert_agent
from config import OPENAI_API_KEY
from chainlit import LangchainCallbackHandler

model = ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4o")

# Create the supervisor workflow
top_supervisor = create_supervisor(
    agents=[weather_agent, sensor_extraction_agent, alert_agent],
    model=model,
    prompt=(
        "You are a Farm Supervisor Agent. Your responsibilities include overseeing tasks related to sensor data retrieval and weather information. "
        "Delegate sensor-related queries to the sensor_extraction_agent, weather-related queries to the weather_agent and alert related queries to the alert_agent"
    )
).compile(name="SCADAgric")

@cl.on_chat_start
async def main():
    # await cl.Message(content="May I help you today?").send()
    pass

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Farm Summary",
            message="What all sensor data in all fields?",
            icon="/public/idea.svg",
        ),
        cl.Starter(
            label="Realtime Information",
            message="Give me realtime data.",
            icon="/public/write.svg",
        ),
        cl.Starter(
            label="How control a pump?",
            message="Control the actuactor.",
            icon="/public/learn.svg",
        ),
        cl.Starter(
            label="Get Farm Alert",
            message="Write a Chainlit hello world app.",
            icon="/public/terminal.svg",
        ),
        cl.Starter(
            label="Get Farm Weather",
            message="What is the weather in  Nyagatare District, Eastern Province, Rwanda.",
            icon="/public/cloudy.png",
        ),
    ]

@cl.on_message
async def on_message(message: cl.Message):
    config = {"configurable": {"thread_id": cl.context.session.id}}
    cb = LangchainCallbackHandler()
    final_answer = cl.Message(content="")

    async for output in top_supervisor.astream(
        {"messages": [HumanMessage(content=message.content)]},
        config=RunnableConfig(callbacks=[cb], **config)
    ):
        print(f"Supervisor Output Step: {output}")
        if isinstance(output, dict) and "supervisor" in output and "messages" in output["supervisor"] and output["supervisor"]["messages"]:
            last_supervisor_message = output["supervisor"]["messages"][-1]
            if isinstance(last_supervisor_message, AIMessage):
                await final_answer.stream_token(last_supervisor_message.content)
        elif isinstance(output, dict) and "messages" in output and output["messages"]:
            last_message = output["messages"][-1]
            if isinstance(last_message, AIMessage):
                await final_answer.stream_token(last_message.content)

    await final_answer.send()