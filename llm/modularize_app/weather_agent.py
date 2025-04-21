# weather_agent.py
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from weather_utils import get_weather_forecast, weather_search
from config import OPENAI_API_KEY

model = ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4o")

# Now create the agent using LangGraph's create_react_agent
weather_agent = create_react_agent(
    model,
    tools=[get_weather_forecast, weather_search],
    prompt="You are a weather assistant, if not city is provide use Kigali as the default city. Use the `weather_search` tool to answer weather-related queries and `get_weather_forecast` to answer weather-forecast related queries",
    name="weather_agent"
)