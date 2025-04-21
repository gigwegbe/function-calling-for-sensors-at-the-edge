import requests
import os
import json
import pandas as pd
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
import chainlit as cl
from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate
from langchain.agents.format_scratchpad.openai_tools import format_to_openai_tool_messages
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from langchain.agents import AgentExecutor
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
import os
from datetime import datetime
import plotly.express as px
# from langchain_experimental.sql import SQLDatabaseSequentialChain
from langchain_community.utilities.sql_database import SQLDatabase
# from langchain_experimental.sql import SQLDatabaseChain
os.environ['MPLCONFIGDIR'] = '/Users/george/.config/matplotlib'
import matplotlib.pyplot as plt

# Load environment variables
load_dotenv()

# API Endpoints
REALTIME_TELEMETRY_URL = "http://127.0.0.1:5000/realtime-telemetry"
DATABASE_TELEMETRY_URL = "http://127.0.0.1:5000/database-telemetry"

DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "thingsboard"
DB_USER = "thingsboard"
DB_PASSWORD = "postgres"
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
# db = SQLDatabase.from_uri(DATABASE_URL)

chat_history = []

# Initialize LLM
llm = ChatOpenAI(openai_api_key=os.getenv('OPENAI_PROJECT_API_KEY'), model="gpt-3.5-turbo")

# Define the prompt
template = '''
You are an expert assistant for sensor telemetry data. You can fetch 'realtime' or 'database' telemetry data.

For Farm data and best practices:
1. If realtime is in the user input use realtime api 
2. If database  is in the user input use database api 
3. For general knowledge about the farm use the content below: 

'''

# Load RAG Data for General Knowledge
with open('rag_data.md', 'r') as f:
    rag_data = f.read()

prompt = ChatPromptTemplate.from_messages([
    ("system", template + rag_data),
    MessagesPlaceholder(variable_name="chat_history"),
    ("user", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# Function to fetch telemetry data
def fetch_telemetry_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data[:10]
        return data
    except requests.RequestException as e:
        return {"error": str(e)}

@tool
def realtime_telemetry_data(): 
    """Fetch realtime telemetry data from the sensor."""
    return fetch_telemetry_data(REALTIME_TELEMETRY_URL)

@tool
def database_telemetry_data(): 
    """Fetch telemetry data from the database."""
    return fetch_telemetry_data(DATABASE_TELEMETRY_URL)

@cl.on_chat_start
def setup_chain():
    tools = [realtime_telemetry_data, database_telemetry_data]
    llm_with_tools = llm.bind_tools(tools)
    agent = ({
        "input": lambda x: x["input"],
        "agent_scratchpad": lambda x: format_to_openai_tool_messages(x["intermediate_steps"]),
        "chat_history": lambda x: x["chat_history"]
    } | prompt | llm_with_tools | OpenAIToolsAgentOutputParser())

    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    cl.user_session.set("llm_chain", agent_executor)

# @cl.on_chat_start
# async def setup_chain(sid, environ, auth=None):  # <--- update this line
#     tools = [realtime_telemetry_data, database_telemetry_data]
#     llm_with_tools = llm.bind_tools(tools)
#     agent = ({
#         "input": lambda x: x["input"],
#         "agent_scratchpad": lambda x: format_to_openai_tool_messages(x["intermediate_steps"]),
#         "chat_history": lambda x: x["chat_history"]
#     } | prompt | llm_with_tools | OpenAIToolsAgentOutputParser())

#     agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
#     cl.user_session.set("llm_chain", agent_executor)


@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Farm Summary",
            message="What kind of application can I create with Chainlit?",
            icon="/public/idea.svg",
        ),
        cl.Starter(
            label="Realtime Information",
            message="Give me realtime data.",
            icon="/public/write.svg",
        ),
        cl.Starter(
            label="How control a actuator?",
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
async def handle_message(message: cl.Message):
    user_message = message.content.lower()
    llm_chain = cl.user_session.get("llm_chain")
    result = llm_chain.invoke({"input": user_message, "chat_history": chat_history})
    chat_history.extend([
        HumanMessage(content=user_message),
        AIMessage(content=result["output"]),
    ])

    if "realtime" in user_message:
        data = realtime_telemetry_data.invoke({})
        if isinstance(data, dict) and "temperature" in data:
            df = pd.DataFrame(data["temperature"])
            formatted_data = df.to_markdown()
        else:
            formatted_data = json.dumps(data, indent=4)
        await cl.Message(content=f"**Realtime Telemetry Data:**\n{formatted_data}").send()
