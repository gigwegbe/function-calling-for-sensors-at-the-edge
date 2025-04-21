import os
import json
import uuid
from datetime import datetime
from typing import Dict, List, Literal, TypedDict, Optional, Any

# Updated imports based on your specifications
from langgraph.graph import StateGraph, START, END
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langchain.prompts import ChatPromptTemplate

from dotenv import load_dotenv

import requests

#load environment variables from .env file if available

load_dotenv()

# ThingsBoard settings (configurable via environment variables)
THINGSBOARD_URL = os.environ.get("THINGSBOARD_URL", "http://localhost:8080")
USERNAME = os.environ.get("THINGSBOARD_USERNAME", "tenant@thingsboard.org")
PASSWORD = os.environ.get("THINGSBOARD_PASSWORD", "tenant")
ROOT_RULE_CHAIN_ID = os.environ.get("ROOT_RULE_CHAIN_ID", "cf80ba30-1847-11f0-9b77-45d09c1e5989")
# tenantId = "337c4a58-be4d-45d6-9daf-f2e08991f0fd"


# State definition for the graph
class AgentState(TypedDict):
    messages: List[Any]
    sensor_field: Optional[str]
    threshold_value: Optional[float]
    tenant_id: Optional[str]
    jwt_token: Optional[str]
    context: Dict[str, Any]

# Helper ThingsBoard Functions (imported from your original script)
def get_jwt_token(username=USERNAME, password=PASSWORD):
    """Get JWT token from ThingsBoard"""
    url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {
        "username": username,
        "password": password
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json().get("token")
    else:
        return None

def create_rule_chain(jwt_token, rule_chain_data):
    """Create a rule chain in ThingsBoard"""
    url = f"{THINGSBOARD_URL}/api/ruleChain"
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }
    try:
        response = requests.post(url, headers=headers, json=rule_chain_data)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

def update_rule_chain_metadata(jwt_token, rule_chain_id, metadata):
    """Update rule chain metadata in ThingsBoard"""
    url = f"{THINGSBOARD_URL}/api/ruleChain/metadata"
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }
    try:
        response = requests.post(url, headers=headers, json=metadata)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

def get_rule_chain_metadata(jwt_token, rule_chain_id):
    """Get rule chain metadata from ThingsBoard"""
    url = f"{THINGSBOARD_URL}/api/ruleChain/{rule_chain_id}/metadata"
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

def add_forwarding_node(metadata, custom_rule_chain_id):
    """Add forwarding node to connect to custom rule chain"""
    current_time = int(datetime.now().timestamp() * 1000)

    forwarding_node = {
        "type": "org.thingsboard.rule.engine.flow.TbRuleChainInputNode",
        "name": "Check the condition",
        "configuration": {
            "forwardMsgToDefaultRuleChain": False,
            "ruleChainId": custom_rule_chain_id
        },
        "additionalInfo": {
            "description": "",
            "layoutX": 964,
            "layoutY": 145
        }
    }

    # Adding the forwarding node to the nodes list
    metadata["nodes"].append(forwarding_node)

    # Connection from the "Save Timeseries" node to the new forwarding node
    timeseries_node_index = next((index for (index, d) in enumerate(metadata["nodes"]) 
                              if d["type"] == "org.thingsboard.rule.engine.telemetry.TbMsgTimeseriesNode"), None)
    if timeseries_node_index is not None:
        metadata["connections"].append({
            "fromIndex": timeseries_node_index,
            "toIndex": len(metadata["nodes"]) - 1,
            "type": "Success"
        })

    return metadata

def build_temperature_rule_chain(sensor_field, tenant_id):
    """Build rule chain data structure"""
    rule_chain_data = {
        "name": f"{sensor_field.capitalize()} Monitoring Rule Chain",
        "type": "CORE",
        "root": False,
        "debugMode": False,
        "tenantId": {
            "id": tenant_id,
            "entityType": "TENANT"
        },
        "configuration": {},
        "additionalInfo": {}
    }
    return rule_chain_data

