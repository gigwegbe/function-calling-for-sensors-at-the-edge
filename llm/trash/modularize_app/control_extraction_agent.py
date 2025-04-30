# sensor_extraction_agent.py
import json
from openai import OpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain.agents.format_scratchpad.openai_tools import format_to_openai_tool_messages
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from langchain.agents import AgentExecutor
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from farm_data_utils import get_farm_details, tools
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)
model = ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-3.5-turbo") # Using gpt-3.5-turbo for this agent

def sensor_extraction(query):
    """
    Processes a user's query to identify and extract relevant sensor IDs from specified farm fields.

    Args:
        query (str): The user's input query describing the desired sensor information.

    Returns:
        str or dict: A JSON-formatted string or dictionary containing the sensor IDs corresponding to the fields mentioned in the query.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant that identifies all relevant sensors mentioned in the user's request "
                "and returns them as a JSON array of their IDs, in this format: "
                '{"actuator": ["PUMP-0100", "PUMP-0700","FD-0100","WV-0100"...]}. '
                "Match the user's field names to the following mappings:\n"
                "- F001: North Field\n"
                "- F002: Northeast Field\n"
                "- F003: East Field\n"
                "- F004: Southeast Field\n"
                "- F005: South Field\n"
                "- F006: Southwest Field\n"
                "- F007: West Field\n"
                "- F008: Northwest Field\n"
                "- F009: Central Field\n"
                "Extract actuator only from the fields mentioned. If no valid field is provided, return an empty JSON array.Do not hallucinate actuator device"
            ),
        },
        {"role": "user", "content": query},
    ]

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )

    response_message = response.choices[0].message

    if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
        tool_responses = []

        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            function_to_call = globals().get(function_name)
            if not function_to_call:
                continue  # Skip if the function is not defined

            function_args = json.loads(tool_call.function.arguments)
            function_response = function_to_call(**function_args)

            tool_responses.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": function_response,
            })

        # Append the assistant's message and all tool responses to the message history
        messages.append(response_message)
        messages.extend(tool_responses)

        # Send the updated message history back to the model
        second_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
        )

        return second_response.choices[0].message.content
    else:
        # If no tool call, attempt to parse the response as JSON
        try:
            return json.loads(response_message.content)
        except (json.JSONDecodeError, TypeError):
            return response_message.content

# Similarly, create the sensor extraction agent with a name
control_extraction_agent = create_react_agent(
    model=model,
    tools=[sensor_extraction],
    prompt="You are an expert in extracting sensor data from user queries.",
    name="sensor_extraction_agent"
)