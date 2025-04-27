from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import Runnable
from langchain.chains.openai_functions import create_openai_fn_runnable
from pydantic import BaseModel, Field
from typing import List
import json
import os
import requests
from dotenv import load_dotenv
from langgraph.prebuilt import create_react_agent

# Load API keys and JSON
load_dotenv()
openai_api_key = os.getenv("OPENAI_PROJECT_API_KEY")
model = ChatOpenAI(api_key=openai_api_key, model="gpt-4o", temperature=0)

# Load farm JSON
with open("smaller_json.json") as f:
    farm_data = json.load(f)
farm_description = json.dumps(farm_data["farm"]["fields"], indent=2)

# Pydantic model
class SensorExtraction(BaseModel):
    sensor_id: List[str] = Field(..., description="List of sensor IDs relevant to the query")

# Prompt
system_message = SystemMessage(
    content=(
        "You are a smart farm assistant. Based on the user query and this farm data, extract sensor IDs.\n"
        "Respond ONLY with a JSON object in this format: {\"sensor_id\": [...]}\n\n"
        f"Farm field data:\n{farm_description}"
    )
)
human_message = HumanMessagePromptTemplate.from_template("{input}")
prompt_template = ChatPromptTemplate.from_messages([system_message, human_message])


sensor_extraction_runnable: Runnable = create_openai_fn_runnable([SensorExtraction], model, prompt_template)


@tool
def sensor_extraction(input: str) -> dict:
    """Extract relevant sensor IDs from a user query about farm fields."""
    return sensor_extraction_runnable.invoke({"input": input})



sensor_extraction_agent = create_react_agent(
    model=model,
    tools=[sensor_extraction],
    prompt="You are an expert in identifying relevant sensor IDs from natural language farm queries.",
    name="sensor_extraction_agent"
)

input_query = "Get all humidity reading in the field today."
inputs = {"messages": [HumanMessage(content=input_query)]}
result = sensor_extraction_agent.invoke(inputs)

# Print result
for msg in result["messages"]:
    msg.pretty_print()



# import openai
# import json
# import os
# from dotenv import load_dotenv

# # Load environment variables
# load_dotenv()
# openai_api_key = os.getenv("OPENAI_PROJECT_API_KEY")

# # Initialize OpenAI client
# client = openai.OpenAI(api_key=openai_api_key)

# # Load farm data and flatten for prompt
# with open("smaller_json.json") as f:
#     farm_data = json.load(f)
# farm_description = json.dumps(farm_data["farm"]["fields"], indent=2)
# # print(farm_description)

# @tool 
# def sensor_extraction(query):
#     """
#     Processes a user's query to identify and extract relevant sensor IDs from specified farm fields.

#     Args:
#         query (str): The user's input query describing the desired sensor information.

#     Returns:
#         dict: A JSON-formatted dictionary containing the sensor IDs corresponding to the fields mentioned in the query.
#     """
#     messages = [
#         {
#             "role": "system",
#             "content": (
#                 "You are a helpful assistant that identifies all relevant sensors mentioned in the user's request "
#                 "and returns them as a JSON object in this format: "
#                 '{"sensor_id": ["TEMP-0100", "HUM-0100", ...]}.\n\n'
#                 "Farm field data:\n"
#                 f"{farm_description}\n\n"
#                 "Match the user's field references with the field names in the data. "
#                 "Extract sensors only from the fields mentioned. "
#                 "If no valid field is provided, return an empty JSON array. "
#                 "Do not hallucinate sensor IDs."
#             ),
#         },
#         {"role": "user", "content": query},
#     ]

#     response = client.chat.completions.create(
#         model="gpt-4o",
#         messages=messages
#     )

#     response_message = response.choices[0].message.content.strip()

#     try:
#         return json.loads(response_message)
#     except json.JSONDecodeError:
#         return {"sensor_id": []}


# # # === EXAMPLE RUN ===
# input_query = "Get all humidity reading in the field today."
# inputs = {"messages": [HumanMessage(content=input_query)]}

# model = ChatOpenAI(api_key=openai_api_key, model="gpt-4o", temperature=0)

# sensor_extraction_agent = create_react_agent(
#     model=model,
#     tools=[sensor_extraction],
#     prompt="You are an expert in identifying relevant sensor IDs from natural language farm queries.",
#     name="sensor_extraction_agent"
# )

# result = sensor_extraction_agent.invoke(inputs)

# # Print result
# for msg in result["messages"]:
#     msg.pretty_print()