def build_rule_chain_metadata(rule_chain_id, sensor_field, threshold_value):
    """Build the metadata for the rule chain with appropriate nodes"""
    js_filter_script = f"return msg.{sensor_field} > {threshold_value};"

    nodes = [
        {
            "type": "org.thingsboard.rule.engine.filter.TbJsFilterNode",
            "name": f"{sensor_field.capitalize()} Filter",
            "configuration": {
                "jsScript": js_filter_script
            },
            "additionalInfo": {
                "layoutX": 260,
                "layoutY": 151,
                "description": f"Checks if {sensor_field} exceeds {threshold_value}"
            }
        },
        {
            "type": "org.thingsboard.rule.engine.action.TbCreateAlarmNode",
            "name": f"Create High {sensor_field.capitalize()} Alarm",
            "configuration": {
                "alarmType": f"High {sensor_field.capitalize()}",
                "alarmDetailsBuildJs": """
                var details = {};
                if (metadata.prevAlarmDetails) {
                    details = JSON.parse(metadata.prevAlarmDetails);
                    delete metadata.prevAlarmDetails;
                }
                return details;
                """,
                "severity": "CRITICAL",
                "propagate": True,
                "useMessageAlarmData": False
            },
            "additionalInfo": {
                "layoutX": 400,
                "layoutY": 100
            }
        },
        {
            "type": "org.thingsboard.rule.engine.action.TbClearAlarmNode",
            "name": f"Clear High {sensor_field.capitalize()} Alarm",
            "configuration": {
                "alarmType": f"High {sensor_field.capitalize()}",
                "alarmDetailsBuildJs": """
                var details = {};
                if (metadata.prevAlarmDetails) {
                    details = JSON.parse(metadata.prevAlarmDetails);
                    delete metadata.prevAlarmDetails;
                }
                return details;
                """,
                "propagate": True
            },
            "additionalInfo": {
                "layoutX": 400,
                "layoutY": 250
            }
        }
    ]

    connections = [
        {"fromIndex": 0, "toIndex": 1, "type": "True"},
        {"fromIndex": 0, "toIndex": 2, "type": "False"}
    ]

    metadata = {
        "ruleChainId": {
            "id": rule_chain_id,
            "entityType": "RULE_CHAIN"
        },
        "version": 1,
        "firstNodeIndex": 0,
        "nodes": nodes,
        "connections": connections,
        "ruleChainConnections": []
    }

    return metadata

# Simplified agent implementation using updated imports
def setup_system_prompt():
    """Create the system prompt for the agent"""
    return SystemMessage(content="""
    You are a smart farming and facility management assistant that helps users create alarms in ThingsBoard.
    
    You can help create sensor monitoring rule chains for:
    - soil_moisture: Monitors soil moisture levels (in percentage)
    - soil_temperature: Monitors soil temperature (in Celsius)
    - soil_conductivity: Monitors electrical conductivity of soil
    - field_air_humidity: Monitors air humidity (in percentage)
    
    Guide the user through the alarm setup process by collecting this information:
    1. The sensor field they want to monitor
    2. The threshold value that should trigger the alarm
    3. Their tenant ID in ThingsBoard
    
    Be helpful and conversational while collecting this information.
    """)

# JsonOutputParser to extract structured data from LLM responses
sensor_parser = JsonOutputParser(pydantic_object=None)

# Chat template to extract information
extract_info_prompt = ChatPromptTemplate.from_messages([
    ("system", """
    Extract information about sensor setup from the conversation. 
    Look for:
    1. Sensor field (one of: soil_moisture, soil_temperature, soil_conductivity, field_air_humidity)
    2. Threshold value (a numeric value)
    3. Tenant ID (UUID format)
    
    If you find any of these values, include them in your response.
    Return your response as a JSON object with these fields:
    {
        "sensor_field": "string or null",
        "threshold_value": number or null,
        "tenant_id": "string or null",
        "confidence": "high/medium/low for each field"
    }
    """),
    ("human", "{input}")
])

# LangGraph node functions
def agent_prompt(state: AgentState) -> AgentState:
    """Main node handling conversation with user"""
    messages = state["messages"]
    api_key = os.environ.get("OPENAI_PROJECT_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key not set. Please set the OPENAI_PROJECT_API_KEY environment variable.")
    
    # Configure the LLM
    llm = ChatOpenAI(api_key=api_key,model="gpt-4", temperature=0)
    
    # Create the agent's system message if it doesn't exist
    if not any(isinstance(msg, SystemMessage) for msg in messages):
        messages.insert(0, setup_system_prompt())
    
    # Get response from the LLM
    ai_response = llm.invoke(messages)
    messages.append(ai_response)
    
    # Return updated state
    return {**state, "messages": messages}

