
# alert_agent.py
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from alert_utils import run_alert_script
from config import OPENAI_API_KEY

model = ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4o")

# Now create Alert Agent
alert_agent = create_react_agent(
    model,
    tools=[run_alert_script],
    prompt="You are a alert assistant, you create alert by running the `run_alert_script` function",
    name="alert_agent"
)