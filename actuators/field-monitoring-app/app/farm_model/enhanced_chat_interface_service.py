from typing import Dict, List, Tuple, Any, Optional
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langchain.schema import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
import json
import os
import re
from time import sleep
from dotenv import load_dotenv
from farm_control_service import FarmControlService

load_dotenv()

import datetime

def _serialize_datetime(obj):
    """Helper function to serialize datetime objects."""
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()  # Convert to ISO 8601 string
    raise TypeError(f"Type {type(obj)} not serializable")


# Define state schema for the graph
class EnhancedActuatorControlState(BaseModel):
    """State for the farm control chat interface."""
    messages: List[Dict] = Field(default_factory=list)
    user_request: Optional[str] = None
    intent: Optional[Dict] = None
    scenario: Optional[str] = None
    context: Optional[Dict] = None
    plan: Optional[List[Dict]] = None
    execution_results: Optional[List[Dict]] = None
    impact_analysis: Optional[Dict] = None
    response: Optional[str] = None
    debug_logs: List[str] = Field(default_factory=list)
    error_occurred: bool = False
    error_message: Optional[str] = None

class FarmChatInterface:
    """
    Chat interface for interacting with the farm control system using natural language.
    Uses LangGraph to handle the conversation flow and process user requests.
    """
    
    def __init__(self, farm_control_service: FarmControlService, 
                 model_name: str = "gpt-4o", temperature: float = 0.1, api_key: str = None,
                 debug_mode: bool = True):
        """
        Initialize the chat interface.
        
        Args:
            farm_control_service: An instance of FarmControlService
            model_name: The LLM model to use
            temperature: Temperature setting for the LLM
            api_key: OpenAI API key
            debug_mode: Whether to log debug information
        """
        self.farm_control_service = farm_control_service
        self.api_key = api_key or os.environ.get("OPENAI_PROJECT_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
            
        self.llm = ChatOpenAI(api_key=self.api_key, model=model_name, temperature=temperature)
        self.debug_mode = debug_mode
        
        # Initialize a dictionary to track command execution status
        self.command_history = {}
        
        # Prefetch available information about the farm system
        self._prefetch_system_info()
        
        # Build the graph after initializing everything else
        self.graph = self._build_graph()
    
    def _log(self, message):
        """Log debug information if debug mode is enabled."""
        if self.debug_mode:
            print(f"[DEBUG] {message}")
    
    def _prefetch_system_info(self):
        """Prefetch basic system information to have on hand."""
        try:
            self.system_info = {
                "farms": self.farm_control_service.get_all_farms(),
                "fields": self.farm_control_service.get_all_fields(),
                "actuators": self.farm_control_service.get_all_actuators(),
                "resources": self.farm_control_service.get_all_resources()
            }
            self._log(f"Prefetched system info with {len(self.system_info['farms'])} farms, "
                     f"{len(self.system_info['fields'])} fields, "
                     f"{len(self.system_info['actuators'])} actuators, "
                     f"{len(self.system_info['resources'])} resources")
        except Exception as e:
            self._log(f"Error prefetching system info: {str(e)}")
            self.system_info = {}
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine for actuator control."""
        workflow = StateGraph(EnhancedActuatorControlState)
        
        # Define the nodes
        workflow.add_node("analyze_request", self._analyze_request)
        workflow.add_node("identify_scenario", self._identify_scenario)
        workflow.add_node("fetch_context", self._fetch_context)
        workflow.add_node("plan_actions", self._plan_actions)
        workflow.add_node("execute_actions", self._execute_actions)
        workflow.add_node("analyze_impacts", self._analyze_impacts)
        workflow.add_node("format_response", self._format_response)
        workflow.add_node("handle_error", self._handle_error)
        
        # Define the edges for normal flow
        workflow.add_edge(START, "analyze_request")
        workflow.add_edge("analyze_request", "identify_scenario")
        workflow.add_edge("identify_scenario", "fetch_context")
        workflow.add_edge("fetch_context", "plan_actions")
        workflow.add_edge("plan_actions", "execute_actions")
        workflow.add_edge("execute_actions", "analyze_impacts")
        workflow.add_edge("analyze_impacts", "format_response")
        workflow.add_edge("format_response", END)
        
        # Define error handling edges
        workflow.add_conditional_edges(
            "analyze_request",
            lambda state: "handle_error" if state.error_occurred else "identify_scenario"
        )
        workflow.add_conditional_edges(
            "identify_scenario",
            lambda state: "handle_error" if state.error_occurred else "fetch_context"
        )
        workflow.add_conditional_edges(
            "fetch_context",
            lambda state: "handle_error" if state.error_occurred else "plan_actions"
        )
        workflow.add_conditional_edges(
            "plan_actions",
            lambda state: "handle_error" if state.error_occurred else "execute_actions"
        )
        workflow.add_conditional_edges(
            "execute_actions",
            lambda state: "handle_error" if state.error_occurred else "analyze_impacts"
        )
        workflow.add_conditional_edges(
            "analyze_impacts",
            lambda state: "handle_error" if state.error_occurred else "format_response"
        )
        
        workflow.add_edge("handle_error", "format_response")
        
        # Compile the graph
        return workflow.compile()

    def _handle_error(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Handle errors that occurred during processing."""
        self._log(f"Handling error: {state.error_message}")
        return state

    def _analyze_request(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Analyze the user request using regex + LLM cooperative intent extraction."""
        self._log(f"Analyzing request: {state.user_request}")

        try:
            # Regex patterns
            patterns = {
                "actuator_ids": r"([A-Z]+-\d{4})",
                "field_ids": r"field\s+(\d+)|field\s+(\w+)",
                "field_names": r"([A-Za-z]+)\s+field",
                "resource_ids": r"(RES-\d{4})",
                "open_command": r"open|start|activate|turn\s+on|switch\s+on|enable|power\s+on",
                "close_command": r"close|stop|deactivate|turn\s+off|switch\s+off|disable|shut(\s+down)?|power\s+off",
                "status_query": r"status|state|condition|what\s+is|how\s+is",
                "level_query": r"level|volume|amount|capacity|how\s+much",
                "all_keyword": r"\ball\b|\bevery\b|\beach\b",
                "actuator_types": r"\bvalves?\b|\bpumps?\b|\bactuators?\b|\bwater\s+valves?\b|\bsensors?\b",
                "irrigation_command": r"irrigate|water|start\s+irrigation|begin\s+watering",
                "irrigation_stop": r"stop\s+irrigation|stop\s+watering|end\s+irrigation"
            }

            # Extract regex entities
            entities = {
                "actuator_ids": re.findall(patterns["actuator_ids"], state.user_request, re.IGNORECASE),
                "field_ids": [x[0] or x[1] for x in re.findall(patterns["field_ids"], state.user_request, re.IGNORECASE) if x[0] or x[1]],
                "field_names": re.findall(patterns["field_names"], state.user_request, re.IGNORECASE),
                "resource_ids": re.findall(patterns["resource_ids"], state.user_request, re.IGNORECASE),
                "is_irrigation_command": bool(re.search(patterns["irrigation_command"], state.user_request, re.IGNORECASE)),
                "is_irrigation_stop": bool(re.search(patterns["irrigation_stop"], state.user_request, re.IGNORECASE))
            }

            # Signal flags to assist LLM
            regex_signals = {
                "has_all_keyword": bool(re.search(patterns["all_keyword"], state.user_request, re.IGNORECASE)),
                "has_open": bool(re.search(patterns["open_command"], state.user_request, re.IGNORECASE)),
                "has_close": bool(re.search(patterns["close_command"], state.user_request, re.IGNORECASE)),
                "is_status_query": bool(re.search(patterns["status_query"], state.user_request, re.IGNORECASE)),
                "is_level_query": bool(re.search(patterns["level_query"], state.user_request, re.IGNORECASE)),
                "actuator_type": re.search(patterns["actuator_types"], state.user_request, re.IGNORECASE).group(0).lower()
                                if re.search(patterns["actuator_types"], state.user_request, re.IGNORECASE) else None
            }

            # Prompt construction
            system_prompt = """
            You are an AI assistant for a smart farm system.
            Interpret the user's natural language command using the raw message and regex-derived metadata.

            If the intent is ambiguous or unclear, DO NOT GUESS.
            Instead, return:
            {
            "intent_type": "clarification_needed",
            "clarification": "<a polite and concise question to ask the user>"
            }

            Otherwise, return a structured intent object like:
            {
                "intent_type": "<control_actuators|query_state|resource_management|...>",
                "action": "<close_actuator|get_resource_level|...>",
                "entities": {
                    "actuator_ids": [...],
                    "field_ids": [...],
                    "resource_ids": [...]
                },
                "parameters": {
                    "new_status": "<open|close>", ...
                }
            }
            Make sure your output is honest and complete. Clarify instead of hallucinating where appropriate.
            """

            human_prompt = json.dumps({
                "user_request": state.user_request,
                "regex_signals": regex_signals,
                "entities": entities
            }, indent=2)

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ]

            response = self.llm.invoke(messages)
            content = response.content

            json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
            intent_json = json.loads(json_match.group(1)) if json_match else json.loads(content)

            self._log(f"LLM intent: {intent_json}")

            updated_state = EnhancedActuatorControlState(
                messages=state.messages,
                user_request=state.user_request,
                intent=intent_json,
                debug_logs=state.debug_logs + ["LLM-enhanced intent extraction"]
            )
            return updated_state
            
        except Exception as e:
            error_message = f"Error analyzing request: {str(e)}"
            self._log(error_message)
            return EnhancedActuatorControlState(
                messages=state.messages,
                user_request=state.user_request,
                intent=None,
                error_occurred=True,
                error_message=error_message,
                debug_logs=state.debug_logs + [error_message]
            )
        
    def _identify_scenario(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Identify the specific scenario the user is asking about."""
        try:
            intent = state.intent
            
            # If we need clarification, don't try to identify a scenario
            if intent.get("intent_type") == "clarification_needed":
                return EnhancedActuatorControlState(
                    messages=state.messages,
                    user_request=state.user_request,
                    intent=state.intent,
                    scenario="clarification",
                    debug_logs=state.debug_logs + ["Scenario: clarification needed"]
                )
            
            # Check for irrigation intents specifically
            if intent.get("intent_type") == "irrigation_control" or (
                intent.get("intent_type") == "control_actuators" and 
                intent.get("action") in ["start_irrigation", "stop_irrigation"]):
                scenario = "irrigation_control"
            else:
                # Use existing mapping
                scenario_mapping = {
                    "query_state": "information_retrieval",
                    "control_actuators": "actuator_control",
                    "resource_management": "resource_management",
                    "irrigation_schedule": "scheduling",
                    "general_info": "general_information"
                }
                
                scenario = scenario_mapping.get(intent.get("intent_type", ""), "general_information")
            
            self._log(f"Identified scenario: {scenario}")
            
            return EnhancedActuatorControlState(
                messages=state.messages,
                user_request=state.user_request,
                intent=state.intent,
                scenario=scenario,
                debug_logs=state.debug_logs + [f"Identified scenario: {scenario}"]
            )
            
        except Exception as e:
            error_message = f"Error identifying scenario: {str(e)}"
            self._log(error_message)
            return EnhancedActuatorControlState(
                messages=state.messages,
                user_request=state.user_request,
                intent=state.intent,
                error_occurred=True,
                error_message=error_message,
                debug_logs=state.debug_logs + [error_message]
            )

    def _fetch_context(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Fetch relevant context based on the identified scenario and entities."""
        try:
            context = {"data": {}, "metadata": {}}
            intent = state.intent
            scenario = state.scenario
            
            # If we need clarification, no need to fetch context
            if scenario == "clarification":
                return EnhancedActuatorControlState(
                    messages=state.messages,
                    user_request=state.user_request,
                    intent=state.intent,
                    scenario=state.scenario,
                    context=context,
                    debug_logs=state.debug_logs + ["No context fetched for clarification"]
                )
            
            self._log(f"Fetching context for scenario: {scenario}")
            
            # Get entities from intent
            entities = intent.get("entities", {})
            field_ids = entities.get("field_ids", [])
            actuator_ids = entities.get("actuator_ids", [])
            resource_ids = entities.get("resource_ids", [])
            
            # Check if there were field names and try to convert them to IDs
            if "field_names" in entities and entities["field_names"]:
                for field_name in entities["field_names"]:
                    field_data = self.farm_control_service.get_field_by_name(field_name)
                    if field_data and field_data.get("id"):
                        field_ids.append(field_data["id"])
                        self._log(f"Resolved field name '{field_name}' to ID '{field_data['id']}'")
            
            # Track what we've already fetched
            fetched = {
                "fields": set(),
                "actuators": set(),
                "resources": set()
            }
            
            # Fetch context based on scenario
            if scenario == "information_retrieval":
                # Get field information
                if field_ids:
                    context["data"]["fields"] = {}
                    for field_id in field_ids:
                        if field_id in fetched["fields"]:
                            continue
                        
                        field_data = self.farm_control_service.get_field_by_id(field_id)
                        if field_data:
                            context["data"]["fields"][field_id] = field_data
                            fetched["fields"].add(field_id)
                            
                            # Also get the actuators for this field
                            field_actuators = self.farm_control_service.get_actuators_by_field(field_id)
                            if field_actuators and not (isinstance(field_actuators, dict) and "error" in field_actuators):
                                if "field_actuators" not in context["data"]:
                                    context["data"]["field_actuators"] = {}
                                context["data"]["field_actuators"][field_id] = field_actuators
                
                # Get actuator information
                if actuator_ids:
                    context["data"]["actuators"] = {}
                    for actuator_id in actuator_ids:
                        if actuator_id in fetched["actuators"]:
                            continue
                        
                        actuator_data = self.farm_control_service.get_actuator_by_id(actuator_id)
                        if actuator_data:
                            context["data"]["actuators"][actuator_id] = actuator_data
                            fetched["actuators"].add(actuator_id)
                
                # Get resource information
                if resource_ids:
                    context["data"]["resources"] = {}
                    for resource_id in resource_ids:
                        if resource_id in fetched["resources"]:
                            continue
                        
                        resource_data = self.farm_control_service.get_resource_by_id(resource_id)
                        if resource_data:
                            context["data"]["resources"][resource_id] = resource_data
                            fetched["resources"].add(resource_id)
            
            elif scenario == "actuator_control":
                # Get current actuator states
                if actuator_ids:
                    context["data"]["actuators"] = {}
                    
                    for actuator_id in actuator_ids:
                        if actuator_id in fetched["actuators"]:
                            continue
                        
                        actuator_data = self.farm_control_service.get_actuator_by_id(actuator_id)
                        if actuator_data:
                            context["data"]["actuators"][actuator_id] = actuator_data
                            fetched["actuators"].add(actuator_id)
                
                # For actuator control, also fetch resource levels as they might be affected
                try:
                    resource_levels = self.farm_control_service.get_resource_levels()
                    context["data"]["resource_levels"] = resource_levels
                except Exception as e:
                    self._log(f"Warning: Could not fetch resource levels: {str(e)}")
            
            elif scenario == "resource_management":
                # Get resource levels
                if resource_ids:
                    context["data"]["resources"] = {}
                    context["data"]["dependent_actuators"] = {}
                    
                    for resource_id in resource_ids:
                        if resource_id in fetched["resources"]:
                            continue
                        
                        resource_data = self.farm_control_service.get_resource_by_id(resource_id)
                        if resource_data:
                            context["data"]["resources"][resource_id] = resource_data
                            fetched["resources"].add(resource_id)
                            
                            # Get actuators dependent on this resource
                            dependent_actuators = self.farm_control_service.get_resource_dependent_actuators(resource_id)
                            if isinstance(dependent_actuators, list):  # Not an error response
                                context["data"]["dependent_actuators"][resource_id] = dependent_actuators
            
            # If no specific entities were mentioned, get overview data
            if not any([field_ids, actuator_ids, resource_ids]):
                # Add summary of the system
                if self.system_info:
                    context["data"]["system_summary"] = {
                        "farms_count": len(self.system_info["farms"]),
                        "fields_count": len(self.system_info["fields"]),
                        "actuators_count": len(self.system_info["actuators"]),
                        "resources_count": len(self.system_info["resources"])
                    }
            
            # Always get active actuators regardless of scenario
            try:
                active_actuators = self.farm_control_service.get_active_actuators()
                if active_actuators:
                    context["data"]["active_actuators"] = active_actuators
            except Exception as e:
                self._log(f"Warning: Could not fetch active actuators: {str(e)}")
            
            # If we have info about actuators that could be operated, add metadata about their types
            if "actuators" in context["data"] and context["data"]["actuators"]:
                actuator_types = {}
                for a_id, actuator in context["data"]["actuators"].items():
                    a_type = actuator.get("type")
                    if a_type:
                        if a_type not in actuator_types:
                            actuator_types[a_type] = []
                        actuator_types[a_type].append(a_id)
                
                if actuator_types:
                    context["metadata"]["actuator_types"] = actuator_types
            
            self._log(f"Fetched context with {len(context['data'])} data categories")
            
            return EnhancedActuatorControlState(
                messages=state.messages,
                user_request=state.user_request,
                intent=state.intent,
                scenario=state.scenario,
                context=context,
                debug_logs=state.debug_logs + [f"Fetched context with {len(context['data'])} data categories"]
            )
            
        except Exception as e:
            error_message = f"Error fetching context: {str(e)}"
            self._log(error_message)
            return EnhancedActuatorControlState(
                messages=state.messages,
                user_request=state.user_request,
                intent=state.intent,
                scenario=state.scenario,
                error_occurred=True,
                error_message=error_message,
                debug_logs=state.debug_logs + [error_message]
            )

    def _plan_actions(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Plan the actions to take based on the intent and context."""
        try:
            intent = state.intent
            self._log(f"Planning actions for intent: {intent.get('intent_type')}, action: {intent.get('action')}")
            
            # Handle clarification needed intent
            if intent.get("intent_type") == "clarification_needed":
                self._log("Intent requires clarification. No actions will be planned.")
                return EnhancedActuatorControlState(
                    messages=state.messages,
                    user_request=state.user_request,
                    intent=state.intent,
                    scenario=state.scenario,
                    context=state.context,
                    plan=None,  # No actions to plan
                    debug_logs=state.debug_logs + ["No actions planned due to clarification_needed intent"]
                )
            
            # Store regex signals for later use
            regex_signals = {}
            if "entities" in intent:
                regex_signals["is_irrigation_command"] = intent["entities"].get("is_irrigation_command", False)
                regex_signals["is_irrigation_stop"] = intent["entities"].get("is_irrigation_stop", False)
                
            # Fast path for irrigation commands
            if (intent.get("intent_type") in ["irrigation_control", "control_actuators"] and 
                (intent.get("action") in ["start_irrigation", "stop_irrigation"] or 
                regex_signals.get("is_irrigation_command") or regex_signals.get("is_irrigation_stop"))):
                
                action_plan = []
                start_irrigation = intent.get("action") == "start_irrigation" or regex_signals.get("is_irrigation_command", False)
                
                # Get field information
                field_ids = intent.get("entities", {}).get("field_ids", [])
                field_names = intent.get("entities", {}).get("field_names", [])
                
                # Resolve field names to IDs if needed
                if field_names and not field_ids:
                    for field_name in field_names:
                        field_data = self.farm_control_service.get_field_by_name(field_name)
                        if field_data and field_data.get("id"):
                            field_ids.append(field_data["id"])
                
                # If no specific field mentioned, check if the request implies a specific field
                if not field_ids:
                    # Check if the request contains words like "north", "south", etc.
                    direction_patterns = {
                        "north": r"\bnorth\b|\bnorthern\b",
                        "south": r"\bsouth\b|\bsouthern\b",
                        "east": r"\beast\b|\beastern\b",
                        "west": r"\bwest\b|\bwestern\b",
                        "central": r"\bcentral\b|\bcenter\b|\bmiddle\b"
                    }
                    
                    for direction, pattern in direction_patterns.items():
                        if re.search(pattern, state.user_request, re.IGNORECASE):
                            # Query fields that match the direction
                            fields = self.farm_control_service.get_all_fields()
                            for field in fields:
                                if direction.lower() in field.get("name", "").lower():
                                    field_ids.append(field["id"])
                                    break
                
                # If still no field identified, ask for clarification
                if not field_ids:
                    return EnhancedActuatorControlState(
                        messages=state.messages,
                        user_request=state.user_request,
                        intent={
                            "intent_type": "clarification_needed",
                            "clarification": "Which field would you like to irrigate? Please specify a field name or ID."
                        },
                        debug_logs=state.debug_logs + ["Field clarification needed for irrigation command"]
                    )
                
                # Create irrigation plan for each field
                for field_id in field_ids:
                    field_plan = self._plan_field_irrigation(field_id, start_irrigation)
                    action_plan.extend(field_plan)
                
                self._log(f"Created irrigation plan with {len(action_plan)} actions")
                
                return EnhancedActuatorControlState(
                    messages=state.messages,
                    user_request=state.user_request,
                    intent=state.intent,
                    scenario=state.scenario,
                    context=state.context,
                    plan=action_plan,
                    debug_logs=state.debug_logs + [f"Created irrigation plan with {len(action_plan)} actions"]
                )
                
            # Fast path for direct actuator control
            if (intent.get("intent_type") == "control_actuators" and 
                intent.get("action") in ["open_actuator", "close_actuator"] and
                "actuator_ids" in intent.get("entities", {}) and
                intent.get("entities", {}).get("actuator_ids")):
                
                # Direct control case - create plan immediately
                action_plan = []
                new_status = "open" if intent.get("action") == "open_actuator" else "close"
                
                for actuator_id in intent.get("entities", {}).get("actuator_ids", []):
                    # Check if actuator exists and what its current status is
                    actuator_data = self.farm_control_service.get_actuator_by_id(actuator_id)
                    if not actuator_data:
                        # If actuator doesn't exist, add a query action instead
                        action_plan.append({
                            "action_type": "query",
                            "target_type": "system",
                            "operation": "check_actuator_exists",
                            "parameters": {
                                "actuator_id": actuator_id
                            }
                        })
                        continue
                    
                    # If actuator exists but already has the requested status, make a verification action
                    if actuator_data.get("status") == new_status:
                        action_plan.append({
                            "action_type": "verify",
                            "target_type": "actuator",
                            "target_id": actuator_id,
                            "operation": "verify_status",
                            "parameters": {
                                "expected_status": new_status
                            }
                        })
                    else:
                        # Otherwise, create an update action
                        action_plan.append({
                            "action_type": "update",
                            "target_type": "actuator",
                            "target_id": actuator_id,
                            "operation": "change_status",
                            "parameters": {
                                "new_status": new_status
                            }
                        })
                
                self._log(f"Fast path created {len(action_plan)} actions")
                
                return EnhancedActuatorControlState(
                    messages=state.messages,
                    user_request=state.user_request,
                    intent=state.intent,
                    scenario=state.scenario,
                    context=state.context,
                    plan=action_plan,
                    debug_logs=state.debug_logs + [f"Fast path created {len(action_plan)} actions"]
                )
            
            # Fast path for resource queries
            elif (intent.get("intent_type") == "resource_management" and 
                  intent.get("action") == "get_resource_level" and 
                  "resource_ids" in intent.get("entities", {}) and
                  intent.get("entities", {}).get("resource_ids")):
                
                action_plan = []
                for resource_id in intent.get("entities", {}).get("resource_ids", []):
                    action_plan.append({
                        "action_type": "query",
                        "target_type": "resource",
                        "target_id": resource_id,
                        "operation": "get_level",
                        "parameters": {}
                    })
                
                self._log(f"Fast path created {len(action_plan)} resource query actions")
                
                return EnhancedActuatorControlState(
                    messages=state.messages,
                    user_request=state.user_request,
                    intent=state.intent,
                    scenario=state.scenario,
                    context=state.context,
                    plan=action_plan,
                    debug_logs=state.debug_logs + [f"Fast path created {len(action_plan)} resource query actions"]
                )
            
            # Fast path for actuator status queries
            elif (intent.get("intent_type") == "query_state" and 
                  intent.get("action") == "get_actuator_status" and 
              "actuator_ids" in intent.get("entities", {}) and
              intent.get("entities", {}).get("actuator_ids")):
            
                action_plan = []
                for actuator_id in intent.get("entities", {}).get("actuator_ids", []):
                    action_plan.append({
                        "action_type": "query",
                        "target_type": "actuator",
                        "target_id": actuator_id,
                        "operation": "get_status",
                        "parameters": {}
                    })
                
                self._log(f"Fast path created {len(action_plan)} actuator status query actions")
                
                return EnhancedActuatorControlState(
                    messages=state.messages,
                    user_request=state.user_request,
                    intent=state.intent,
                    scenario=state.scenario,
                    context=state.context,
                    plan=action_plan,
                    debug_logs=state.debug_logs + [f"Fast path created {len(action_plan)} actuator status query actions"]
                )
            
            # Regular path for other requests - use LLM to create the plan
            system_prompt = """You are an AI assistant specializing in farm control systems.
                Based on the user's intent and the context provided, create a plan of actions that need to be taken.
                
                Here are the available operations on the farm control system:
                1. Query operations:
                - get_all_farms() - Get a list of all farms
                - get_farm_by_id(farm_id) - Get details of a specific farm
                - get_all_fields() - Get a list of all fields
                - get_field_by_id(field_id) - Get details of a specific field
                - get_field_by_name(field_name) - Get details of a field by name
                - get_all_actuators() - Get a list of all actuators
                - get_actuator_by_id(actuator_id) - Get details of a specific actuator
                - get_actuator_by_type(actuator_type) - Get all actuators of a specific type
                - get_all_resources() - Get a list of all resources
                - get_resource_by_id(resource_id) - Get details of a specific resource
                - get_actuators_by_field(field_id) - Get all actuators in a field
                - get_active_actuators() - Get all actuators with status 'open'
                - get_resource_levels() - Get levels of all resources

                2. Control operations:
                - update_actuator_status(actuator_id, new_status) - Change actuator status
                - update_resource_level(resource_id, new_level) - Update resource level

                Return a JSON array with the following structure for each action:
                [
                    {
                        "action_type": "<query|update|create|verify>",
                        "target_type": "<actuator|resource|field|system>",
                        "target_id": "<id>",
                        "operation": "<operation_name>",
                        "parameters": {
                            "<param_name>": "<param_value>"
                        }
                    }
                ]
                
                Make sure to ONLY include valid operations that exist in the farm control system.
                """
            
            human_prompt = f"Intent: {json.dumps(intent)}\nScenario: {state.scenario}\nContext: {json.dumps(state.context)}"
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ]
            
            response = self.llm.invoke(messages)
            
            # Extract JSON from response text
            try:
                # Try to extract JSON from the content
                json_match = re.search(r'```json\n(.*?)\n```', response.content, re.DOTALL)
                if json_match:
                    action_plan = json.loads(json_match.group(1))
                else:
                    # Try to parse the entire content as JSON
                    action_plan = json.loads(response.content)
                
                self._log(f"LLM created action plan with {len(action_plan)} actions")
            except json.JSONDecodeError:
                # If parsing fails, create a simple action plan
                self._log("Failed to parse LLM action plan, creating a default plan")
                action_plan = [{"action_type": "query", "target_type": "system", "operation": "provide_info", "parameters": {}}]
            
            return EnhancedActuatorControlState(
                messages=state.messages,
                user_request=state.user_request,
                intent=state.intent,
                scenario=state.scenario,
                context=state.context,
                plan=action_plan,
                debug_logs=state.debug_logs + [f"Created action plan with {len(action_plan)} actions"]
            )
        except Exception as e:
            error_message = f"Error planning actions: {str(e)}"
            self._log(error_message)
            return EnhancedActuatorControlState(
                messages=state.messages,
                user_request=state.user_request,
                intent=state.intent,
                scenario=state.scenario,
                context=state.context,
                error_occurred=True,
                error_message=error_message,
                debug_logs=state.debug_logs + [error_message]
            )
    

    
    # Add this as a new method to FarmChatInterface
    def _plan_field_irrigation(self, field_id, start_irrigation=True):
        """
        Improved irrigation planning with field validation and actuator sequencing
        """
        action_plan = []
        
        # First verify field existence
        action_plan.append({
            "action_type": "verify",
            "target_type": "field",
            "target_id": field_id,
            "operation": "exists",
            "parameters": {}
        })
        
        # Get field actuators with proper error handling
        field_actuators = self.farm_control_service.get_actuators_by_field(field_id)
        if not field_actuators:
            return [{
                "action_type": "error",
                "message": f"No actuators found in field {field_id}",
                "recovery_action": "get_actuators_by_field_name"
            }]
        
        # Categorize actuators with status verification
        categorized = {"valves": [], "pumps": [], "dispensers": []}
        for actuator in field_actuators:
            actuator_id = actuator["id"]
            
            # Add status verification step
            action_plan.append({
                "action_type": "verify",
                "target_type": "actuator",
                "target_id": actuator_id,
                "operation": "current_status",
                "parameters": {"expected_status": actuator["status"]}
            })
            
            # Categorize based on type
            if "valve" in actuator["type"].lower():
                categorized["valves"].append(actuator_id)
            elif "pump" in actuator["type"].lower():
                categorized["pumps"].append(actuator_id)
            elif "dispenser" in actuator["type"].lower():
                categorized["dispensers"].append(actuator_id)
        
        # Create ordered control sequence
        control_sequence = []
        if start_irrigation:
            # Open valves -> dispensers -> pumps
            control_sequence.extend([
                ("valves", "open"),
                ("dispensers", "open"),
                ("pumps", "open")
            ])
        else:
            # Close pumps -> dispensers -> valves
            control_sequence.extend([
                ("pumps", "close"),
                ("dispensers", "close"),
                ("valves", "close")
            ])
        
        # Build final action plan with verification
        for device_type, status in control_sequence:
            for actuator_id in categorized[device_type]:
                action_plan.extend([
                    {
                        "action_type": "update",
                        "target_type": "actuator",
                        "target_id": actuator_id,
                        "operation": "change_status",
                        "parameters": {"new_status": status}
                    },
                    {
                        "action_type": "verify",
                        "target_type": "actuator",
                        "target_id": actuator_id,
                        "operation": "status_changed",
                        "parameters": {"expected_status": status}
                    }
                ])
        
        return action_plan

    def _execute_actions(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Execute the planned actions."""
        plan = state.plan
        results = []
        
        # Track successful and failed actions
        action_summary = {
            "successful": [],
            "failed": []
        }
        
        if not plan:
            return EnhancedActuatorControlState(
                messages=state.messages,
                user_request=state.user_request,
                intent=state.intent,
                scenario=state.scenario,
                context=state.context,
                plan=plan,
                execution_results=[{"status": "no_actions", "message": "No actions to execute"}],
                debug_logs=state.debug_logs + ["No actions to execute"]
            )
        
        self._log(f"Executing {len(plan)} actions")
        if state.intent.get("intent_type") == "clarification_needed":
            
            self._log("No actions will be executed due to clarification_needed intent")
            return EnhancedActuatorControlState(
                messages=state.messages,
                user_request=state.user_request,
                intent=state.intent,
                scenario=state.scenario,
                context=state.context,
                plan=plan,
                execution_results=[{"status": "no_actions", "message": "No actions to execute"}],
                debug_logs=state.debug_logs + ["No actions to execute due to clarification_needed intent"]
            )
            
        for action in plan:
            result = {"action": action, "status": "success", "data": None, "message": ""}
            
            try:
                action_type = action.get("action_type")
                target_type = action.get("target_type")
                target_id = action.get("target_id")
                operation = action.get("operation")
                parameters = action.get("parameters", {})
                
                self._log(f"Executing {action_type} on {target_type} {target_id} - {operation}")
                
                # Handle different action types
                if action_type == "query":
                    result = self._execute_query_action(target_type, target_id, operation, parameters)
                elif action_type == "update":
                    result = self._execute_update_action(target_type, target_id, operation, parameters)
                elif action_type == "verify":
                    result = self._execute_verify_action(target_type, target_id, operation, parameters)
                else:
                    result["status"] = "error"
                    result["message"] = f"Unknown action type: {action_type}"
                    action_summary["failed"].append(f"{action_type} on {target_type} {target_id}")
                
                # Update action summary
                if result["status"] == "success":
                    action_summary["successful"].append(f"{operation} on {target_type} {target_id}")
                else:
                    action_summary["failed"].append(f"{operation} on {target_type} {target_id}")
            
            except Exception as e:
                error_msg = f"Error executing action: {str(e)}"
                self._log(error_msg)
                result["status"] = "error"
                result["message"] = error_msg
                action_summary["failed"].append(f"{operation} on {target_type} {target_id}")
            
            results.append(result)
        
        # Refresh context with updated system state
        updated_context = self._refresh_context(state.context, results)
        
        return EnhancedActuatorControlState(
            messages=state.messages,
            user_request=state.user_request,
            intent=state.intent,
            scenario=state.scenario,
            context=updated_context,
            plan=plan,
            execution_results=results,
            debug_logs=state.debug_logs + [f"Executed {len(results)} actions: {len(action_summary['successful'])} successful, {len(action_summary['failed'])} failed"]
        )

    def _execute_query_action(self, target_type: str, target_id: str, operation: str, parameters: dict) -> dict:
        """Execute a query action."""
        result = {"status": "success", "data": None, "message": ""}
        
        try:
            if target_type == "actuator":
                if operation == "get_status":
                    data = self.farm_control_service.get_actuator_by_id(target_id)
                    if data:
                        result["data"] = data
                    else:
                        result["status"] = "error"
                        result["message"] = f"Actuator {target_id} not found"
            elif target_type == "resource":
                if operation == "get_level":
                    data = self.farm_control_service.get_resource_by_id(target_id)
                    if data:
                        result["data"] = data.get("level")
                    else:
                        result["status"] = "error"
                        result["message"] = f"Resource {target_id} not found"
            # Add other query operations as needed
        except Exception as e:
            result["status"] = "error"
            result["message"] = str(e)
        
        return result

    def _execute_update_action(self, target_type: str, target_id: str, operation: str, parameters: dict) -> dict:
        """Execute an update action."""
        result = {"status": "success", "data": None, "message": ""}
        
        try:
            if target_type == "actuator" and operation == "change_status":
                new_status = parameters.get("new_status")
                if new_status in ["open", "close"]:
                    current_state = self.farm_control_service.get_actuator_by_id(target_id)
                    if current_state:
                        if current_state["status"] != new_status:
                            update_result = self.farm_control_service.update_actuator_status(target_id, new_status)
                            if "error" in update_result:
                                result["status"] = "error"
                                result["message"] = update_result["error"]
                            else:
                                result["data"] = update_result
                        else:
                            result["message"] = f"Actuator {target_id} already in {new_status} state"
                    else:
                        result["status"] = "error"
                        result["message"] = f"Actuator {target_id} not found"
                else:
                    result["status"] = "error"
                    result["message"] = "Invalid status parameter"
            # Add other update operations as needed
        except Exception as e:
            result["status"] = "error"
            result["message"] = str(e)
        
        return result

    def _execute_verify_action(self, target_type: str, target_id: str, operation: str, parameters: dict) -> dict:
        """Enhanced verification with field-specific checks"""
        result = {"status": "success", "data": None, "message": ""}
        
        try:
            
            if target_type == "field" and operation == "exists":
                field_data = self.farm_control_service.get_field_by_id(target_id)
                if not field_data:
                    result["status"] = "error"
                    result["message"] = f"Field {target_id} not found"
                else:
                    result["data"] = field_data
            
            elif target_type == "actuator" and operation == "current_status":
                expected_status = parameters.get("expected_status")
                current_status = self.farm_control_service.get_actuator_by_id(target_id).get("status")
                
                if current_status != expected_status:
                    result["status"] = "error"
                    result["message"] = f"Unexpected current status: {current_status}"
                    
            elif target_type == "actuator" and operation == "status_changed":
                expected_status = parameters.get("expected_status")
                current_status = self.farm_control_service.get_actuator_by_id(target_id).get("status")
                
                if current_status != expected_status:
                    result["status"] = "error"
                    result["message"] = f"Status change failed. Current: {current_status}"
                    
            else:
                result = super()._execute_verify_action(target_type, target_id, operation, parameters)
                
        except Exception as e:
            result["status"] = "error"
            result["message"] = str(e)
            
        return result


    def _refresh_context(self, original_context: dict, execution_results: list) -> dict:
        """Refresh system context after executing actions."""
        updated_context = original_context.copy()
        
        # Track affected entities
        affected_entities = {
            "actuators": set(),
            "resources": set(),
            "fields": set()
        }
        
        # Collect IDs from execution results
        for result in execution_results:
            action = result.get("action", {})
            target_id = action.get("target_id")
            if target_id:
                target_type = action.get("target_type")
                if target_type == "actuator":
                    affected_entities["actuators"].add(target_id)
                elif target_type == "resource":
                    affected_entities["resources"].add(target_id)
                elif target_type == "field":
                    affected_entities["fields"].add(target_id)
        
        # Refresh actuator data
        if "actuators" not in updated_context["data"]:
            updated_context["data"]["actuators"] = {}
        for actuator_id in affected_entities["actuators"]:
            updated_context["data"]["actuators"][actuator_id] = \
                self.farm_control_service.get_actuator_by_id(actuator_id)
        
        # Refresh resource data
        if "resources" not in updated_context["data"]:
            updated_context["data"]["resources"] = {}
        for resource_id in affected_entities["resources"]:
            updated_context["data"]["resources"][resource_id] = \
                self.farm_control_service.get_resource_by_id(resource_id)
        
        # Refresh field data
        if "fields" not in updated_context["data"]:
            updated_context["data"]["fields"] = {}
        for field_id in affected_entities["fields"]:
            updated_context["data"]["fields"][field_id] = \
                self.farm_control_service.get_field_by_id(field_id)
        
        # Refresh active actuators
        updated_context["data"]["active_actuators"] = \
            self.farm_control_service.get_active_actuators()
        
        return updated_context


    def _analyze_impacts(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Analyze the impacts of the executed actions."""
        execution_results = state.execution_results
        impact_analysis = {
            "summary": f"Executed {len(execution_results)} actions.",
            "details": execution_results
        }
        return EnhancedActuatorControlState(
            messages=state.messages,
            user_request=state.user_request,
            intent=state.intent,
            scenario=state.scenario,
            context=state.context,
            plan=state.plan,
            execution_results=execution_results,
            impact_analysis=impact_analysis
        )

    def _format_response(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Format a natural language response to the user."""
        
        
        
        system_prompt = """You are an AI assistant specializing in farm control systems.
            Create a natural, helpful response to the user based on the results of their request.
            
            VERY IMPORTANT: Be COMPLETELY HONEST about what happened. If actions failed, clearly explain that they failed.
            Do not claim that actions were successful if they weren't. Check the execution_results carefully.
            
            Your response should:
            1. Clearly state which actions succeeded and which failed
            2. Provide the current state of any relevant actuators, resources, or fields
            3. Only mention successful changes if they are verified in the execution_results
            4. For any failures, explain what might have gone wrong and suggest alternatives
            5. Keep the tone helpful and professional
            
            If there were mixed results (some successes, some failures), acknowledge both.
            """
        
        try:
            # Serialize execution results safely
            simplified_results = json.dumps(state.execution_results, default=_serialize_datetime)
            human_prompt = f"""
                User request: {state.user_request}
                Intent: {json.dumps(state.intent, default=_serialize_datetime)}
                Execution results: {simplified_results}
                Context: {json.dumps(state.context, default=_serialize_datetime)}
            """
        except Exception as e:
            self._log(f"Error serializing response data: {str(e)}")
            human_prompt = "Error occurred while processing the request."
            
        self._log(f"Formatting response for user request: {state.user_request}")
       
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]
        
        response = self.llm.invoke(messages)
        response_text = response.content
        
        # Update the conversation history
        updated_messages = state.messages.copy()
        updated_messages.append({"role": "assistant", "content": response_text})
        
        return EnhancedActuatorControlState(
            messages=updated_messages,
            user_request=state.user_request,
            intent=state.intent,
            scenario=state.scenario,
            context=state.context,
            plan=state.plan,
            execution_results=state.execution_results,
            impact_analysis=state.impact_analysis,
            response=response_text
        )


    def chat(self, message: str) -> str:
        """
        Process a user message and return a response.
        
        Args:
            message: User's message
            
        Returns:
            Response from the system
        """
        # Create initial state with the user message
        initial_state = EnhancedActuatorControlState(
            messages=[{"role": "user", "content": message}],
            user_request=message
        )
        
        # Run the graph
        final_state = self.graph.invoke(initial_state)
        #print("[DEBUG] Final state:", final_state)
        
        # Based on the debug output, the response is directly available as a top-level key
        if hasattr(final_state, 'response'):
            return final_state.response
        elif isinstance(final_state, dict) and 'response' in final_state:
            return final_state['response']
        elif isinstance(final_state, dict) and 'messages' in final_state:
            # If there are assistant messages, return the most recent one
            assistant_messages = [msg['content'] for msg in final_state['messages'] 
                                if msg.get('role') == 'assistant']
            if assistant_messages:
                return assistant_messages[-1]
        
        # Fallback
        return "Sorry, I couldn't process your request."

def create_farm_chat_endpoint(farm_control_service, model_name="gpt-4o"):
    """
    Create a farm chat interface instance.
    
    Args:
        farm_control_service: An instance of FarmControlService
        model_name: The LLM model to use
        
    Returns:
        An instance of FarmChatInterface
    """
    return FarmChatInterface(farm_control_service, model_name=model_name)