def extract_info(state: AgentState) -> AgentState:
    """Extract sensor information from the conversation"""
    messages = state["messages"]
    human_messages = [msg.content for msg in messages if isinstance(msg, HumanMessage)]
    
    # Initialize with existing values
    sensor_field = state.get("sensor_field")
    threshold_value = state.get("threshold_value")
    tenant_id = state.get("tenant_id")
    
    # Skip extraction if we already have all values
    if sensor_field and threshold_value is not None and tenant_id:
        return state
    
    # Use LLM to extract information
    llm = ChatOpenAI(model="gpt-4", temperature=0)
    extraction_chain = extract_info_prompt | llm | sensor_parser
    
    try:
        # Extract info from the latest conversation
        conversation_text = "\n".join(human_messages[-3:]) if len(human_messages) > 0 else ""
        extracted = extraction_chain.invoke({"input": conversation_text})
        
        # Update with any new information (only if not already set)
        if not sensor_field and extracted.get("sensor_field") and extracted.get("confidence", {}).get("sensor_field") != "low":
            sensor_field = extracted.get("sensor_field")
        
        if threshold_value is None and extracted.get("threshold_value") is not None and extracted.get("confidence", {}).get("threshold_value") != "low":
            threshold_value = float(extracted.get("threshold_value"))
        
        if not tenant_id and extracted.get("tenant_id") and extracted.get("confidence", {}).get("tenant_id") != "low":
            tenant_id = extracted.get("tenant_id")
            
    except Exception as e:
        # Fallback to regex extraction if parser fails
        if not sensor_field:
            valid_sensors = ["soil_moisture", "soil_temperature", "soil_conductivity", "field_air_humidity"]
            for msg in human_messages:
                for sensor in valid_sensors:
                    if sensor in msg.lower() or sensor.replace("_", " ") in msg.lower():
                        sensor_field = sensor
                        break
        
        if threshold_value is None and sensor_field:
            import re
            for msg in human_messages:
                number_matches = re.findall(r'\b\d+(?:\.\d+)?\b', msg)
                if number_matches:
                    try:
                        threshold_value = float(number_matches[0])
                        break
                    except ValueError:
                        continue
        
        if not tenant_id and sensor_field and threshold_value is not None:
            import re
            uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
            for msg in human_messages:
                uuid_matches = re.findall(uuid_pattern, msg, re.IGNORECASE)
                if uuid_matches:
                    tenant_id = uuid_matches[0]
                    break
    
    # Return updated state
    return {
        **state,
        "sensor_field": sensor_field,
        "threshold_value": threshold_value,
        "tenant_id": tenant_id
    }

def check_readiness(state: AgentState) -> Literal["continue_collection", "setup_alarm", "authenticate"]:
    """Determine next action based on collected information"""
    sensor_field = state.get("sensor_field")
    threshold_value = state.get("threshold_value")
    tenant_id = state.get("tenant_id")
    jwt_token = state.get("jwt_token")
    
    # Check if we need authentication
    if all([sensor_field, threshold_value is not None, tenant_id]) and not jwt_token:
        return "authenticate"
    
    # Check if we have all information needed
    if all([sensor_field, threshold_value is not None, tenant_id, jwt_token]):
        return "setup_alarm"
    
    # Continue collecting information
    return "continue_collection"

def authenticate(state: AgentState) -> AgentState:
    """Get JWT token for ThingsBoard API"""
    jwt_token = get_jwt_token()
    
    messages = state["messages"]
    if jwt_token:
        messages.append(SystemMessage(content="Authentication with ThingsBoard successful."))
    else:
        messages.append(SystemMessage(content="Authentication with ThingsBoard failed. Please check credentials."))
    
    return {**state, "jwt_token": jwt_token, "messages": messages}

