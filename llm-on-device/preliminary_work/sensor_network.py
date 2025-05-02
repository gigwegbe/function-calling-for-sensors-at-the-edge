import langgraph
# from langchain.chat_models import ChatOpenAI
import random 
from typing import Literal
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

# Initialize the model
# llm = ChatOpenAI(model_name="gpt-4-turbo")

# State 
class State(TypedDict): 
    graph_state: str 


# Define nodes (agents) - Conditional Edge 
def central_agent(state) -> Literal["database_agent", "realtime_agent", "rag_agent"]:

    # Often, we will use state to decide on the next node to visit
    query = state['graph_state']
    print(f"The finder -------------QUERY{query}-------------------- ")

    return "database_agent"
    # if "database" in query:
    #     return "database_agent"
    # elif "real-time" in query:
    #     return "realtime_agent"
    # else:
    #     return "rag_agent"


def rag_agent(state):
    print("---rag agent---")
    return {"output": f"RAG response for query: {state['query']}"}

def database_agent(state):
    print("---database agent---")
    return {"graph_state":state['graph_state']+ " database_agent"}

def database_tool(state):
    print("--database tool---")
    return {"graph_state":state['graph_state']+ " database_tool"}

def visualization_agent(state):
    print("---visualization agent---")
    return {"graph_state":state['graph_state']+ " visualization agent"}

def visualization_tool(state):
    print("---visualization tool---")
    return {"graph_state":state['graph_state']+ " visualization tool"}

def realtime_agent(state):
    print("---realtime agent---")
    return {"graph_state":state['graph_state']+ " realtime agent"}

def realtime_tool(state):
    print("---realtime tool---")
    return {"graph_state":state['graph_state']+ " realtime_tool"}

def output(state):
    print("---realtime tool---")
    return {"graph_state":state['graph_state']+ " output"}


# Create the graph
# workflow = langgraph.Graph()
workflow = StateGraph(State)
workflow.add_node("central_agent", central_agent)
workflow.add_node("rag_agent", rag_agent)
workflow.add_node("database_agent", database_agent)
workflow.add_node("database_tool", database_tool)
workflow.add_node("visualization_agent", visualization_agent)
workflow.add_node("visualization_tool", visualization_tool)
workflow.add_node("realtime_agent", realtime_agent)
workflow.add_node("realtime_tool", realtime_tool)
workflow.add_node("output", output)

# Define edges (flow)
workflow.add_edge(START, "central_agent")
workflow.add_conditional_edges("central_agent", central_agent)
workflow.add_edge("database_agent", "database_tool")
workflow.add_edge("database_tool", "visualization_agent")
workflow.add_edge("visualization_agent", "visualization_tool")
workflow.add_edge("realtime_agent", "realtime_tool")
workflow.add_edge("realtime_tool", "visualization_agent")
workflow.add_edge("rag_agent", "output")
workflow.add_edge("realtime_agent", "output")
workflow.add_edge("visualization_tool", "output")


# Compile and run
graph = workflow.compile()
