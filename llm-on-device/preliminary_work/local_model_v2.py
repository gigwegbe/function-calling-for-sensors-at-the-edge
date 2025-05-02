from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain.chains.openai_functions import create_openai_fn_runnable
from pydantic import BaseModel, Field
from typing import List
import json
import os
from dotenv import load_dotenv
from langgraph.prebuilt import create_react_agent

# Load .env if needed
load_dotenv()

# Local LM Studio setup
LM_STUDIO_API_URL = "http://localhost:1234/v1"
LOCAL_MODEL_NAME = "'lm-studio'"  # Or your preferred local model name

model = ChatOpenAI(
    base_url=LM_STUDIO_API_URL,
    api_key="not-needed",  # Placeholder
    model=LOCAL_MODEL_NAME,
    temperature=0
)

model = ChatOpenAI(
    api_key=os.getenv('LM_STUDIO_API_KEY', 'lm-studio'),  # Default key if not set
    base_url=LM_STUDIO_API_URL
)

# Load farm JSON data
with open("smaller_json.json") as f:
    farm_data = json.load(f)
farm_description = json.dumps(farm_data["farm"]["fields"], indent=2)

# Custom LLM prompt template (for LM Studio)
template = '''<|begin_of_text|><|start_header_id|>system<|end_header_id|>
You are an expert assistant for sensor telemetry data. You can fetch 'realtime' or 'database' telemetry data.
Farm field data:
{farm_description}
<|eot_id|><|start_header_id|>user<|end_header_id|>
{input}
<|eot_id|><|start_header_id|>assistant<|end_header_id|>'''

# Pydantic model for function calling
class SensorExtraction(BaseModel):
    sensor_id: List[str] = Field(..., description="List of sensor IDs relevant to the query")

# Use this to wrap the formatted string into a single message and send it
def build_custom_prompt(user_input: str) -> str:
    return template.format(
        input=user_input,
        farm_description=farm_description
    )

# Function-calling compatible wrapper
def custom_sensor_extraction_runnable(input_str: str):
    prompt = build_custom_prompt(input_str)
    message = HumanMessage(content=prompt)
    return model.invoke([message])

# Wrap in LangChain Runnable using OpenAI function call style
sensor_extraction_runnable = create_openai_fn_runnable(
    [SensorExtraction],
    model=model,
    prompt=build_custom_prompt  # We'll override input formatting
)

@tool
def sensor_extraction(input: str) -> dict:
    """Extract relevant sensor IDs from a user query about farm fields."""
    return sensor_extraction_runnable.invoke({"input": input})

# Create REACT agent
sensor_extraction_agent = create_react_agent(
    model=model,
    tools=[sensor_extraction],
    prompt="You are an expert in identifying relevant sensor IDs from natural language farm queries.",
    name="sensor_extraction_agent"
)

# Test input
user_query = "Get all humidity reading in the field today."
result = sensor_extraction_agent.invoke({"input": user_query})

# Print results
for msg in result["messages"]:
    msg.pretty_print()
