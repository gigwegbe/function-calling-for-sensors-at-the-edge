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

# Load environment variables
load_dotenv()

# API Endpoints
REALTIME_TELEMETRY_URL = "http://127.0.0.1:5000/realtime-telemetry"
DATABASE_TELEMETRY_URL = "http://127.0.0.1:5000/database-telemetry"

chat_history = []

# LM_STUDIO_API_URL = "http://localhost:8000/v1"  # Ensure LM Studio server is running on this endpoint
LM_STUDIO_API_URL = "http://localhost:1234/v1"
llm = ChatOpenAI(
    api_key=os.getenv('LM_STUDIO_API_KEY', 'lm-studio'),  # Default key if not set
    base_url=LM_STUDIO_API_URL
)
# Initialize LLM
# llm = ChatOpenAI(openai_api_key=os.getenv('OPENAI_PROJECT_API_KEY'), model="gpt-3.5-turbo")

# Define the prompt
template = '''
<|begin_of_text|><|start_header_id|>system<|end_header_id|>
You are an expert assistant for sensor telemetry data. You can fetch 'realtime' or 'database' telemetry data.

For Farm data and best practices:
1. If realtime is in the user input use realtime api 
2. If database  is in the user input use database api 
3. For general knowledge about the farm use the content below: 
<|eot_id|><|start_header_id|>user<|end_header_id|>
{input}
<|eot_id|><|start_header_id|>assistant<|end_header_id|>
'''

# Load RAG Data for General Knowledge
with open('rag.md', 'r') as f:
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

    elif "database" in user_message:
        data = database_telemetry_data.invoke({})
        if isinstance(data, list):
            df = pd.DataFrame(data)
            formatted_data = df.to_markdown()
        else:
            formatted_data = json.dumps(data, indent=4)
        await cl.Message(content=f"**Database Telemetry Data:**\n{formatted_data}").send()

    else:
        # Output RAG-based responses in plain text
        await cl.Message(content=result["output"]).send()

# Run with: chainlit run sensor_chat.py -w --port 8000
#  chainlit run sensor_chat_full_v2.py -w --port 8000