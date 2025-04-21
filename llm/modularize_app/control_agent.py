# control_agent.py
import json
from openai import OpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain.agents.format_scratchpad.openai_tools import format_to_openai_tool_messages
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from langchain.agents import AgentExecutor
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from farm_data_utils import get_farm_details, tools  # Ensure farm_data_utils.py exists with necessary tools
from config import OPENAI_API_KEY  # Ensure config.py exists with OPENAI_API_KEY

# Initialize OpenAI client and ChatOpenAI model
client = OpenAI(api_key=OPENAI_API_KEY)
model = ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-3.5-turbo")

def extract_actuator_ids(query: str) -> str:
    """
    Identifies and extracts relevant actuator IDs from a user's query based on farm field names.

    Args:
        query: The user's input query specifying the desired actuator information and farm fields.

    Returns:
        A JSON-formatted string containing a list of actuator IDs for the mentioned fields.
        Example: '{"actuator": ["PUMP-0100", "WV-0100"]}'
        Returns '{"actuator": []}' if no valid field is provided or no actuators are found.
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful assistant that identifies all relevant actuator devices mentioned in the user's request "
                "and returns them as a JSON array of their IDs, in this format: "
                '{{"actuator": ["ACTUATOR_ID_1", "ACTUATOR_ID_2", ...]}}. '
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
                "Extract actuator IDs only from the fields mentioned. If no valid field is provided, return an empty JSON array. "
                "Do not invent actuator device IDs.",
            ),
            ("human", "{query}"),
        ]
    )
    chain = prompt | model | OpenAIToolsAgentOutputParser()  # Assuming no tools are directly used here

    try:
        response = chain.invoke({"query": query})
        if isinstance(response, AIMessage) and response.content:
            return response.content
        else:
            return '{"actuator": []}'
    except Exception as e:
        print(f"Error processing query: {e}")
        return '{"actuator": []}'

# Create the control extraction agent using LangGraph's create_react_agent
control_extraction_agent = create_react_agent(
    model=model,
    tools=[extract_actuator_ids],  # Pass the function directly as a tool
    prompt="You are an expert in extracting actuator data from user queries.",
    name="actuator_extraction_agent"  # Renamed for clarity
)

if __name__ == "__main__":
    test_queries = [
        "Which actuators are in the North Field and East Field?",
        "Show me the actuators in F005.",
        "What about the West and Central fields?",
        "Get the actuators for an invalid field like F999.",
        "Any actuators?",
    ]

    for query in test_queries:
        print(f"\nQuery: {query}")
        result = extract_actuator_ids(query)
        print(f"Extracted Actuator IDs: {result}")

    # Example of using the LangGraph agent (requires a slightly different setup and likely more tools)
    # For this specific task, the direct function call might be more straightforward.
    # async def main():
    #     inputs = {"input": "Which actuators are in the South Field?"}
    #     response = await control_extraction_agent.ainvoke(inputs)
    #     print("\nLangGraph Agent Response:", response)

    # if __name__ == "__main__":
    #     import asyncio
    #     asyncio.run(main())