def setup_alarm(state: AgentState) -> AgentState:
    """Create the rule chain and set up the alarm in ThingsBoard"""
    sensor_field = state["sensor_field"]
    threshold_value = state["threshold_value"]
    tenant_id = state["tenant_id"]
    jwt_token = state["jwt_token"]
    messages = state["messages"]
    
    # Build and create rule chain
    rule_chain_data = build_temperature_rule_chain(sensor_field, tenant_id)
    created_rule_chain = create_rule_chain(jwt_token, rule_chain_data)
    
    if created_rule_chain:
        custom_rule_chain_id = created_rule_chain.get("id", {}).get("id")
        if custom_rule_chain_id:
            # Update metadata for the custom rule chain
            metadata = build_rule_chain_metadata(custom_rule_chain_id, sensor_field, threshold_value)
            metadata_result = update_rule_chain_metadata(jwt_token, custom_rule_chain_id, metadata)
            
            # Get root rule chain metadata and add forwarding
            root_metadata = get_rule_chain_metadata(jwt_token, ROOT_RULE_CHAIN_ID)
            if root_metadata and metadata_result:
                updated_root_metadata = add_forwarding_node(root_metadata, custom_rule_chain_id)
                root_update_result = update_rule_chain_metadata(jwt_token, ROOT_RULE_CHAIN_ID, updated_root_metadata)
                
                if root_update_result:
                    status_message = f"""
                    Successfully set up alarm:
                    - Sensor: {sensor_field}
                    - Threshold: {threshold_value}
                    - Rule Chain ID: {custom_rule_chain_id}
                    """
                    messages.append(SystemMessage(content=status_message))
                else:
                    messages.append(SystemMessage(content="Failed to update root rule chain."))
            else:
                messages.append(SystemMessage(content="Failed to retrieve or update rule chain metadata."))
        else:
            messages.append(SystemMessage(content="Could not extract rule chain ID from response."))
    else:
        messages.append(SystemMessage(content="Failed to create custom rule chain."))
    
    return {**state, "messages": messages}

# Create simplified session management
sessions = {}

def build_farm_alarm_graph():
    """Create the LangGraph state graph for the conversation flow"""
    # Create the workflow
    workflow = StateGraph(AgentState)
    
    # Add nodes to the graph
    workflow.add_node("agent_prompt", agent_prompt)
    workflow.add_node("extract_info", extract_info)
    workflow.add_node("authenticate", authenticate)
    workflow.add_node("setup_alarm", setup_alarm)
    
    # Define the conditional edge
    workflow.add_conditional_edges(
        "extract_info",
        check_readiness,
        {
            "continue_collection": END,  # Change from "agent_prompt" to END
            "authenticate": "authenticate",
            "setup_alarm": "setup_alarm"
        }
    )
    
    # Add other edges
    workflow.add_edge(START, "agent_prompt")  # /////// debug Add explicit start 
    workflow.add_edge("agent_prompt", "extract_info")
    workflow.add_edge("authenticate", "setup_alarm")
    workflow.add_edge("setup_alarm", END)  # //////////////////////////Change to END instead of "agent_prompt"
    
    # Compile the graph
    app = workflow.compile()
    
    return app

# Build the graph
farm_alarm_graph = build_farm_alarm_graph()

# Function to handle user interactions
def chat_with_agent(user_input: str, session_id: str = None):
    """Process a user message and get a response from the agent"""
    if not session_id:
        session_id = str(uuid.uuid4())
    
    # Get existing state or create a new one
    if session_id in sessions:
        state = sessions[session_id]
        messages = state["messages"]
        messages.append(HumanMessage(content=user_input))
        new_state = {**state, "messages": messages}
    else:
        # First message in conversation
        new_state = {"messages": [HumanMessage(content=user_input)], "context": {}}
    
    # Run the graph with the input
    try:
        result = farm_alarm_graph.invoke(new_state)
        
        # Save state for next interaction
        sessions[session_id] = result
        
        # Get the AI's response
        messages = result["messages"]
        ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]
        
        # Return the most recent AI message
        if ai_messages:
            return ai_messages[-1].content, session_id
    except Exception as e:
        print(f"Error in graph execution: {str(e)}")
    
    return "I'm having trouble processing your request.", session_id