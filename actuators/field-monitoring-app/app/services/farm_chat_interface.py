from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field
import os
import json
import re
import datetime
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain.schema import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langchain.prompts import ChatPromptTemplate

from models.models import get_session_factory
from services.farm_control_service import FarmControlService

load_dotenv()  # Load environment variables

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime) or isinstance(obj, datetime.date):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)
    
class FarmChatState(BaseModel):
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
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
    confirmation_needed: bool = False
    confirmation_details: Optional[Dict] = None
    debug_logs: List[str] = Field(default_factory=list)
    error_occurred: bool = False
    error_message: Optional[str] = None


class EnhancedFarmChatInterface:
    """
    Enhanced natural language chat interface for farm control system.
    Allows farmers to manage irrigation, monitoring, and farm equipment
    through conversational language with improved context awareness.
    """
    
    def __init__(self, farm_control_service: FarmControlService, 
                 model_name: str = "gpt-4o", temperature: float = 0.1, 
                 api_key: str = None, debug_mode: bool = True):
        """Initialize the chat interface."""
        
        self.debug_mode = debug_mode
        self.farm_control_service = farm_control_service
        self.api_key = api_key or os.environ.get("OPENAI_PROJECT_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
            
        self.llm = ChatOpenAI(api_key=self.api_key, model=model_name, temperature=temperature)
        
        # Initialize system info
        self.system_info = {}
        # Prefetch available information about the farm system
        self._prefetch_system_info()
        
        # Farm status cache to reduce duplicate queries
        self.status_cache = {
            "last_update": None,
            "active_actuators": None,
            "field_status": {},
            "resource_levels": None
        }
        # Initialize recent mentions tracking
        self.recent_mentions = {
            "fields": [],
            "actuators": [],
            "resources": []
        }
    
        self.cache_lifetime = datetime.timedelta(minutes=5)  # Cache valid for 5 minutes
        
        # Conversation memory
        self.conversation_memory = []
        self.max_memory_items = 10
        
        # Build the conversation graph
        self.graph = self._build_graph()
        
    def _log(self, message):
        """Log debug information if debug mode is enabled."""
        if self.debug_mode:
            print(f"[DEBUG] {message}")
    
    def _prefetch_system_info(self):
        """Enhanced system info prefetch with resource mapping."""
        try:
            self.system_info = {
                "farms": self.farm_control_service.get_all_farms(),
                "fields": self.farm_control_service.get_all_fields(),
                "actuators": self.farm_control_service.get_all_actuators(),
                "sensors": self.farm_control_service.get_all_sensors(),
                "resources": self.farm_control_service.get_all_resources()
            }
            
            # Add field name mapping
            self.field_name_map = {}
            for field in self.system_info.get("fields", []):
                name = field.get("name", "").lower()
                if name:
                    self.field_name_map[name] = field.get("id")
                    if not name.endswith("field"):
                        self.field_name_map[f"{name} field"] = field.get("id")
            
            # Add actuator name mapping
            self.actuator_name_map = {}
            for actuator in self.system_info.get("actuators", []):
                name = actuator.get("name", "").lower()
                if name:
                    self.actuator_name_map[name] = actuator.get("id")
                    
            # Add resource name mapping
            self.resource_name_map = {}
            for resource in self.system_info.get("resources", []):
                name = resource.get("name", "").lower()
                if name:
                    self.resource_name_map[name] = resource.get("id")
                    
            # Add crop to field mapping
            self.field_crop_map = {}
            for field in self.system_info.get("fields", []):
                crop = field.get("crop", "").lower()
                if crop:
                    if crop not in self.field_crop_map:
                        self.field_crop_map[crop] = []
                    self.field_crop_map[crop].append(field.get("id"))
                    
            self._log(f"Prefetched system info with {len(self.system_info['farms'])} farms, "
                     f"{len(self.system_info['fields'])} fields, "
                     f"{len(self.system_info['sensors'])} sensors, "
                     f"{len(self.system_info['actuators'])} actuators, "
                     f"{len(self.system_info['resources'])} resources")
                     
        except Exception as e:
            self._log(f"Error prefetching system info: {str(e)}")
            self.system_info = {}
            
    def _update_status_cache(self):
        """Update the status cache if it's expired."""
        now = datetime.datetime.now()
        if (not self.status_cache["last_update"] or 
            now - self.status_cache["last_update"] > self.cache_lifetime):
            try:
                self.status_cache["active_actuators"] = self.farm_control_service.get_active_actuators()
                self.status_cache["inactive_actuators"] = self.farm_control_service.get_inactive_actuators()
                self.status_cache["resource_levels"] = self.farm_control_service.get_resource_levels()
                
                # Update field status
                for field in self.system_info.get("fields", []):
                    field_id = field.get("id")
                    if field_id:
                        # Check irrigation status
                        field_actuators = self.farm_control_service.get_actuators_by_field(field_id)
                        active_irrigation = any(
                            actuator.get("status") == "open" and 
                            actuator.get("type") in ["water_valves", "pump"] 
                            for actuator in field_actuators
                        )
                        
                        # Check soil moisture if available
                        moisture_sensors = [
                            sensor for sensor in self.farm_control_service.get_sensors_by_field(field_id)
                            if "moist" in sensor.get("type", "").lower()
                        ]
                        
                        self.status_cache["field_status"][field_id] = {
                            "is_irrigating": active_irrigation,
                            "has_moisture_sensors": len(moisture_sensors) > 0,
                            "actuators": field_actuators
                        }
                
                self.status_cache["last_update"] = now
            except Exception as e:
                self._log(f"Error updating status cache: {str(e)}")
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine for farm control interactions."""
        workflow = StateGraph(FarmChatState)
        
        # Define the nodes
        workflow.add_node("analyze_request", self._analyze_request)
        workflow.add_node("check_clarification", self._check_clarification)
        workflow.add_node("get_clarification", self._get_clarification)
        workflow.add_node("identify_scenario", self._identify_scenario)
        workflow.add_node("fetch_context", self._fetch_context)
        workflow.add_node("plan_actions", self._plan_actions)
        workflow.add_node("check_confirmation", self._check_confirmation)
        workflow.add_node("get_confirmation", self._get_confirmation)
        workflow.add_node("execute_actions", self._execute_actions)
        workflow.add_node("analyze_impacts", self._analyze_impacts)
        workflow.add_node("format_response", self._format_response)
        workflow.add_node("handle_error", self._handle_error)
        
        # Define the edges
        workflow.add_edge(START, "analyze_request")
        
        # Add error handling for all nodes
        workflow.add_conditional_edges(
            "analyze_request",
            lambda state: "handle_error" if state.error_occurred else "check_clarification"
        )
        
        # Conditional edge - if clarification needed
        workflow.add_conditional_edges(
            "check_clarification",
            lambda state: "get_clarification" if state.clarification_needed else "identify_scenario"
        )
        
        workflow.add_edge("get_clarification", END)  # End for clarification, user will respond
        workflow.add_edge("identify_scenario", "fetch_context")
        workflow.add_edge("fetch_context", "plan_actions")
        
        # Add confirmation step for potentially risky operations
        workflow.add_conditional_edges(
            "plan_actions",
            lambda state: "check_confirmation" if state.plan else "format_response"
        )
        
        workflow.add_conditional_edges(
            "check_confirmation",
            lambda state: "get_confirmation" if state.confirmation_needed else "execute_actions"
        )
        
        workflow.add_edge("get_confirmation", END)  # End for confirmation, user will respond
        workflow.add_edge("execute_actions", "analyze_impacts")
        workflow.add_edge("analyze_impacts", "format_response")
        workflow.add_edge("format_response", END)
        workflow.add_edge("handle_error", END)
        
        # Compile the graph
        return workflow.compile()
    
    def _analyze_request(self, state: FarmChatState) -> FarmChatState:
        """
        Analyze the user request with enhanced contextual understanding and 
        reduced need for clarifications by leveraging historical context.
        """
        # Ensure user_request exists
        if not state.user_request or state.user_request.strip() == "":
            state.error_occurred = True
            state.error_message = "No user request provided"
            return state
            
        # Update status cache for fresh information
        self._update_status_cache()
            
        # Handle greetings and basic status requests with richer information
        greeting_pattern = r'^(hi|hello|hey|greetings|good morning|good afternoon|good evening|how are you|how\'s it going)\s*\??$'
        overview_pattern = r'^(tell me about|show me|what\'s|what is|show|overview|status of|report on) (my|the) (farm|fields?|situation|system|overview)\s*\??$'
        
        if re.match(greeting_pattern, state.user_request.strip().lower()):
            # Respond with greeting and comprehensive farm overview
            # Count active equipment by type for more informative response
            active_actuators = self.status_cache.get("active_actuators", [])
            active_by_type = {}
            for actuator in active_actuators:
                actuator_type = actuator.get("type", "unknown")
                if actuator_type not in active_by_type:
                    active_by_type[actuator_type] = 0
                active_by_type[actuator_type] += 1
            
            # Format active equipment summary
            active_summary = []
            for actuator_type, count in active_by_type.items():
                # Format the actuator type for display
                display_type = actuator_type.replace("_", " ")
                if display_type.endswith("s"):
                    display_type = display_type[:-1] + "(s)"
                active_summary.append(f"{count} {display_type}")
            
            # Count irrigating fields with names
            irrigating_fields = []
            for field_id, status in self.status_cache.get("field_status", {}).items():
                if status.get("is_irrigating", False):
                    # Find field name
                    for field in self.system_info.get("fields", []):
                        if field.get("id") == field_id:
                            irrigating_fields.append(field.get("name", "Unknown field"))
                            break
            
            # Check resource levels for insights
            resources = self.status_cache.get("resource_levels", {})
            low_resources = []
            for resource_id, resource_info in resources.items():
                try:
                    current = float(resource_info.get("current_level", "0").split()[0].replace(",", ""))
                    capacity = float(resource_info.get("capacity", "0").split()[0].replace(",", ""))
                    if capacity > 0 and (current / capacity) < 0.25:
                        low_resources.append(resource_info.get("name", "Unknown resource"))
                except (ValueError, IndexError):
                    continue
            
            # Build a more informative greeting
            greeting_response = f"Hello! Welcome to your Thousand Hills Farm management system. Here's your current status:\n\n"
            
            # Add active equipment summary
            if active_summary:
                greeting_response += f"**Active Equipment:** {', '.join(active_summary)}\n\n"
            else:
                greeting_response += "**Active Equipment:** No equipment currently active\n\n"
            
            # Add irrigation status
            if irrigating_fields:
                if len(irrigating_fields) == 1:
                    greeting_response += f"**Irrigation:** Currently watering {irrigating_fields[0]}\n\n"
                else:
                    greeting_response += f"**Irrigation:** Watering {len(irrigating_fields)} fields: {', '.join(irrigating_fields)}\n\n"
            else:
                greeting_response += "**Irrigation:** No fields currently being irrigated\n\n"
            
            # Add resource warnings if any
            if low_resources:
                if len(low_resources) == 1:
                    greeting_response += f"**❗ Notice:** {low_resources[0]} is running low\n\n"
                else:
                    greeting_response += f"**❗ Notice:** Low resources: {', '.join(low_resources)}\n\n"
            
            greeting_response += f"How can I help with your farm management today?"
            
            state.response = greeting_response
            return state
            
        elif re.match(overview_pattern, state.user_request.strip().lower()):
            # Provide a comprehensive system overview with actionable insights
            
            # Get current active actuators with improved grouping
            active_actuators = self.status_cache.get("active_actuators", [])
            active_by_type = {}
            for actuator in active_actuators:
                actuator_type = actuator.get("type", "unknown")
                field_id = actuator.get("field_id")
                
                # Group by type and field for more context
                if actuator_type not in active_by_type:
                    active_by_type[actuator_type] = {}
                
                field_name = "Unassigned"
                if field_id:
                    for field in self.system_info.get("fields", []):
                        if field.get("id") == field_id:
                            field_name = field.get("name", "Unknown field")
                            break
                
                if field_name not in active_by_type[actuator_type]:
                    active_by_type[actuator_type][field_name] = 0
                active_by_type[actuator_type][field_name] += 1
            
            # Get resource status with level percentage
            resources = self.status_cache.get("resource_levels", {})
            resource_summary = []
            for resource_id, resource_info in resources.items():
                name = resource_info.get("name", "Unknown")
                current = resource_info.get("current_level", "Unknown")
                capacity = resource_info.get("capacity", "Unknown")
                
                # Calculate percentage if possible
                percentage = ""
                try:
                    current_val = float(current.split()[0].replace(",", ""))
                    capacity_val = float(capacity.split()[0].replace(",", ""))
                    if capacity_val > 0:
                        percentage = f" ({(current_val / capacity_val) * 100:.0f}%)"
                except (ValueError, IndexError):
                    pass
                
                resource_summary.append({
                    "name": name,
                    "level": f"{current} / {capacity}{percentage}",
                    "is_low": percentage and int(percentage.strip("()%")) < 25
                })
            
            # Format field status with more details
            irrigating_fields = []
            fields_by_crop = {}
            
            for field in self.system_info.get("fields", []):
                field_id = field.get("id")
                field_name = field.get("name", "Unknown field")
                crop = field.get("crop", "Unknown crop")
                
                if crop not in fields_by_crop:
                    fields_by_crop[crop] = []
                fields_by_crop[crop].append(field_name)
                
                field_status = self.status_cache.get("field_status", {}).get(field_id, {})
                if field_status.get("is_irrigating", False):
                    irrigating_fields.append(field_name)
            
            # Build the comprehensive overview response
            overview_response = "# Thousand Hills Farm - System Overview\n\n"
            
            # Equipment section
            overview_response += "## Equipment Status\n"
            if active_actuators:
                for actuator_type, fields in active_by_type.items():
                    display_type = actuator_type.replace("_", " ").title()
                    overview_response += f"### {display_type}\n"
                    for field_name, count in fields.items():
                        overview_response += f"* {field_name}: {count} active\n"
            else:
                overview_response += "* No equipment currently active\n"
            
            # Field section
            overview_response += "\n## Field Status\n"
            if irrigating_fields:
                overview_response += "### Currently Irrigating\n"
                for field in irrigating_fields:
                    overview_response += f"* {field}\n"
            
            overview_response += "\n### Fields by Crop\n"
            for crop, fields in fields_by_crop.items():
                overview_response += f"* {crop}: {', '.join(fields)}\n"
            
            # Resource section
            overview_response += "\n## Resource Levels\n"
            for resource in resource_summary:
                prefix = "❗ " if resource["is_low"] else ""
                overview_response += f"* {prefix}{resource['name']}: {resource['level']}\n"
            
            # Add recommendations if applicable
            if any(resource["is_low"] for resource in resource_summary):
                overview_response += "\n## Recommendations\n"
                overview_response += "* Consider refilling low resources soon\n"
            
            if not irrigating_fields and len(self.system_info.get("fields", [])) > 0:
                overview_response += "* No fields are currently being irrigated. Use 'irrigate [field name]' to start watering\n"
            
            state.response = overview_response
            return state
    
        self._log(f"Analyzing request: {state.user_request}")
    
        try:
            # Enhanced intent extraction with better context usage
            # Expanded regex patterns for entity extraction
            patterns = {
                "actuator_ids": r"([A-Z]+-\d{4})",
                "field_ids": r"field\s+(\d+)|field\s+(\w+)",
                "field_names": r"([A-Za-z]+)\s+field|([A-Za-z]+ern)\s+field?|field\s+of\s+([A-Za-z]+)|([A-Za-z]+)\s+Field",  # Added capitalized Field
                "resource_ids": r"(RES-\d{4})",
                "open_command": r"\b(open|start|activate|turn\s+on|switch\s+on|enable|power\s+on)\b",
                "close_command": r"\b(close|stop|deactivate|turn\s+off|switch\s+off|disable|shut(\s+down)?|power\s+off)\b",
                "status_query": r"\b(status|state|condition|what\s+is|how\s+is)\b",
                "level_query": r"\b(level|volume|amount|capacity|how\s+much)\b",
                "all_keyword": r"\b(all|every|each)\b",
                "actuator_types": r"\b(valves?|pumps?|actuators?|water\s+valves?|sensors?|equipment|machines?|devices?)\b",
                "irrigation_command": r"\b(irrigate|water|start\s+irrigation|begin\s+watering)\b",
                "irrigation_stop": r"\b(stop\s+irrigation|stop\s+watering|end\s+irrigation)\b",
                "moisture_query": r"\b(moisture|wetness|humidity|soil\s+moisture)\b",
                "temperature_query": r"\b(temperature|heat|warmth|how\s+hot|how\s+cold)\b",
                "bulk_operation": r"\b(all|every|each|multiple|several|many)\b",
                "crop_reference": r"\b(corn|wheat|soy|soybeans|barley|alfalfa|cotton|rice|potatoes|vegetables)\b"
            }
    
            entities = {
                "actuator_ids": re.findall(patterns["actuator_ids"], state.user_request, re.IGNORECASE),
                "field_ids": [x[0] or x[1] for x in re.findall(patterns["field_ids"], state.user_request, re.IGNORECASE) if x[0] or x[1]],
                "field_names": [],  # We'll extract these more carefully below
                "resource_ids": re.findall(patterns["resource_ids"], state.user_request, re.IGNORECASE),
                "is_irrigation_command": bool(re.search(patterns["irrigation_command"], state.user_request, re.IGNORECASE)),
                "is_irrigation_stop": bool(re.search(patterns["irrigation_stop"], state.user_request, re.IGNORECASE)),
                "is_moisture_query": bool(re.search(patterns["moisture_query"], state.user_request, re.IGNORECASE)),
                "is_temperature_query": bool(re.search(patterns["temperature_query"], state.user_request, re.IGNORECASE)),
                "is_bulk_operation": bool(re.search(patterns["bulk_operation"], state.user_request, re.IGNORECASE))
            }
    
            # Signal flags to assist LLM
            regex_signals = {
                "has_all_keyword": bool(re.search(patterns["all_keyword"], state.user_request, re.IGNORECASE)),
                "has_open": bool(re.search(patterns["open_command"], state.user_request, re.IGNORECASE)),
                "has_close": bool(re.search(patterns["close_command"], state.user_request, re.IGNORECASE)),
                "is_status_query": bool(re.search(patterns["status_query"], state.user_request, re.IGNORECASE)),
                "is_level_query": bool(re.search(patterns["level_query"], state.user_request, re.IGNORECASE)),
            }
            
            # Enhanced actuator related patterns
            actuator_patterns = {
                "list_actuators": r"\b(what|list|show|get|tell).*(actuators?|equipment|devices?)\b",
                "available_actuators": r"\b(available|active|current|existing)\s*(actuators?|equipment|devices?)\b",
                "actuator_status": r"\b(status|state|condition)\s*(of|for)?\s*(actuators?|equipment|devices?)\b",
                # FIX: Added patterns for inactive actuators
                "inactive_actuators": r"\b(inactive|closed|off|disabled)\s*(actuators?|equipment|devices?)\b"
            }

            # More comprehensive field name extraction with priority given to exact matches
            # Extract field names from patterns
            field_name_matches = []
            
            # First check for explicit field name patterns
            for match in re.finditer(patterns["field_names"], state.user_request, re.IGNORECASE):
                groups = match.groups()
                for group in groups:
                    if group:
                        field_name_matches.append(group.lower())

            # Now check for exact field names in the text
            for field in self.system_info.get("fields", []):
                field_name = field.get("name", "").lower()
                if field_name and field_name in state.user_request.lower():
                    field_name_matches.append(field_name)
                    
                    # Also check without "field" suffix
                    if field_name.endswith(" field") and field_name[:-6] in state.user_request.lower():
                        field_name_matches.append(field_name[:-6])
            
            # Check for crop-based field references
            crop_matches = re.findall(patterns["crop_reference"], state.user_request, re.IGNORECASE)
            for crop in crop_matches:
                crop_lower = crop.lower()
                if crop_lower in self.field_crop_map:
                    # If we find fields with this crop type, add their names
                    for field_id in self.field_crop_map[crop_lower]:
                        for field in self.system_info.get("fields", []):
                            if field.get("id") == field_id:
                                field_name_matches.append(field.get("name", "").lower())
            
            # Look for cardinal directions as potential field names
            cardinal_directions = ["north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest", "central"]
            for direction in cardinal_directions:
                if direction in state.user_request.lower():
                    # Check if this direction corresponds to a field
                    potential_field = f"{direction} field"
                    if potential_field in self.field_name_map:
                        field_name_matches.append(direction)
                    
                    # Also check for variations like "northern field"
                    directional_variations = [f"{direction}ern", f"{direction}ern field"]
                    for variation in directional_variations:
                        if variation in state.user_request.lower() and variation in self.field_name_map:
                            field_name_matches.append(variation)
            
            # Add recently mentioned fields for better context continuity
            if not field_name_matches and self.recent_mentions["fields"]:
                # Check if request implies continuing with the same field
                continuity_patterns = [
                    r"\b(there|it|that field|this field|the field|same field|this one)\b",
                    r"\b(check|status|moisture|temperature|irrigation)\b"
                ]
                
                has_continuity_marker = any(re.search(pattern, state.user_request, re.IGNORECASE) 
                                           for pattern in continuity_patterns)
                
                if has_continuity_marker:
                    field_name_matches.extend(self.recent_mentions["fields"])
            
            # Remove duplicates while preserving order
            entities["field_names"] = list(dict.fromkeys(field_name_matches))
            
            # Map field names to IDs for easier processing
            entities["field_name_to_id"] = {}
            for name in entities["field_names"]:
                clean_name = name.lower().strip()
                if clean_name in self.field_name_map:
                    entities["field_name_to_id"][clean_name] = self.field_name_map[clean_name]
                    
                    # Also check with "field" appended if not already present
                    if not clean_name.endswith("field"):
                        field_variant = f"{clean_name} field" 
                        if field_variant in self.field_name_map:
                            entities["field_name_to_id"][clean_name] = self.field_name_map[field_variant]
            
            # Extract actuator references with enhanced natural language understanding
            actuator_matches = []
            
            # First check for explicit actuator IDs
            actuator_matches.extend(entities["actuator_ids"])
            
            # Then check for natural language references to actuators
            for actuator_key in self.actuator_name_map:
                if actuator_key in state.user_request.lower():
                    actuator_matches.append(self.actuator_name_map[actuator_key])
            
            # Add recently mentioned actuators for continuity
            if not actuator_matches and self.recent_mentions["actuators"]:
                continuity_patterns = [
                    r"\b(it|that|this one|the equipment|the device|this device|same equipment)\b",
                    r"\b(status|open|close|turn on|turn off|activate|deactivate)\b"
                ]
                
                has_continuity_marker = any(re.search(pattern, state.user_request, re.IGNORECASE) 
                                           for pattern in continuity_patterns)
                
                if has_continuity_marker:
                    actuator_matches.extend(self.recent_mentions["actuators"])
            
            # Remove duplicates
            entities["actuator_ids"] = list(dict.fromkeys(actuator_matches))
            
            # Extract resource references
            resource_matches = []
            
            # First check for explicit resource IDs
            resource_matches.extend(entities["resource_ids"])
            
            # Then check for natural language references to resources
            for resource_key in self.resource_name_map:
                if resource_key in state.user_request.lower():
                    resource_matches.append(self.resource_name_map[resource_key])
            
            # Remove duplicates
            entities["resource_ids"] = list(dict.fromkeys(resource_matches))
            
            # Safely extract actuator type if present
            actuator_type_match = re.search(patterns["actuator_types"], state.user_request, re.IGNORECASE)
            regex_signals["actuator_type"] = actuator_type_match.group(0).lower() if actuator_type_match else None
            
            # Try to resolve field references
            if not entities["field_ids"] and not entities["field_names"]:
                field_id, field_name = self._extract_field_reference(state.user_request)
                if field_id:
                    entities["field_ids"] = [field_id]
                    entities["field_names"] = [field_name]

            # Try to resolve actuator references
            if not entities["actuator_ids"]:
                actuator_id, actuator_name = self._extract_actuator_reference(state.user_request)
                if actuator_id:
                    entities["actuator_ids"] = [actuator_id]
            
            
            # Include pre-fetched system information with richer context
            system_info_summary = {
                "field_count": len(self.system_info.get("fields", [])),
                "actuator_count": len(self.system_info.get("actuators", [])),
                "field_names": [field.get("name") for field in self.system_info.get("fields", [])],
                "actuator_types": list(set(actuator.get("type") for actuator in self.system_info.get("actuators", []))),
                "resource_types": list(set(resource.get("content") for resource in self.system_info.get("resources", []))),
                "active_fields": [
                    field.get("name") for field in self.system_info.get("fields", [])
                    if field.get("id") in self.status_cache.get("field_status", {}) and
                    self.status_cache["field_status"][field.get("id")].get("is_irrigating", False)
                ]
            }
            
            # Add conversation memory with improved context
            memory_context = ""
            if self.conversation_memory:
                last_exchanges = self.conversation_memory[-min(3, len(self.conversation_memory)):]
                memory_context = "Recent conversation:\n" + "\n".join([
                    f"User: {exchange['user']}\nAssistant: {exchange['assistant'][:100]}..."
                    for exchange in last_exchanges
                ])
    
            # Improved prompt construction for LLM with better context handling
            system_prompt = f"""
            You are an AI assistant for a smart farm system.
            Interpret the user's natural language command using the raw message, regex-derived metadata, 
            and the following system information.
            
            Be proactive and helpful - try to understand what the user wants to accomplish rather than
            focusing only on literal commands. Farmers speak naturally about their fields and equipment.

            System Information: {system_info_summary}

            {memory_context}

            If the intent is genuinely ambiguous with no way to determine what the user wants,
            return:
            {{
                "intent_type": "clarification_needed",
                "clarification": "<a polite and concise question to ask the user>"
            }}

            However, if you can reasonably infer the intent from context, prior conversation,
            or common farming requests, DO NOT ask for clarification. Make your best judgment.

            Return a structured intent object like:
            {{
                "intent_type": "<control_actuators|query_state|resource_management|...>",
                "action": "<close_actuator|get_resource_level|...>",
                "entities": {{
                    "actuator_ids": [...],
                    "field_ids": [...],
                    "resource_ids": [...]
                }},
                "parameters": {{
                    "new_status": "<open|close>", ...
                }}
            }}

            Remember that farmers often speak in natural terms. They might say "water the north field" instead of "open valve WV-0100".
            Focus on what they're trying to accomplish, not just literal commands.
            """
    
            human_prompt = json.dumps({
                "user_request": state.user_request,
                "regex_signals": regex_signals,
                "entities": entities
            }, indent=2, cls=DateTimeEncoder)
    
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ]
    
            response = self.llm.invoke(messages)
            content = response.content
    
            # Try to parse JSON from the LLM response with improved error handling
            try:
                json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
                if json_match:
                    intent_json = json.loads(json_match.group(1))
                else:
                    # Try to extract JSON from the plain text response
                    json_match = re.search(r'({.*})', content, re.DOTALL)
                    if json_match:
                        intent_json = json.loads(json_match.group(1))
                    else:
                        intent_json = json.loads(content)
            except json.JSONDecodeError:
                # If JSON parsing fails, try to infer intent directly from the request
                # This reduces unnecessary clarification requests
                intent_json = self._infer_intent_from_request(state.user_request, entities)
    
            self._log(f"LLM intent: {intent_json}")
    
            # Process common request patterns if LLM gave a clarification but we can handle it
            if intent_json.get("intent_type") == "clarification_needed":
                # Try to match common patterns - significantly expanded to reduce clarifications
                request_lower = state.user_request.lower()
                
                # Check for field irrigation requests - very common operation
                if (("irrigate" in request_lower or "water" in request_lower) and 
                        (entities["field_names"] or "all" in request_lower)):
                    
                    # Handle "irrigate all fields" specially
                    if "all" in request_lower and not entities["field_names"]:
                        intent_json = {
                            "intent_type": "irrigation_control",
                            "action": "start_irrigation_all_fields",
                            "entities": {
                                "field_ids": [field.get("id") for field in self.system_info.get("fields", [])],
                                "field_names": [field.get("name") for field in self.system_info.get("fields", [])]
                            },
                            "parameters": {
                                "duration": 30  # Default 30-minute irrigation
                            }
                        }
                    else:
                        # Single or multiple field irrigation
                        field_ids = []
                        field_names = []
                        
                        # Get IDs for all named fields
                        for field_name in entities["field_names"]:
                            field_id = entities["field_name_to_id"].get(field_name.lower())
                            if field_id:
                                field_ids.append(field_id)
                                field_names.append(field_name)
                        
                        if field_ids:
                            intent_json = {
                                "intent_type": "irrigation_control",
                                "action": "start_irrigation",
                                "entities": {
                                    "field_ids": field_ids,
                                    "field_names": field_names
                                },
                                "parameters": {
                                    "duration": 30  # Default 30-minute irrigation
                                }
                            }
                
                # Check for irrigation stop requests
                elif (("stop" in request_lower or "end" in request_lower or "turn off" in request_lower) and 
                      ("irrigation" in request_lower or "watering" in request_lower)):
                    
                    # Handle "stop all irrigation" specially
                    if "all" in request_lower and not entities["field_names"]:
                        # Find all currently irrigating fields
                        irrigating_fields = []
                        irrigating_names = []
                        
                        for field_id, status in self.status_cache.get("field_status", {}).items():
                            if status.get("is_irrigating", False):
                                irrigating_fields.append(field_id)
                                # Find field name
                                for field in self.system_info.get("fields", []):
                                    if field.get("id") == field_id:
                                        irrigating_names.append(field.get("name", ""))
                                        break
                        
                        if irrigating_fields:
                            intent_json = {
                                "intent_type": "irrigation_control",
                                "action": "stop_irrigation",
                                "entities": {
                                    "field_ids": irrigating_fields,
                                    "field_names": irrigating_names
                                },
                                "parameters": {}
                            }
                        else:
                            # No fields currently irrigating
                            intent_json = {
                                "intent_type": "information",
                                "action": "get_irrigation_status",
                                "entities": {},
                                "parameters": {}
                            }
                    elif entities["field_names"]:
                        # Stop irrigation for specific fields
                        field_ids = []
                        field_names = []
                        
                        # Get IDs for all named fields
                        for field_name in entities["field_names"]:
                            field_id = entities["field_name_to_id"].get(field_name.lower())
                            if field_id:
                                field_ids.append(field_id)
                                field_names.append(field_name)
                        
                        if field_ids:
                            intent_json = {
                                "intent_type": "irrigation_control",
                                "action": "stop_irrigation",
                                "entities": {
                                    "field_ids": field_ids,
                                    "field_names": field_names
                                },
                                "parameters": {}
                            }
                
                # Check for status requests about irrigation
                elif ("status" in request_lower or "check" in request_lower or 
                      "how is" in request_lower or "tell me about" in request_lower):
                    
                    # Check for field-specific status
                    if entities["field_names"]:
                        field_ids = []
                        field_names = []
                        
                        # Get IDs for all named fields
                        for field_name in entities["field_names"]:
                            field_id = entities["field_name_to_id"].get(field_name.lower())
                            if field_id:
                                field_ids.append(field_id)
                                field_names.append(field_name)
                        
                        if field_ids:
                            # Determine what aspect of the field they're asking about
                            if "irrigation" in request_lower or "watering" in request_lower:
                                intent_json = {
                                    "intent_type": "query_state",
                                    "action": "get_field_irrigation_status",
                                    "entities": {
                                        "field_ids": field_ids,
                                        "field_names": field_names
                                    },
                                    "parameters": {}
                                }
                            elif "moisture" in request_lower or "wetness" in request_lower or "humid" in request_lower:
                                intent_json = {
                                    "intent_type": "query_state",
                                    "action": "get_moisture_readings",
                                    "entities": {
                                        "field_ids": field_ids,
                                        "field_names": field_names
                                    },
                                    "parameters": {}
                                }
                            elif "temperature" in request_lower or "temp" in request_lower or "hot" in request_lower or "cold" in request_lower:
                                intent_json = {
                                    "intent_type": "query_state",
                                    "action": "get_temperature_readings",
                                    "entities": {
                                        "field_ids": field_ids,
                                        "field_names": field_names
                                    },
                                    "parameters": {}
                                }
                            else:
                                # General field status
                                intent_json = {
                                    "intent_type": "query_state",
                                    "action": "get_field_info",
                                    "entities": {
                                        "field_ids": field_ids,
                                        "field_names": field_names
                                    },
                                    "parameters": {}
                                }
                    else:
                        # General status queries
                        if "irrigation" in request_lower or "watering" in request_lower:
                            intent_json = {
                                "intent_type": "query_state",
                                "action": "get_all_irrigation_status",
                                "entities": {},
                                "parameters": {}
                            }
                        elif "equipment" in request_lower or "actuator" in request_lower or "device" in request_lower:
                            intent_json = {
                                "intent_type": "query_state",
                                "action": "get_all_actuator_status",
                                "entities": {},
                                "parameters": {}
                            }
                        elif "water" in request_lower or "level" in request_lower or "resource" in request_lower:
                            intent_json = {
                                "intent_type": "query_state",
                                "action": "get_resource_levels",
                                "entities": {},
                                "parameters": {}
                            }
                        else:
                            # General farm overview
                            intent_json = {
                                "intent_type": "query_state",
                                "action": "get_farm_overview",
                                "entities": {},
                                "parameters": {}
                            }
                
                # Check for equipment control - common operation
                elif (("open" in request_lower or "activate" in request_lower or "start" in request_lower or 
                       "turn on" in request_lower or "close" in request_lower or "deactivate" in request_lower or 
                       "stop" in request_lower or "turn off" in request_lower) and
                      ("valve" in request_lower or "pump" in request_lower or "equipment" in request_lower or
                       "device" in request_lower)):
                    
                    new_status = "open" if ("open" in request_lower or "activate" in request_lower or 
                                          "start" in request_lower or "turn on" in request_lower) else "close"
                    
                    # Check if specific actuators are mentioned
                    if entities["actuator_ids"]:
                        intent_json = {
                            "intent_type": "control_actuators",
                            "action": f"{new_status}_actuator",
                            "entities": {
                                "actuator_ids": entities["actuator_ids"]
                            },
                            "parameters": {
                                "new_status": new_status
                            }
                        }
                    elif entities["field_names"]:
                        # Control actuators in specific fields
                        field_ids = []
                        field_names = []
                        
                        # Get IDs for all named fields
                        for field_name in entities["field_names"]:
                            field_id = entities["field_name_to_id"].get(field_name.lower())
                            if field_id:
                                field_ids.append(field_id)
                                field_names.append(field_name)
                        
                        if field_ids:
                            # Try to determine actuator type from request
                            actuator_type = None
                            if "valve" in request_lower:
                                actuator_type = "water_valves"
                            elif "pump" in request_lower:
                                actuator_type = "pump"
                            elif "fertilizer" in request_lower:
                                actuator_type = "fertilizer_dispensers"
                            
                            intent_json = {
                                "intent_type": "control_actuators",
                                "action": f"{new_status}_field_actuators",
                                "entities": {
                                    "field_ids": field_ids,
                                    "field_names": field_names
                                },
                                "parameters": {
                                    "new_status": new_status,
                                    "actuator_type": actuator_type
                                }
                            }
                
                # Check for moisture queries
                elif entities["is_moisture_query"] and entities["field_names"]:
                    field_ids = []
                    field_names = []
                    
                    # Get IDs for all named fields
                    for field_name in entities["field_names"]:
                        field_id = entities["field_name_to_id"].get(field_name.lower())
                        if field_id:
                            field_ids.append(field_id)
                            field_names.append(field_name)
                    
                    if field_ids:
                        intent_json = {
                            "intent_type": "query_state",
                            "action": "get_moisture_readings",
                            "entities": {
                                "field_ids": field_ids,
                                "field_names": field_names
                            },
                            "parameters": {}
                        }
                
                # Check for temperature queries
                elif entities["is_temperature_query"] and entities["field_names"]:
                    field_ids = []
                    field_names = []
                    
                    # Get IDs for all named fields
                    for field_name in entities["field_names"]:
                        field_id = entities["field_name_to_id"].get(field_name.lower())
                        if field_id:
                            field_ids.append(field_id)
                            field_names.append(field_name)
                    
                    if field_ids:
                        intent_json = {
                            "intent_type": "query_state",
                            "action": "get_temperature_readings",
                            "entities": {
                                "field_ids": field_ids,
                                "field_names": field_names
                            },
                            "parameters": {}
                        }
                
                # Check for resource level queries
                elif ("water" in request_lower or "resource" in request_lower or "tank" in request_lower or 
                      "supply" in request_lower or "reservoir" in request_lower) and ("level" in request_lower or "how much" in request_lower or "status" in request_lower):
                    
                    # Handle specific resource queries
                    if entities["resource_ids"]:
                        intent_json = {
                            "intent_type": "query_state",
                            "action": "get_resource_levels",
                            "entities": {
                                "resource_ids": entities["resource_ids"]
                            },
                            "parameters": {}
                        }
                    else:
                        # Try to determine resource type
                        resource_type = None
                        if "water" in request_lower:
                            resource_type = "water"
                        elif "fertilizer" in request_lower:
                            resource_type = "fertilizer"
                        
                        intent_json = {
                            "intent_type": "query_state",
                            "action": "get_resource_levels",
                            "entities": {},
                            "parameters": {
                                "resource_type": resource_type
                            }
                        }
            
            # Update recent mentions for better continuity in future requests
            if intent_json != {"intent_type": "clarification_needed"}:
                # Update field mentions
                if "entities" in intent_json and "field_names" in intent_json["entities"] and intent_json["entities"]["field_names"]:
                    self.recent_mentions["fields"] = intent_json["entities"]["field_names"]
                
                # Update actuator mentions
                if "entities" in intent_json and "actuator_ids" in intent_json["entities"] and intent_json["entities"]["actuator_ids"]:
                    self.recent_mentions["actuators"] = intent_json["entities"]["actuator_ids"]
                
                # Update resource mentions
                if "entities" in intent_json and "resource_ids" in intent_json["entities"] and intent_json["entities"]["resource_ids"]:
                    self.recent_mentions["resources"] = intent_json["entities"]["resource_ids"]
            
            
            
            updated_state = FarmChatState(
                messages=state.messages,
                user_request=state.user_request,
                intent=intent_json,
                debug_logs=state.debug_logs + ["Intent extraction completed"]
            )
            return updated_state
            
        except Exception as e:
            error_message = f"Error analyzing request: {str(e)}"
            self._log(error_message)
            return FarmChatState(
                messages=state.messages,
                user_request=state.user_request,
                intent=None,
                error_occurred=True,
                error_message=error_message,
                debug_logs=state.debug_logs + [error_message]
            )
    
    
    
    def _extract_field_reference(self, text: str) -> Tuple[str, str]:
        """
        Extracts field references from text and returns a tuple of (field_id, field_name).
        Returns (None, None) if no reference found.
        """
        text_lower = text.lower()
        
        # First check for exact field name matches
        for field in self.system_info.get("fields", []):
            field_name = field.get("name", "").lower()
            if field_name and field_name in text_lower:
                return field.get("id"), field.get("name")
        
        # Then check for cardinal directions
        cardinal_directions = ["north", "south", "east", "west", "northeast", 
                            "northwest", "southeast", "southwest", "central"]
        
        for direction in cardinal_directions:
            if direction in text_lower:
                for field in self.system_info.get("fields", []):
                    field_name = field.get("name", "").lower()
                    if direction in field_name:
                        return field.get("id"), field.get("name")
        
        # Try to match by field number ("field 3")
        field_num_match = re.search(r'field\s+(\d+)', text_lower)
        if field_num_match:
            number = int(field_num_match.group(1))
            # Assuming field IDs might be like "F001", "F002", etc.
            potential_id = f"F{number:03d}"
            
            for field in self.system_info.get("fields", []):
                if field.get("id") == potential_id:
                    return potential_id, field.get("name")
        
        # Add specific handling for "first field", "second field", etc.
        ordinal_match = re.search(r'(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)\s+field', text_lower)
        if ordinal_match:
            ordinal_words = {"first": 0, "second": 1, "third": 2, "fourth": 3, 
                            "fifth": 4, "sixth": 5, "seventh": 6, "eighth": 7, "ninth": 8}
            index = ordinal_words.get(ordinal_match.group(1), 0)
            fields = self.system_info.get("fields", [])
            if 0 <= index < len(fields):
                return fields[index].get("id"), fields[index].get("name")
        
        # Add handling for recently mentioned fields in conversation
        if self.conversation_memory:
            for entry in reversed(self.conversation_memory):
                if "entities" in entry and "field" in entry["entities"]:
                    recent_field = entry["entities"]["field"]
                    self._log(f"Using recently mentioned field: {recent_field['name']}")
                    return recent_field["id"], recent_field["name"]
        
        return None, None
    
    def _extract_actuator_reference(self, text: str) -> Tuple[str, str]:
        """Extract actuator ID and name from text."""
        text_lower = text.lower()
        
        # Check for explicit actuator IDs with format like "FD-0900"
        actuator_id_match = re.search(r'([A-Z]+-\d{4})', text, re.IGNORECASE)
        if actuator_id_match:
            actuator_id = actuator_id_match.group(1)
            for actuator in self.system_info.get("actuators", []):
                if actuator.get("id") == actuator_id:
                    return actuator_id, actuator.get("name", "")
        
        # Check for actuator type references
        type_keywords = {
            "water valve": "water_valves",
            "pump": "pump",
            "fertilizer": "fertilizer_dispensers",
            "fertilizer dispenser": "fertilizer_dispensers",
            "dispenser": "fertilizer_dispensers"
        }
        
        for keyword, act_type in type_keywords.items():
            if keyword in text_lower:
                # Find actuators of this type
                matching_actuators = [a for a in self.system_info.get("actuators", []) 
                                    if a.get("type") == act_type]
                if matching_actuators:
                    # Return the first one or try to find one in the mentioned field
                    field_id, _ = self._extract_field_reference(text)
                    if field_id:
                        for actuator in matching_actuators:
                            if actuator.get("field_id") == field_id:
                                return actuator.get("id"), actuator.get("name", "")
                    
                    # If no field-specific match, return the first one
                    return matching_actuators[0].get("id"), matching_actuators[0].get("name", "")
        
        return None, None
            
    def _handle_error(self, state: FarmChatState) -> FarmChatState:
        """Handle errors and generate a helpful response."""
        error_message = state.error_message or "An unexpected error occurred"
        
        # Create a more informative error response based on context
        if "actuator" in error_message.lower():
            error_response = (
                f"I encountered an issue with the farm equipment. {error_message}. "
                f"This might be because the equipment ID wasn't recognized or the equipment is currently offline. "
                f"Try specifying the equipment by name (like 'north field water valve') or check your equipment status first."
            )
        elif "sensor" in error_message.lower():
            error_response = (
                f"There was a problem reading the farm sensors. {error_message}. "
                f"This could be due to a connectivity issue or the sensor might need maintenance. "
                f"Try asking about a specific field's sensors or check the system status."
            )
        elif "resource" in error_message.lower():
            error_response = (
                f"I had trouble accessing information about the farm resources. {error_message}. "
                f"You might want to check if the resource names are correct or try asking about specific resources like 'water tank' or 'fertilizer storage'."
            )
        else:
            error_response = (
                f"I'm sorry, I encountered an issue while processing your farm request: {error_message}. "
                f"Could you try rephrasing your request? You can ask about specific fields, equipment status, or start with 'show me an overview of my farm'."
            )
        
        state.response = error_response
        return state
    
    def _check_clarification(self, state: FarmChatState) -> FarmChatState:
        """
        Check if clarification is needed before proceeding.
        Significantly improved to reduce unnecessary clarification requests.
        """
        if not state.intent:
            state.clarification_needed = True
            state.clarification_question = "I'm not sure what you're asking about your farm. Could you please provide more details or rephrase your request?"
            return state
            
        intent_type = state.intent.get("intent_type", "")
        if intent_type == "clarification_needed":
            # Try field reference resolution first
            field_id, field_name = self._extract_field_reference(state.user_request)
            if field_id:
                # Update intent with resolved field
                if "entities" not in state.intent:
                    state.intent["entities"] = {}
                state.intent["entities"]["field_ids"] = [field_id]
                state.intent["entities"]["field_names"] = [field_name]
                state.clarification_needed = False
                return state
                
            # Try actuator reference resolution
            actuator_id, actuator_name = self._extract_actuator_reference(state.user_request)
            if actuator_id:
                if "entities" not in state.intent:
                    state.intent["entities"] = {}
                state.intent["entities"]["actuator_ids"] = [actuator_id]
                state.clarification_needed = False
                return state

            state.clarification_needed = True
            clarification = state.intent.get("clarification", "Could you provide more details?")
            state.clarification_question = clarification
            return state

        
        # If we have a valid intent type other than clarification_needed, we only ask for 
        # clarification in very specific cases where it's genuinely needed
        
        # For irrigation requests, check if we have field information
        if intent_type == "irrigation_control":
            entities = state.intent.get("entities", {})
            if not entities.get("field_ids") and not entities.get("field_names"):
                # Check if we can infer from recent context
                if self.recent_mentions["fields"]:
                    # Add the recent field to the intent to avoid unnecessary clarification
                    field_name = self.recent_mentions["fields"][0]
                    field_id = None
                    
                    # Find the field ID
                    for field in self.system_info.get("fields", []):
                        if field.get("name", "").lower() == field_name.lower():
                            field_id = field.get("id")
                            break
                    
                    if field_id:
                        # Update the intent with the recent field
                        if "entities" not in state.intent:
                            state.intent["entities"] = {}
                        
                        state.intent["entities"]["field_ids"] = [field_id]
                        state.intent["entities"]["field_names"] = [field_name]
                        return state
                
                # Otherwise, ask for clarification
                state.clarification_needed = True
                
                # Get a list of available fields for more helpful clarification
                field_names = [field.get("name") for field in self.system_info.get("fields", [])[:5]]
                field_list = ", ".join(field_names)
                
                state.clarification_question = f"Which field would you like to irrigate? Available fields include: {field_list}, etc."
                return state
                
        elif intent_type == "control_actuators":
            # For equipment control, check if we have actuator information or field context
            entities = state.intent.get("entities", {})
            if not entities.get("actuator_ids") and not entities.get("field_ids") and not entities.get("field_names"):
                # Check if we can infer from recent context
                if self.recent_mentions["actuators"]:
                    # Add the recent actuator to the intent to avoid unnecessary clarification
                    actuator_id = self.recent_mentions["actuators"][0]
                    
                    if "entities" not in state.intent:
                        state.intent["entities"] = {}
                    
                    state.intent["entities"]["actuator_ids"] = [actuator_id]
                    return state
                
                # Otherwise, ask for clarification
                state.clarification_needed = True
                state.clarification_question = "Which equipment would you like to control? Please specify a field or equipment name, like 'North Field valve' or 'main pump'."
                return state
        
        # For other intent types, we don't need clarification - we'll use available context
        return state

    def _get_clarification(self, state: FarmChatState) -> FarmChatState:
        """Process clarification needs and prepare more helpful response asking for information."""
        # Add the clarification question to response with more context about available options
        
        clarification = state.clarification_question
        
        # Add helpful context based on the type of clarification needed
        if "field" in clarification.lower():
            fields = [field.get("name") for field in self.system_info.get("fields", [])]
            if fields:
                # Group fields by crop for more natural suggestions
                fields_by_crop = {}
                for field in self.system_info.get("fields", []):
                    crop = field.get("crop", "Unknown")
                    if crop not in fields_by_crop:
                        fields_by_crop[crop] = []
                    fields_by_crop[crop].append(field.get("name"))
                
                # Add field options by crop
                clarification += "\n\nAvailable fields:"
                for crop, crop_fields in fields_by_crop.items():
                    if len(crop_fields) > 0:
                        clarification += f"\n• {crop}: {', '.join(crop_fields)}"
        
        elif "equipment" in clarification.lower() or "actuator" in clarification.lower():
            # Add info about equipment types by field for more natural interaction
            equipment_by_field = {}
            for actuator in self.system_info.get("actuators", []):
                field_id = actuator.get("field_id")
                actuator_type = actuator.get("type", "").replace("_", " ")
                
                field_name = "General"
                for field in self.system_info.get("fields", []):
                    if field.get("id") == field_id:
                        field_name = field.get("name")
                        break
                
                if field_name not in equipment_by_field:
                    equipment_by_field[field_name] = set()
                
                equipment_by_field[field_name].add(actuator_type)
            
            if equipment_by_field:
                clarification += "\n\nAvailable equipment:"
                for field, equipment in equipment_by_field.items():
                    clarification += f"\n• {field}: {', '.join(equipment)}"
                
        elif "resource" in clarification.lower():
            # Add info about resource types with current levels
            resources = self.status_cache.get("resource_levels", {})
            if resources:
                clarification += "\n\nAvailable resources:"
                for resource_id, resource_info in resources.items():
                    name = resource_info.get("name", "Unknown")
                    content = resource_info.get("content", "")
                    current = resource_info.get("current_level", "Unknown")
                    
                    resource_text = f"• {name}"
                    if content:
                        resource_text += f" ({content})"
                    resource_text += f": {current}"
                    
                    clarification += f"\n{resource_text}"
        
        state.response = clarification
        return state
    
    def _identify_scenario(self, state: FarmChatState) -> FarmChatState:
        """Identify the scenario based on the extracted intent."""
        scenarios = {
            "irrigation": ["irrigate", "water", "hydrate", "spray", "wet", "drip", "moist"],
            "monitoring": ["check", "monitor", "read", "measure", "status", "level", "how much", "how many"],
            "resource_management": ["refill", "drain", "empty", "fill", "transfer", "level"],
            "system_control": ["activate", "deactivate", "start", "stop", "turn on", "turn off", "open", "close"],
            "maintenance": ["clean", "fix", "repair", "maintain", "calibrate"],
            "information": ["tell", "show", "list", "display", "report", "summarize", "what is"]
        }
        
        # Ensure we have a valid intent
        if not state.intent:
            state.scenario = "information"
            return state
            
        # Special handling for irrigation intents
        if state.intent.get("intent_type") == "irrigation_control":
            state.scenario = "irrigation"
            return state
            
        # Determine the most likely scenario based on the action verb and request content
        action = state.intent.get("action", "").lower()
        intent_type = state.intent.get("intent_type", "").lower()
        user_request = state.user_request.lower()
        scenario = "unknown"
        
        # Check action verb first
        for key, verbs in scenarios.items():
            if any(verb in action for verb in verbs):
                scenario = key
                break
                
        # If still unknown, check intent_type
        if scenario == "unknown":
            for key, terms in scenarios.items():
                if any(term in intent_type for term in terms):
                    scenario = key
                    break
        
        # If still unknown, check the full request
        if scenario == "unknown":
            for key, terms in scenarios.items():
                if any(term in user_request for term in terms):
                    scenario = key
                    break
                    
        # Default to information if still unknown
        if scenario == "unknown":
            scenario = "information"
        
        state.scenario = scenario
        return state
    
    def _infer_intent_from_request(self, request: str, entities: Dict) -> Dict:
        """
        Directly infer intent from user request when LLM fails to provide a clear intent.
        This significantly reduces unnecessary clarification requests.
        """
        request_lower = request.lower()
        
        # Check for irrigation commands
        if "irrigate" in request_lower or "water" in request_lower:
            if entities["field_names"]:
                field_ids = []
                field_names = []
                
                # Get IDs for all named fields
                for field_name in entities["field_names"]:
                    field_id = entities["field_name_to_id"].get(field_name.lower())
                    if field_id:
                        field_ids.append(field_id)
                        field_names.append(field_name)
                
                if field_ids:
                    return {
                        "intent_type": "irrigation_control",
                        "action": "start_irrigation",
                        "entities": {
                            "field_ids": field_ids,
                            "field_names": field_names
                        },
                        "parameters": {
                            "duration": 30  # Default 30-minute irrigation
                        }
                    }
            
            # If no specific field, but "all" is mentioned
            if "all" in request_lower:
                return {
                    "intent_type": "irrigation_control",
                    "action": "start_irrigation_all_fields",
                    "entities": {
                        "field_ids": [field.get("id") for field in self.system_info.get("fields", [])],
                        "field_names": [field.get("name") for field in self.system_info.get("fields", [])]
                    },
                    "parameters": {
                        "duration": 30  # Default 30-minute irrigation
                    }
                }
        
        # Check for status queries
        if "status" in request_lower or "how is" in request_lower or "check" in request_lower:
            if entities["field_names"]:
                field_ids = []
                field_names = []
                
                # Get IDs for all named fields
                for field_name in entities["field_names"]:
                    field_id = entities["field_name_to_id"].get(field_name.lower())
                    if field_id:
                        field_ids.append(field_id)
                        field_names.append(field_name)
                
                if field_ids:
                    return {
                        "intent_type": "query_state",
                        "action": "get_field_info",
                        "entities": {
                            "field_ids": field_ids,
                            "field_names": field_names
                        },
                        "parameters": {}
                    }
            else:
                # General farm status
                return {
                    "intent_type": "query_state",
                    "action": "get_farm_overview",
                    "entities": {},
                    "parameters": {}
                }
        
        # If all else fails, ask for clarification
        return {
            "intent_type": "clarification_needed",
            "clarification": "I'm not entirely sure what you'd like to do with your farm system. Could you please provide more details or rephrase your request?"
        }
    
    def _fetch_context(self, state: FarmChatState) -> FarmChatState:
        """Fetch context information relevant to the intent and scenario."""
        context = {
            "farms": [],
            "fields": [],
            "resources": [],
            "actuators": [],
            "sensors": [],
            "data": {},
            "metadata": {}
        }
        
        try:
            
            # Update status cache first
            self._update_status_cache()
            
            # Add cached active actuators
            if self.status_cache.get("active_actuators"):
                context["data"]["active_actuators"] = self.status_cache["active_actuators"]
                
            # Add cached field status
            if self.status_cache.get("field_status"):
                context["data"]["field_status"] = self.status_cache["field_status"]
                
            # Add cached resource levels
            if self.status_cache.get("resource_levels"):
                context["data"]["resource_levels"] = self.status_cache["resource_levels"]

            # Extract target entities from intent (safely)
            if not state.intent:
                # Return empty context if no intent
                state.context = context
                return state
                
            entities = state.intent.get("entities", {})
            field_ids = entities.get("field_ids", [])
            field_names = entities.get("field_names", [])
            actuator_ids = entities.get("actuator_ids", [])
            parameters = state.intent.get("parameters", {})
            
            # Update cache before fetching context
            self._update_status_cache()
            
            # Handle different scenarios
            if state.scenario == "irrigation":
                # For irrigation, we need field info and irrigation-related actuators
                if field_ids:
                    # Get fields by ID
                    for field_id in field_ids:
                        field = self.farm_control_service.get_field_by_id(field_id, include_related=True)
                        if field:
                            context["fields"].append(field)
                            
                            # Get actuators for this field
                            field_actuators = self.farm_control_service.get_actuators_by_field(field_id)
                            context["actuators"].extend(field_actuators)
                            
                            # Get water resources
                            water_resources = [res for res in self.farm_control_service.get_all_resources()
                                              if "water" in res.get("content", "").lower()]
                            context["resources"].extend(water_resources)
                            
                            # Get soil moisture sensors
                            field_sensors = self.farm_control_service.get_sensors_by_field(field_id)
                            moisture_sensors = [s for s in field_sensors if "moist" in s.get("type", "").lower()]
                            context["sensors"].extend(moisture_sensors)
                
                elif field_names:
                    # Get fields by name
                    for field_name in field_names:
                        field = self.farm_control_service.get_field_by_name(field_name, include_related=True)
                        if field:
                            context["fields"].append(field)
                            field_id = field.get("id")
                            
                            # Get actuators for this field
                            field_actuators = self.farm_control_service.get_actuators_by_field(field_id)
                            context["actuators"].extend(field_actuators)
                            
                            # Get water resources
                            water_resources = [res for res in self.farm_control_service.get_all_resources()
                                              if "water" in res.get("content", "").lower()]
                            context["resources"].extend(water_resources)
                            
                            # Get soil moisture sensors
                            field_sensors = self.farm_control_service.get_sensors_by_field(field_id)
                            moisture_sensors = [s for s in field_sensors if "moist" in s.get("type", "").lower()]
                            context["sensors"].extend(moisture_sensors)
                else:
                    # No specific field mentioned, get active irrigation information
                    active_fields = []
                    for field_id, status in self.status_cache.get("field_status", {}).items():
                        if status.get("is_irrigating", False):
                            field = self.farm_control_service.get_field_by_id(field_id, include_related=True)
                            if field:
                                active_fields.append(field)
                    
                    if active_fields:
                        context["fields"] = active_fields
                    else:
                        # No active irrigation, get all fields
                        context["fields"] = self.farm_control_service.get_all_fields()
                    
                    # Get all irrigation actuators
                    water_valves = self.farm_control_service.get_actuator_by_type("water_valves")
                    context["actuators"].extend(water_valves)
                    water_pumps = self.farm_control_service.get_actuator_by_type("pump")
                    context["actuators"].extend(water_pumps)
                    
                    # Get water resources
                    water_resources = [res for res in self.farm_control_service.get_all_resources()
                                      if "water" in res.get("content", "").lower()]
                    context["resources"].extend(water_resources)
            
            elif state.scenario == "monitoring":
                # For monitoring, fetch sensor data based on target
                if field_ids:
                    # Get fields by ID
                    for field_id in field_ids:
                        field = self.farm_control_service.get_field_by_id(field_id, include_related=True)
                        if field:
                            context["fields"].append(field)
                            
                            # Get sensors for this field
                            field_sensors = self.farm_control_service.get_sensors_by_field(field_id)
                            context["sensors"].extend(field_sensors)
                            
                            # If moisture or temperature query, filter sensors
                            if state.intent.get("action") == "get_moisture_readings":
                                context["sensors"] = [s for s in context["sensors"] if "moist" in s.get("type", "").lower()]
                            elif state.intent.get("action") == "get_temperature_readings":
                                context["sensors"] = [s for s in context["sensors"] if "temp" in s.get("type", "").lower()]
                
                elif field_names:
                    # Get fields by name
                    for field_name in field_names:
                        field = self.farm_control_service.get_field_by_name(field_name, include_related=True)
                        if field:
                            context["fields"].append(field)
                            field_id = field.get("id")
                            
                            # Get sensors for this field
                            field_sensors = self.farm_control_service.get_sensors_by_field(field_id)
                            context["sensors"].extend(field_sensors)
                            
                            # If moisture or temperature query, filter sensors
                            if state.intent.get("action") == "get_moisture_readings":
                                context["sensors"] = [s for s in context["sensors"] if "moist" in s.get("type", "").lower()]
                            elif state.intent.get("action") == "get_temperature_readings":
                                context["sensors"] = [s for s in context["sensors"] if "temp" in s.get("type", "").lower()]
                
                # Check if we're querying resources
                if "resource" in state.intent.get("action", "").lower():
                    resource_type = parameters.get("resource_type")
                    if resource_type:
                        # Filter resources by type
                        resources = [res for res in self.farm_control_service.get_all_resources()
                                    if resource_type.lower() in res.get("content", "").lower()]
                        context["resources"] = resources
                    else:
                        # Get all resources
                        context["resources"] = self.farm_control_service.get_all_resources()
            
            elif state.scenario == "system_control":
                # For system control, get information about actuators
                if actuator_ids:
                    # Get specific actuators
                    for actuator_id in actuator_ids:
                        actuator = self.farm_control_service.get_actuator_by_id(actuator_id)
                        if actuator:
                            context["actuators"].append(actuator)
                            
                            # Get associated resources
                            if "resources" in actuator:
                                for resource in actuator["resources"]:
                                    resource_id = resource.get("id")
                                    if resource_id:
                                        resource_obj = self.farm_control_service.get_resource_by_id(resource_id)
                                        if resource_obj:
                                            context["resources"].append(resource_obj)
                
                elif field_ids or field_names:
                    # Get actuators for specific fields
                    target_field_ids = field_ids.copy()
                    
                    # Convert field names to IDs if needed
                    for field_name in field_names:
                        field = self.farm_control_service.get_field_by_name(field_name)
                        if field:
                            target_field_ids.append(field.get("id"))
                    
                    for field_id in target_field_ids:
                        field = self.farm_control_service.get_field_by_id(field_id, include_related=True)
                        if field:
                            context["fields"].append(field)
                            
                            # Get actuators for this field
                            field_actuators = self.farm_control_service.get_actuators_by_field(field_id)
                            context["actuators"].extend(field_actuators)
                            
                            # If controlling water-related actuators, add water resources
                            actuator_type = parameters.get("actuator_type", "").lower()
                            if any(water_term in actuator_type for water_term in ["water", "irrigation", "valve", "pump"]):
                                water_resources = [res for res in self.farm_control_service.get_all_resources()
                                                 if "water" in res.get("content", "").lower()]
                                context["resources"].extend(water_resources)
                
                else:
                    # No specific target, determine by intent or parameters
                    actuator_type = parameters.get("actuator_type", "").lower()
                    if any(water_term in actuator_type for water_term in ["water", "irrigation", "valve", "pump"]):
                        # Water-related actuators
                        water_valves = self.farm_control_service.get_actuator_by_type("water_valves")
                        context["actuators"].extend(water_valves)
                        water_pumps = self.farm_control_service.get_actuator_by_type("pump")
                        context["actuators"].extend(water_pumps)
                        
                        # Get water resources
                        water_resources = [res for res in self.farm_control_service.get_all_resources()
                                          if "water" in res.get("content", "").lower()]
                        context["resources"].extend(water_resources)
                    
                    elif any(fert_term in actuator_type for fert_term in ["fertilizer", "nutrient"]):
                        # Fertilizer-related actuators
                        fertilizer_dispensers = self.farm_control_service.get_actuator_by_type("fertilizer_dispensers")
                        context["actuators"].extend(fertilizer_dispensers)
                        
                        # Get fertilizer resources
                        fertilizer_resources = [res for res in self.farm_control_service.get_all_resources()
                                              if any(f_term in res.get("content", "").lower() 
                                                    for f_term in ["fertilizer", "nutrient", "npk", "urea"])]
                        context["resources"].extend(fertilizer_resources)
                    
                    else:
                        # Get all actuators if target is not specific
                        context["actuators"] = self.farm_control_service.get_all_actuators()
            
            elif state.scenario == "resource_management":
                # For resource management, get information about resources
                resource_type = parameters.get("resource_type")
                if resource_type:
                    # Filter resources by type
                    resources = [res for res in self.farm_control_service.get_all_resources()
                                if resource_type.lower() in res.get("content", "").lower()]
                    context["resources"] = resources
                else:
                    # Get all resources
                    context["resources"] = self.farm_control_service.get_all_resources()
                
                # Get actuators that use these resources
                for resource in context["resources"]:
                    resource_id = resource.get("id")
                    if resource_id:
                        resource_actuators = self.farm_control_service.get_resource_dependent_actuators(resource_id)
                        if isinstance(resource_actuators, list):
                            context["actuators"].extend(resource_actuators)
            
            else:
                # For other scenarios or information requests, get general farm information
                if field_ids or field_names:
                    # Get specific fields
                    target_field_ids = field_ids.copy()
                    
                    # Convert field names to IDs if needed
                    for field_name in field_names:
                        field = self.farm_control_service.get_field_by_name(field_name)
                        if field:
                            target_field_ids.append(field.get("id"))
                    
                    for field_id in target_field_ids:
                        field = self.farm_control_service.get_field_by_id(field_id, include_related=True)
                        if field:
                            context["fields"].append(field)
                            
                            # Get sensors for this field
                            field_sensors = self.farm_control_service.get_sensors_by_field(field_id)
                            context["sensors"].extend(field_sensors)
                            
                            # Get actuators for this field
                            field_actuators = self.farm_control_service.get_actuators_by_field(field_id)
                            context["actuators"].extend(field_actuators)
                else:
                    # Get general farm information
                    context["farms"] = self.farm_control_service.get_all_farms()
                    context["fields"] = self.farm_control_service.get_all_fields()
                    
                    # If asking about active equipment
                    if "active" in state.intent.get("action", "").lower():
                        context["actuators"] = self.farm_control_service.get_active_actuators()
                    
                    # Add resource information for completeness
                    context["resources"] = self.farm_control_service.get_all_resources()
        
        except Exception as e:
            error_message = f"Error fetching context: {str(e)}"
            self._log(error_message)
            # Return empty context on error
            
        # De-duplicate entries in context lists by ID
        for key in context:
            if isinstance(context[key], list) and len(context[key]) > 0:
                # Use a dictionary to de-duplicate while preserving order
                deduped = {}
                for item in context[key]:
                    if "id" in item:
                        deduped[item["id"]] = item
                context[key] = list(deduped.values())
            
        state.context = context
        return state
        
    def _plan_actions(self, state: FarmChatState) -> FarmChatState:
        """Plan actions based on intent, scenario, and context."""
        if not state.context:
            state.plan = []
            return state
        
        # For general inquiry/information requests without actions, skip planning
        if state.scenario == "information" and not state.intent.get("action", "").startswith("get_"):
            state.plan = []
            return state
            
        # Convert context to a string representation for the LLM
        context_summary = {
            "fields": [
                {
                    "id": field.get("id"),
                    "name": field.get("name"),
                    "crop": field.get("crop"),
                    "area": field.get("area")
                } for field in state.context.get("fields", [])
            ],
            "actuators": [
                {
                    "id": act.get("id"),
                    "name": act.get("name", ""),
                    "type": act.get("type"),
                    "status": act.get("status"),
                    "field_id": act.get("field_id")
                } for act in state.context.get("actuators", [])
            ],
            "sensors": [
                {
                    "id": sensor.get("id"),
                    "type": sensor.get("type"),
                    "field_id": sensor.get("field_id"),
                    "unit": sensor.get("unit")
                } for sensor in state.context.get("sensors", [])
            ],
            "resources": [
                {
                    "id": res.get("id"),
                    "name": res.get("name"),
                    "capacity": res.get("capacity"),
                    "current_level": res.get("current_level"),
                    "content": res.get("content")
                } for res in state.context.get("resources", [])
            ]
        }
        
        context_str = json.dumps(context_summary, indent=2, cls=DateTimeEncoder)
        intent_str = json.dumps(state.intent, indent=2, cls=DateTimeEncoder) if state.intent else "{}"
        
        # Define the prompt for action planning with properly escaped JSON template
        planning_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a farm management AI assistant that helps plan actions for farm operations.
                        Based on the user's intent and available context, create a detailed action plan.
                        
                        The action plan should include concrete steps that can be executed by the farm control system.
                        Be realistic and specific - don't invent actions or IDs not present in the context.
                        
                        Return a JSON array of action objects with the following structure:
                        [
                            {{
                                "action_type": "The type of action (activate_actuator, deactivate_actuator, check_sensor, update_resource, etc.)",
                                "target_id": "The ID of the target entity (actuator, sensor, resource, etc.)",
                                "target_name": "The name of the target for reference",
                                "parameters": {{
                                    "status": "For actuators, the desired status (open/close)",
                                    "duration": "Duration in minutes if applicable",
                                    "value": "For resource updates, the new value"
                                }},
                                "reason": "Why this action is necessary based on the intent"
                            }}
                        ]
                        
                        If there are no entities in the context that match what the user is asking for,
                        return an empty array and don't invent actions that can't be executed.
                        
                        Remember:
                        - Water valves need pumps to be active - when opening valves, also open their linked pumps
                        - Resources have limited capacity - check levels before operating
                        - Think about farm operations logically - e.g., for irrigation, check moisture first
                        - For bulk operations on multiple fields, include separate actions for each field"""),
            ("human", """
                        User Request: {user_request}
                        
                        Extracted Intent: {intent_str}
                        
                        Scenario: {scenario}
                        
                        Available Context:
                        {context_str}
                        
                        Please create an action plan to address the user's request.
                        """)
        ])
        
        # Define custom handling for common scenarios to avoid LLM variability
        
        # 1. Irrigation start
        if (state.scenario == "irrigation" and 
            state.intent.get("action") == "start_irrigation" and 
            state.context.get("fields")):
            
            plan = []
            
            for field in state.context.get("fields", []):
                field_id = field.get("id")
                field_name = field.get("name")
                
                # Check if the field is already being irrigated
                field_status = self.status_cache.get("field_status", {}).get(field_id, {})
                if field_status.get("is_irrigating", False):
                    # Field already irrigating, no action needed
                    continue
                
                # Find water valves for this field
                water_valves = [act for act in state.context.get("actuators", [])
                               if act.get("field_id") == field_id and
                               act.get("type") == "water_valves"]
                
                for valve in water_valves:
                    # Add valve open action
                    plan.append({
                        "action_type": "activate_actuator",
                        "target_id": valve.get("id"),
                        "target_name": valve.get("name", f"Water valve for {field_name}"),
                        "parameters": {
                            "status": "open",
                            "duration": state.intent.get("parameters", {}).get("duration", 30)
                        },
                        "reason": f"Opening water valve to irrigate {field_name}"
                    })
                    
                    # Find and add linked pump actions
                    linked_pumps = valve.get("linked_pumps", [])
                    for pump in linked_pumps:
                        pump_id = pump.get("id")
                        if pump_id:
                            plan.append({
                                "action_type": "activate_actuator",
                                "target_id": pump_id,
                                "target_name": pump.get("name", "Water pump"),
                                "parameters": {
                                    "status": "open"
                                },
                                "reason": f"Activating pump for water supply to {field_name}"
                            })
            
            state.plan = plan
            return state
            
        # 2. Irrigation stop
        elif (state.scenario == "irrigation" and 
              state.intent.get("action") == "stop_irrigation" and 
              state.context.get("fields")):
            
            plan = []
            
            for field in state.context.get("fields", []):
                field_id = field.get("id")
                field_name = field.get("name")
                
                # Check if the field is currently being irrigated
                field_status = self.status_cache.get("field_status", {}).get(field_id, {})
                if not field_status.get("is_irrigating", False):
                    # Field not irrigating, no action needed
                    continue
                
                # Find water valves for this field
                water_valves = [act for act in state.context.get("actuators", [])
                               if act.get("field_id") == field_id and
                               act.get("type") == "water_valves" and
                               act.get("status") == "open"]
                
                for valve in water_valves:
                    # Add valve close action
                    plan.append({
                        "action_type": "deactivate_actuator",
                        "target_id": valve.get("id"),
                        "target_name": valve.get("name", f"Water valve for {field_name}"),
                        "parameters": {
                            "status": "close"
                        },
                        "reason": f"Closing water valve to stop irrigation in {field_name}"
                    })
            
            state.plan = plan
            return state
            
        # 3. Check moisture
        elif (state.intent.get("action") == "get_moisture_readings" and 
              state.context.get("fields") and
              state.context.get("sensors")):
            
            plan = []
            
            for field in state.context.get("fields", []):
                field_id = field.get("id")
                field_name = field.get("name")
                
                # Find moisture sensors for this field
                moisture_sensors = [sensor for sensor in state.context.get("sensors", [])
                                   if sensor.get("field_id") == field_id and
                                   "moist" in sensor.get("type", "").lower()]
                
                for sensor in moisture_sensors:
                    plan.append({
                        "action_type": "check_sensor",
                        "target_id": sensor.get("id"),
                        "target_name": f"Moisture sensor in {field_name}",
                        "parameters": {},
                        "reason": f"Checking soil moisture levels in {field_name}"
                    })
            
            state.plan = plan
            return state
        
                    # For other scenarios, use the LLM
        try:
            # Generate action plan using the LLM
            planning_chain = planning_prompt | self.llm | JsonOutputParser()
            plan = planning_chain.invoke({
                "user_request": state.user_request,
                "intent_str": intent_str,
                "scenario": state.scenario,
                "context_str": context_str
            })
            
            # Ensure we get a list back
            if not isinstance(plan, list):
                plan = []
                
            state.plan = plan
            return state
            
        except Exception as e:
            error_message = f"Error planning actions: {str(e)}"
            self._log(error_message)
            state.plan = []
            
        return state
    
    def _check_confirmation(self, state: FarmChatState) -> FarmChatState:
        """Check if the planned actions require user confirmation before executing."""
        if not state.plan:
            state.confirmation_needed = False
            return state
            
        # Determine if actions are risky or significant enough to require confirmation
        needs_confirmation = False
        confirmation_reasons = []
        
        # Check for bulk operations (multiple actions of same type)
        action_types = {}
        for action in state.plan:
            action_type = action.get("action_type")
            if action_type in action_types:
                action_types[action_type] += 1
            else:
                action_types[action_type] = 1
                
        # If we're activating multiple actuators, that's a bulk operation
        if action_types.get("activate_actuator", 0) > 2:
            needs_confirmation = True
            confirmation_reasons.append(f"This will activate {action_types['activate_actuator']} pieces of equipment")
        
        # If we're deactivating multiple actuators, that's a bulk operation
        if action_types.get("deactivate_actuator", 0) > 2:
            needs_confirmation = True
            confirmation_reasons.append(f"This will deactivate {action_types['deactivate_actuator']} pieces of equipment")
            
        # Check for resource updates (potentially risky)
        if action_types.get("update_resource", 0) > 0:
            needs_confirmation = True
            confirmation_reasons.append("This will modify resource levels in your farm system")
            
        # Check for irrigation actions on fields that might not need it
        fields_to_irrigate = []
        for action in state.plan:
            if action.get("action_type") == "activate_actuator":
                target_id = action.get("target_id")
                if target_id:
                    # Find the actuator in the context
                    for actuator in state.context.get("actuators", []):
                        if actuator.get("id") == target_id and actuator.get("type") in ["water_valves"]:
                            field_id = actuator.get("field_id")
                            if field_id:
                                # Check if we have moisture data for this field
                                field_status = self.status_cache.get("field_status", {}).get(field_id, {})
                                if field_status.get("has_moisture_sensors", False):
                                    for field in state.context.get("fields", []):
                                        if field.get("id") == field_id:
                                            fields_to_irrigate.append(field.get("name", "Unknown field"))
                                            break
        
        if fields_to_irrigate:
            needs_confirmation = True
            if len(fields_to_irrigate) == 1:
                confirmation_reasons.append(f"This will start irrigation in {fields_to_irrigate[0]}")
            else:
                confirmation_reasons.append(f"This will start irrigation in multiple fields: {', '.join(fields_to_irrigate)}")
                
        # Set confirmation state
        state.confirmation_needed = needs_confirmation
        if needs_confirmation:
            # Create summary of actions for confirmation
            action_summary = {}
            for action in state.plan:
                action_type = action.get("action_type")
                target_name = action.get("target_name", "Unknown")
                if action_type not in action_summary:
                    action_summary[action_type] = []
                action_summary[action_type].append(target_name)
                
            # Store details for confirmation message
            state.confirmation_details = {
                "reasons": confirmation_reasons,
                "action_summary": action_summary
            }
            
        return state
    
    def _get_confirmation(self, state: FarmChatState) -> FarmChatState:
        """Create a confirmation message for the user to approve actions."""
        if not state.confirmation_details:
            # No confirmation details, skip confirmation
            state.confirmation_needed = False
            state.response = "Sorry, I couldn't determine what actions need confirmation. Please try your request again."
            return state
        
        # Build a user-friendly confirmation message
        reasons = state.confirmation_details.get("reasons", [])
        action_summary = state.confirmation_details.get("action_summary", {})
        
        confirmation_message = "I need your confirmation before proceeding with these actions:\n\n"
        
        # Add reasons for confirmation
        for reason in reasons:
            confirmation_message += f"• {reason}\n"
            
        confirmation_message += "\nHere's what I'm planning to do:\n"
        
        # Add action summary
        for action_type, targets in action_summary.items():
            # Format action type for display
            display_action = action_type.replace("_", " ").title()
            
            if len(targets) <= 3:
                # List all targets for small lists
                targets_str = ", ".join(targets)
                confirmation_message += f"• {display_action}: {targets_str}\n"
            else:
                # Summarize for longer lists
                confirmation_message += f"• {display_action}: {len(targets)} devices including {', '.join(targets[:2])} and others\n"
                
        # Add confirmation request
        confirmation_message += "\nShould I proceed with these actions? Please confirm with 'yes' or suggest modifications."
        
        state.response = confirmation_message
        return state

    def _execute_actions(self, state: FarmChatState) -> FarmChatState:
        """Execute the planned actions using the farm control service."""
        results = []
        
        # If no plan, return empty results
        if not state.plan:
            state.execution_results = []
            return state
            
        for action in state.plan:
            action_type = action.get("action_type", "")
            target_id = action.get("target_id")
            parameters = action.get("parameters", {})
            
            result = {
                "action": action,
                "success": False,
                "details": {},
                "error": None
            }
            
            # Skip if no target_id
            if not target_id:
                result["error"] = "No target ID provided"
                results.append(result)
                continue
                
            try:
                if action_type == "activate_actuator":
                    # Activate an actuator (open valve, start pump, etc.)
                    status = parameters.get("status", "open")
                    details = self.farm_control_service.update_actuator_status(target_id, status)
                    result["success"] = "error" not in details
                    result["details"] = details
                    if "error" in details:
                        result["error"] = details["error"]
                
                elif action_type == "deactivate_actuator":
                    # Deactivate an actuator (close valve, stop pump, etc.)
                    details = self.farm_control_service.update_actuator_status(target_id, "close")
                    result["success"] = "error" not in details
                    result["details"] = details
                    if "error" in details:
                        result["error"] = details["error"]
                
                elif action_type == "check_sensor":
                    # Get sensor readings
                    details = self.farm_control_service.get_sensor_by_id(target_id)
                    result["success"] = details is not None
                    result["details"] = details or {"error": "Sensor not found"}
                    if not details:
                        result["error"] = "Sensor not found"
                
                elif action_type == "check_resource":
                    # Get resource levels
                    details = self.farm_control_service.get_resource_by_id(target_id)
                    result["success"] = details is not None
                    result["details"] = details or {"error": "Resource not found"}
                    if not details:
                        result["error"] = "Resource not found"
                
                elif action_type == "update_resource":
                    # Update resource level
                    new_level = parameters.get("value")
                    if new_level is not None:
                        details = self.farm_control_service.update_resource_level(target_id, new_level)
                        result["success"] = "error" not in details
                        result["details"] = details
                        if "error" in details:
                            result["error"] = details["error"]
                    else:
                        result["error"] = "No value provided for resource update"
                
                elif action_type == "get_field_info":
                    # Get field information
                    details = self.farm_control_service.get_field_by_id(target_id)
                    result["success"] = details is not None
                    result["details"] = details or {"error": "Field not found"}
                    if not details:
                        result["error"] = "Field not found"
                
                elif action_type == "get_actuator_info":
                    # Get actuator information
                    details = self.farm_control_service.get_actuator_by_id(target_id)
                    result["success"] = details is not None
                    result["details"] = details or {"error": "Actuator not found"}
                    if not details:
                        result["error"] = "Actuator not found"
                
                elif action_type == "get_all_active_actuators":
                    # Get all active actuators
                    details = self.farm_control_service.get_active_actuators()
                    result["success"] = True
                    result["details"] = {"active_actuators": details}
                
                elif action_type == "create_irrigation_schedule":
                    # Create an irrigation schedule
                    schedule_data = parameters.get("schedule", {})
                    details = self.farm_control_service.create_irrigation_schedule(target_id, schedule_data)
                    result["success"] = "error" not in details
                    result["details"] = details
                    if "error" in details:
                        result["error"] = details["error"]
                
                else:
                    result["error"] = f"Unknown action type: {action_type}"
            
            except Exception as e:
                result["error"] = str(e)
            
            results.append(result)
        
        # Update status cache after executing actions
        self.status_cache["last_update"] = None  # Force cache refresh on next fetch
        
        state.execution_results = results
        return state

    def _analyze_impacts(self, state: FarmChatState) -> FarmChatState:
        """Analyze the impacts of executed actions on the farm system."""
        # Initialize impact analysis
        impact_analysis = {
            "system_changes": [],
            "resource_impacts": [],
            "warnings": [],
            "recommendations": [],
            "success_rate": 0,
            "overall_success": True
        }

        # If no execution results, return empty impact analysis
        if not state.execution_results:
            state.impact_analysis = impact_analysis
            return state

        # Calculate success rate
        total_actions = len(state.execution_results)
        successful_actions = sum(1 for result in state.execution_results if result.get("success", False))
        
        if total_actions > 0:
            impact_analysis["success_rate"] = (successful_actions / total_actions) * 100
        
        # Overall success is true only if all actions succeeded
        impact_analysis["overall_success"] = successful_actions == total_actions

        # Analyze each execution result
        for result in state.execution_results:
            action = result.get("action", {})
            success = result.get("success", False)
            details = result.get("details", {})
            error = result.get("error", None)
            
            action_type = action.get("action_type", "")
            target_name = action.get("target_name", "unknown")

            if not success:
                impact_analysis["overall_success"] = False
                impact_analysis["warnings"].append(
                    f"Action '{action_type}' on {target_name} failed: {error}"
                )
                continue

            # Record system changes based on action type
            if action_type == "activate_actuator":
                impact_analysis["system_changes"].append(
                    f"{target_name} was activated"
                )
                
                # Check if this was a water valve or pump for irrigation
                if "valve" in target_name.lower() or "pump" in target_name.lower():
                    # Add recommendation for moisture monitoring
                    impact_analysis["recommendations"].append(
                        "Monitor soil moisture levels to ensure irrigation is effective"
                    )
                    
                    # Check water levels
                    water_resources = [res for res in state.context.get("resources", [])
                                     if "water" in res.get("content", "").lower()]
                    
                    if water_resources:
                        water_resource = water_resources[0]
                        capacity = water_resource.get("capacity", "0").replace(",", "")
                        current_level = water_resource.get("current_level", "0").replace(",", "")
                        
                        try:
                            capacity_value = float(capacity.split()[0])
                            current_value = float(current_level.split()[0])
                            
                            if current_value / capacity_value < 0.25:
                                impact_analysis["warnings"].append(
                                    f"Water levels are below 25% capacity ({current_level}/{capacity})"
                                )
                                impact_analysis["recommendations"].append(
                                    "Consider refilling water resources soon"
                                )
                        except (ValueError, IndexError):
                            pass
            
            elif action_type == "deactivate_actuator":
                impact_analysis["system_changes"].append(
                    f"{target_name} was deactivated"
                )
                
            elif action_type == "update_resource":
                impact_analysis["resource_impacts"].append(
                    f"{target_name} level updated to {details.get('current_level', 'unknown')}"
                )
                
            elif action_type == "check_sensor":
                # For sensor readings, we need to extract and format the value
                sensor_value = "unknown"
                if "value" in details:
                    sensor_value = details["value"]
                elif "status" in details:
                    sensor_value = details["status"]
                    
                impact_analysis["system_changes"].append(
                    f"{target_name} reading: {sensor_value}"
                )
                
                # Add recommendations based on sensor type
                if "moisture" in target_name.lower():
                    impact_analysis["recommendations"].append(
                        "Use soil moisture readings to optimize irrigation scheduling"
                    )
                elif "temperature" in target_name.lower():
                    impact_analysis["recommendations"].append(
                        "Monitor temperature trends to adjust irrigation timing"
                    )

        # Generalize recommendations if we have several similar ones
        if len(impact_analysis["recommendations"]) > 3:
            unique_recommendations = set(impact_analysis["recommendations"])
            if len(unique_recommendations) < len(impact_analysis["recommendations"]):
                impact_analysis["recommendations"] = list(unique_recommendations)

        state.impact_analysis = impact_analysis
        return state
    
    def _format_response(self, state: FarmChatState) -> FarmChatState:
        """Format a natural language response based on the execution results and impact analysis."""
        # If a response is already set (e.g. from clarification or confirmation), return it
        if state.response:
            return state
            
        # For information requests without executed actions
        if not state.execution_results and state.scenario == "information":
            return self._format_information_response(state)
            
        execution_results = state.execution_results or []
        impact_analysis = state.impact_analysis or {}
        
        # Check success rate
        overall_success = impact_analysis.get("overall_success", False)
        success_rate = impact_analysis.get("success_rate", 0)
        
        # Build a user-friendly response
        response_parts = []
        
        # Start with acknowledgment of the request
        if state.intent and state.intent.get("action"):
            action = state.intent.get("action")
            
            if action.startswith("get_") or "query" in state.intent.get("intent_type", ""):
                response_parts.append("Here's the information you requested:")
            else:
                response_parts.append("I've processed your request for the farm system.")
        else:
            response_parts.append("I've analyzed your request for the farm system.")
            
        # Add summary of what was done
        if overall_success:
            if state.scenario == "irrigation" and "start" in state.intent.get("action", ""):
                # Successful irrigation start
                field_names = []
                for result in execution_results:
                    if result.get("success", False) and "valve" in result.get("action", {}).get("target_name", "").lower():
                        # Extract field name from action reason
                        reason = result.get("action", {}).get("reason", "")
                        field_match = re.search(r'irrigate\s+(.+?)', reason)
                        if field_match:
                            field_name = field_match.group(1)
                            if field_name not in field_names:
                                field_names.append(field_name)
                                if field_name not in self.recent_mentions["fields"]:
                                    self.recent_mentions["fields"].append(field_name)
                
                if field_names:
                    if len(field_names) == 1:
                        response_parts.append(f"✓ Successfully started irrigation in {field_names[0]}.")
                    else:
                        response_parts.append(f"✓ Successfully started irrigation in multiple fields: {', '.join(field_names)}.")
                else:
                    response_parts.append("✓ Successfully started irrigation as requested.")
                    
            elif state.scenario == "irrigation" and "stop" in state.intent.get("action", ""):
                # Successful irrigation stop
                field_names = []
                for result in execution_results:
                    if result.get("success", False) and "valve" in result.get("action", {}).get("target_name", "").lower():
                        # Extract field name from action reason
                        reason = result.get("action", {}).get("reason", "")
                        field_match = re.search(r'irrigation\s+in\s+(.+?), reason')
                        if field_match:
                            field_name = field_match.group(1)
                            if field_name not in field_names:
                                field_names.append(field_name)
                
                if field_names:
                    if len(field_names) == 1:
                        response_parts.append(f"✓ Successfully stopped irrigation in {field_names[0]}.")
                    else:
                        response_parts.append(f"✓ Successfully stopped irrigation in multiple fields: {', '.join(field_names)}.")
                else:
                    response_parts.append("✓ Successfully stopped irrigation as requested.")
                    
            elif state.scenario == "monitoring":
                # For monitoring scenario, summarize the readings
                if state.intent.get("action") == "get_moisture_readings":
                    # Summarize moisture readings
                    moisture_readings = []
                    for result in execution_results:
                        if result.get("success", False) and result.get("action", {}).get("action_type") == "check_sensor":
                            target_name = result.get("action", {}).get("target_name", "")
                            if "moisture" in target_name.lower():
                                field_match = re.search(r'in\s+(.+?), target_name', reason)
                                if field_match:
                                    field_name = field_match.group(1)
                                    moisture_readings.append({
                                        "field": field_name,
                                        "value": result.get("details", {}).get("value", "Unknown"),
                                        "unit": result.get("details", {}).get("unit", "%")
                                    })
                    
                    if moisture_readings:
                        response_parts.append("Here are the current soil moisture readings:")
                        for reading in moisture_readings:
                            response_parts.append(f"• {reading['field']}: {reading['value']}{reading['unit']}")
                    else:
                        response_parts.append("I wasn't able to find any moisture readings for the requested fields.")
                        
                elif state.intent.get("action") == "get_temperature_readings":
                    # Summarize temperature readings
                    temp_readings = []
                    for result in execution_results:
                        if result.get("success", False) and result.get("action", {}).get("action_type") == "check_sensor":
                            target_name = result.get("action", {}).get("target_name", "")
                            if "temperature" in target_name.lower():
                                field_match = re.search(r'in\s+(.+?), target_name', reason)
                                if field_match:
                                    field_name = field_match.group(1)
                                    temp_readings.append({
                                        "field": field_name,
                                        "value": result.get("details", {}).get("value", "Unknown"),
                                        "unit": result.get("details", {}).get("unit", "°C")
                                    })
                    
                    if temp_readings:
                        response_parts.append("Here are the current temperature readings:")
                        for reading in temp_readings:
                            response_parts.append(f"• {reading['field']}: {reading['value']}{reading['unit']}")
                    else:
                        response_parts.append("I wasn't able to find any temperature readings for the requested fields.")
                        
            else:
                # General success message
                response_parts.append(f"✓ All requested actions completed successfully.")
        else:
            # Partial or no success
            if success_rate > 0:
                response_parts.append(f"Partially completed your request ({success_rate:.0f}% success rate).")
            else:
                response_parts.append("I wasn't able to complete the requested actions.")
                
        # Add notable system changes
        system_changes = impact_analysis.get("system_changes", [])
        if len(system_changes) == 1:
            response_parts.append(f"System change: {system_changes[0]}.")
        elif len(system_changes) > 1:
            if len(system_changes) <= 3:
                response_parts.append("System changes:")
                for change in system_changes:
                    response_parts.append(f"• {change}")
            else:
                # Summarize many changes
                response_parts.append(f"Made {len(system_changes)} system changes including:")
                for change in system_changes[:2]:
                    response_parts.append(f"• {change}")
                response_parts.append(f"• And {len(system_changes) - 2} more changes")
                
        # Add resource impacts if any
        resource_impacts = impact_analysis.get("resource_impacts", [])
        if resource_impacts:
            response_parts.append("Resource changes:")
            for impact in resource_impacts[:3]:  # Show at most 3
                response_parts.append(f"• {impact}")
                
        # Add warnings if any
        warnings = impact_analysis.get("warnings", [])
        if warnings:
            response_parts.append("Important notes:")
            for warning in warnings[:2]:  # Show at most 2 warnings
                response_parts.append(f"⚠️ {warning}")
                
        # Add recommendations if any
        recommendations = impact_analysis.get("recommendations", [])
        if recommendations:
            response_parts.append("Recommendations:")
            for recommendation in recommendations[:2]:  # Show at most 2 recommendations
                response_parts.append(f"• {recommendation}")
                
        # Handle errors for failed requests
        if not overall_success:
            errors = []
            for result in execution_results:
                if not result.get("success", False) and result.get("error"):
                    action = result.get("action", {})
                    target_name = action.get("target_name", "Unknown")
                    error = result.get("error")
                    errors.append(f"{target_name}: {error}")
            
            if errors:
                response_parts.append("Issues encountered:")
                for error in errors[:3]:  # Show at most 3 errors
                    response_parts.append(f"• {error}")
                    
                if len(errors) > 3:
                    response_parts.append(f"• And {len(errors) - 3} more issues")
                    
                # Add helpful suggestion
                response_parts.append("\nPlease check your equipment or try again with more specific information.")
        
        # Join all parts with appropriate spacing
        response = "\n\n".join(response_parts)
        
        state.response = response
        return state
    
    def _format_information_response(self, state: FarmChatState) -> FarmChatState:
        """Format a response for information requests without actions."""
        response_parts = []
        
        # Handle different information request types
        intent_action = state.intent.get("action", "") if state.intent else ""
        
        if "irrigation_status" in intent_action:
            # Irrigation status information
            fields = state.context.get("fields", [])
            
            if fields:
                # Check irrigation status for each field
                irrigating_fields = []
                non_irrigating_fields = []
                
                for field in fields:
                    field_id = field.get("id")
                    field_name = field.get("name", "Unknown field")
                    
                    # Check if the field is being irrigated
                    field_status = self.status_cache.get("field_status", {}).get(field_id, {})
                    if field_status.get("is_irrigating", False):
                        irrigating_fields.append(field_name)
                    else:
                        non_irrigating_fields.append(field_name)
                
                response_parts.append("Here's the current irrigation status:")
                
                if irrigating_fields:
                    response_parts.append("Currently irrigating:")
                    for field in irrigating_fields:
                        response_parts.append(f"• {field}")
                        
                if len(fields) == 1:
                    # Single field query
                    field_name = fields[0].get("name", "Unknown field")
                    if field_name in irrigating_fields:
                        response_parts = [f"{field_name} is currently being irrigated."]
                        
                        # Add details about active equipment
                        field_id = fields[0].get("id")
                        field_status = self.status_cache.get("field_status", {}).get(field_id, {})
                        field_actuators = field_status.get("actuators", [])
                        
                        active_valves = [a for a in field_actuators if a.get("status") == "open" and a.get("type") == "water_valves"]
                        active_pumps = [a for a in field_actuators if a.get("status") == "open" and a.get("type") == "pump"]
                        
                        if active_valves or active_pumps:
                            response_parts.append("\nActive irrigation equipment:")
                            if active_valves:
                                response_parts.append(f"• {len(active_valves)} water valve(s)")
                            if active_pumps:
                                response_parts.append(f"• {len(active_pumps)} pump(s)")
                    else:
                        response_parts = [f"{field_name} is not currently being irrigated."]
                else:
                    # Multiple fields summary
                    if not irrigating_fields:
                        response_parts.append("No fields are currently being irrigated.")
            else:
                response_parts.append("I couldn't find information about the requested fields.")
                
        elif "resource_levels" in intent_action or "get_resource" in intent_action:
            # Resource level information
            resources = state.context.get("resources", [])
            
            if resources:
                response_parts.append("Current resource levels:")
                
                for resource in resources:
                    name = resource.get("name", "Unknown")
                    content = resource.get("content", "")
                    current = resource.get("current_level", "Unknown")
                    capacity = resource.get("capacity", "")
                    
                    resource_info = f"• {name}"
                    if content:
                        resource_info += f" ({content})"
                    resource_info += f": {current}"
                    if capacity:
                        resource_info += f" / {capacity}"
                        
                        # Calculate percentage if possible
                        try:
                            current_val = float(current.split()[0].replace(",", ""))
                            capacity_val = float(capacity.split()[0].replace(",", ""))
                            if capacity_val > 0:
                                percentage = (current_val / capacity_val) * 100
                                resource_info += f" ({percentage:.0f}%)"
                        except (ValueError, IndexError):
                            pass
                            
                    response_parts.append(resource_info)
            else:
                response_parts.append("I couldn't find information about the requested resources.")
                
        elif "active_actuators" in intent_action or "get_all_active" in intent_action:
            # Active equipment information
            active_actuators = self.status_cache.get("active_actuators", [])
            
            if active_actuators:
                # Group by type
                actuators_by_type = {}
                for actuator in active_actuators:
                    actuator_type = actuator.get("type", "Unknown")
                    if actuator_type not in actuators_by_type:
                        actuators_by_type[actuator_type] = []
                    actuators_by_type[actuator_type].append(actuator)
                
                response_parts.append(f"There are {len(active_actuators)} active pieces of equipment:")
                
                for actuator_type, actuators in actuators_by_type.items():
                    # Format type for display
                    display_type = actuator_type.replace("_", " ").title()
                    response_parts.append(f"• {display_type}: {len(actuators)}")
                    
                    # List a few examples if there are many
                    if len(actuators) <= 3:
                        for actuator in actuators:
                            name = actuator.get("name") or f"ID: {actuator.get('id')}"
                            response_parts.append(f"  - {name}")
                    else:
                        # Just list the first two as examples
                        for actuator in actuators[:2]:
                            name = actuator.get("name") or f"ID: {actuator.get('id')}"
                            response_parts.append(f"  - {name}")
                        response_parts.append(f"  - And {len(actuators) - 2} more {display_type.lower()}")
            else:
                response_parts.append("There are no active pieces of equipment right now.")
                
        elif "field_info" in intent_action or "get_field" in intent_action:
            # Field information
            fields = state.context.get("fields", [])
            
            if fields:
                if len(fields) == 1:
                    # Single field detail view
                    field = fields[0]
                    field_name = field.get("name", "Unknown field")
                    field_crop = field.get("crop", "Unknown crop")
                    field_area = field.get("area", "Unknown size")
                    
                    response_parts.append(f"Information about {field_name}:")
                    response_parts.append(f"• Crop: {field_crop}")
                    response_parts.append(f"• Size: {field_area}")
                    
                    # Get sensor information
                    sensors = [s for s in state.context.get("sensors", []) if s.get("field_id") == field.get("id")]
                    if sensors:
                        sensor_types = list(set(s.get("type", "unknown") for s in sensors))
                        response_parts.append(f"• Sensors: {len(sensors)} sensors including {', '.join(sensor_types[:3])}")
                    
                    # Get actuator information
                    actuators = [a for a in state.context.get("actuators", []) if a.get("field_id") == field.get("id")]
                    if actuators:
                        actuator_types = list(set(a.get("type", "unknown") for a in actuators))
                        response_parts.append(f"• Equipment: {len(actuators)} devices including {', '.join(actuator_types[:3])}")
                    
                    # Irrigation status
                    field_id = field.get("id")
                    field_status = self.status_cache.get("field_status", {}).get(field_id, {})
                    if field_status.get("is_irrigating", False):
                        response_parts.append(f"• Status: Currently being irrigated")
                    else:
                        response_parts.append(f"• Status: Not currently irrigated")
                else:
                    # Multiple fields summary
                    response_parts.append(f"Found {len(fields)} fields:")
                    
                    for field in fields:
                        field_name = field.get("name", "Unknown field")
                        field_crop = field.get("crop", "Unknown crop")
                        field_area = field.get("area", "Unknown size")
                        
                        # Check irrigation status
                        field_id = field.get("id")
                        field_status = self.status_cache.get("field_status", {}).get(field_id, {})
                        status_indicator = "🌧️" if field_status.get("is_irrigating", False) else "☀️"
                        
                        response_parts.append(f"• {status_indicator} {field_name}: {field_crop}, {field_area}")
            else:
                response_parts.append("I couldn't find information about the requested fields.")
        else:
            # Generic information response
            response_parts.append("Here's the information from your farm system:")
            
            # Include whatever context we have
            if state.context.get("fields"):
                response_parts.append(f"Fields: {len(state.context.get('fields'))} fields found")
                
            if state.context.get("actuators"):
                active_count = sum(1 for a in state.context.get("actuators", []) if a.get("status") == "open")
                response_parts.append(f"Equipment: {active_count} active out of {len(state.context.get('actuators'))} total")
                
            if state.context.get("resources"):
                response_parts.append(f"Resources: {len(state.context.get('resources'))} resources available")
                
            if state.context.get("sensors"):
                response_parts.append(f"Sensors: {len(state.context.get('sensors'))} monitoring devices")
        
        # Join all parts with appropriate spacing
        response = "\n\n".join(response_parts)
        
        state.response = response
        return state
    
    def chat(self, message: str) -> Dict:
        """Process a message from the user and return a response."""
        # Check if this is a confirmation response
        confirmation_pattern = r'^(yes|confirm|proceed|go ahead|ok|sure|do it|approved)[\s\.\!\?]*'
        rejection_pattern = r'^(no|cancel|abort|stop|don\'t|negative|reject)[\s\.\!\?]*'
        
        if re.match(confirmation_pattern, message.strip().lower()):
            # User is confirming a previous action, check if we have pending confirmations
            if self.conversation_memory and self.conversation_memory[-1].get("needs_confirmation", False):
                # Execute the pending plan
                pending_plan = self.conversation_memory[-1].get("pending_plan", [])
                if pending_plan:
                    for action in pending_plan:
                        if "field_name" in action.get("parameters", {}):
                            field_name = action["parameters"]["field_name"]
                        if field_name not in self.recent_mentions["fields"]:
                            self.recent_mentions["fields"].insert(0, field_name)
                    if action.get("target_id") and action.get("action_type") == "activate_actuator":
                        actuator_id = action["target_id"]
                        if actuator_id not in self.recent_mentions["actuators"]:
                            self.recent_mentions["actuators"].insert(0, actuator_id)
                
                
                    # Create a new state with the pending plan
                    initial_state = FarmChatState(
                        messages=[{"role": "human", "content": message}],
                        user_request="Confirm execution",
                        plan=pending_plan,
                        confirmation_needed=False
                    )
                    
                    # Run execution directly
                    state = self._execute_actions(initial_state)
                    state = self._analyze_impacts(state)
                    state = self._format_response(state)
                    
                    # Save the exchange to conversation memory
                    self.conversation_memory.append({
                        "user": message,
                        "assistant": state.response or "No response generated.",
                        "needs_confirmation": False
                    })
                    
                    # Trim conversation memory if too long
                    if len(self.conversation_memory) > self.max_memory_items:
                        self.conversation_memory = self.conversation_memory[-self.max_memory_items:]
                    
                    # Return the response and other useful information
                    return {
                        "response": state.response or "No response generated.",
                        "plan": pending_plan,
                        "execution_results": state.execution_results,
                        "impact_analysis": state.impact_analysis
                    }
                    
            # If we get here, either there was no pending confirmation or no pending plan
            return {
                "response": "I don't have any pending actions to confirm. What would you like me to do with your farm system?",
                "intent": None,
                "plan": None
            }
            
        elif re.match(rejection_pattern, message.strip().lower()):
            # User is rejecting a previous action
            if self.conversation_memory and self.conversation_memory[-1].get("needs_confirmation", False):
                # Clear the pending plan
                self.conversation_memory[-1]["needs_confirmation"] = False
                self.conversation_memory[-1]["pending_plan"] = []
                
                # Add rejection to conversation memory
                self.conversation_memory.append({
                    "user": message,
                    "assistant": "Action cancelled. Is there something else you'd like to do with your farm system?",
                    "needs_confirmation": False
                })
                
                # Trim conversation memory if too long
                if len(self.conversation_memory) > self.max_memory_items:
                    self.conversation_memory = self.conversation_memory[-self.max_memory_items:]
                
                return {
                    "response": "Action cancelled. Is there something else you'd like to do with your farm system?",
                    "intent": None,
                    "plan": None
                }
                
            # If we get here, there was no pending confirmation
            return {
                "response": "I don't have any pending actions to cancel. What would you like me to do with your farm system?",
                "intent": None,
                "plan": None
            }
            
        # Normal request processing
        # Initialize state with the user's message
        initial_state = FarmChatState(
            messages=[{"role": "human", "content": message}],
            user_request=message
        )
        
        # Run the graph
        final_state = FarmChatState(**self.graph.invoke(initial_state))
        
        # Check if confirmation is needed
        if final_state.confirmation_needed:
            # Save plan for later execution after confirmation
            self.conversation_memory.append({
                "user": message,
                "assistant": final_state.response or "No response generated.",
                "needs_confirmation": True,
                "pending_plan": final_state.plan
            })
        else:
            # Save the exchange to conversation memory
            self.conversation_memory.append({
                "user": message,
                "assistant": final_state.response or "No response generated.",
                "needs_confirmation": False
            })
            
        # Trim conversation memory if too long
        if len(self.conversation_memory) > self.max_memory_items:
            self.conversation_memory = self.conversation_memory[-self.max_memory_items:]
        
        # Return the response and other useful information
        return {
            "response": final_state.response or "No response generated.",
            "intent": final_state.intent,
            "scenario": final_state.scenario,
            "plan": final_state.plan,
            "execution_results": final_state.execution_results,
            "impact_analysis": final_state.impact_analysis
        }
    
    
    def get_conversation_history(self):
        """Return the conversation history."""
        return [
            {"user": exchange["user"], "assistant": exchange["assistant"]}
            for exchange in self.conversation_memory
        ]
        
    def _get_closed_actuators(self):
        """Get all actuators with 'close' status."""
        closed_actuators = []
        for actuator in self.system_info.get("actuators", []):
            if actuator.get("status") == "close":
                closed_actuators.append(actuator)
        return closed_actuators
    
    def get_system_overview(self):
        """Get a comprehensive overview of the farm system."""
        self._update_status_cache()
        
        overview = {
            "farm_info": {
                "total_farms": len(self.system_info.get("farms", [])),
                "total_fields": len(self.system_info.get("fields", [])),
                "total_equipment": len(self.system_info.get("actuators", [])),
                "total_sensors": len(self.system_info.get("sensors", []))
            },
            "active_equipment": {
                "count": len(self.status_cache.get("active_actuators", [])),
                "by_type": {}
            },
            "field_status": {},
            "resource_levels": {}
        }
        
        # Group active equipment by type
        for actuator in self.status_cache.get("active_actuators", []):
            actuator_type = actuator.get("type", "Unknown")
            if actuator_type not in overview["active_equipment"]["by_type"]:
                overview["active_equipment"]["by_type"][actuator_type] = []
            overview["active_equipment"]["by_type"][actuator_type].append(actuator.get("id"))
        
        # Summarize field status
        for field in self.system_info.get("fields", []):
            field_id = field.get("id")
            if field_id:
                field_status = self.status_cache.get("field_status", {}).get(field_id, {})
                overview["field_status"][field.get("name", "Unknown")] = {
                    "is_irrigating": field_status.get("is_irrigating", False),
                    "crop": field.get("crop", "Unknown"),
                    "area": field.get("area", "Unknown")
                }
        
        # Summarize resource levels
        for resource in self.system_info.get("resources", []):
            overview["resource_levels"][resource.get("name", "Unknown")] = {
                "current_level": resource.get("current_level", "Unknown"),
                "capacity": resource.get("capacity", "Unknown"),
                "content": resource.get("content", "Unknown")
            }
        
        return overview


def create_farm_chat_interface(farm_control_service, model_name="gpt-4o"):
    """Create an enhanced farm chat interface instance."""
    return EnhancedFarmChatInterface(farm_control_service, model_name=model_name)


# Example usage in a web application or API
if __name__ == "__main__":
    # Initialize the farm control service
    session_factory = get_session_factory()
    farm_service = FarmControlService(session_factory)
    
    # Create the chat interface
    farm_chat = create_farm_chat_interface(farm_service)
    
    # Example interaction
    while True:
        user_input = input("\nFarmer: ")
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("Farm Assistant: Goodbye! Have a great day on the farm.")
            break
            
        response = farm_chat.chat(user_input)
        print(f"\nFarm Assistant: {response['response']}")