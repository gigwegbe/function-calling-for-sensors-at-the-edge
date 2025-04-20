from typing import Dict, List, Optional, Any
import os
import json
import asyncio
import logging
import re
from dotenv import load_dotenv
from smolagents import ToolCollection
from mcp import StdioServerParameters
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
import chainlit as cl


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('chainlit_farm.log')
    ]
)
logger = logging.getLogger('chainlit_farm')

# Load environment variables
load_dotenv()

# Initialize dictionary to track active operations for UI display
active_operations = {}
resource_levels = {}

class SmartFarmAgent:
    """An agent that handles tool calling with minimal confirmation steps"""
    
    def __init__(self, tools, model):
        # Store tools as a dictionary mapped by name for easy access
        self.tools = {}
        for tool in tools:
            self.tools[tool.name] = tool
        
        self.model = model
        self.tool_descriptions = self._generate_tool_descriptions()
        print("Tool descriptions generated:")
        print(self.tool_descriptions)
        self.conversation_history = []
        
    def _generate_tool_descriptions(self):
        descriptions = []
        for name, tool in self.tools.items():
            descriptions.append(f"- {name}: {tool.description}")
        return "\n".join(descriptions)
    
    def _get_system_message(self):
        return f"""You are a direct and efficient farm management assistant with access to the following tools:

        {self.tool_descriptions}

        Important instructions:
        1. Execute user requests immediately without asking for confirmation
        2. Use your best judgment to determine the right parameters
        3. Be concise in your responses - focus on what was done rather than asking questions
        4. When dealing with farm control operations, just do them without checking first
        5. Always show the specific actuator ID in your responses (like "The fertilizer dispenser FD-0900 has been opened")
        
        When a user refers to a field:
        1. Use find_field_by_name to look up the field directly
        2. For partial matches, try different variations (e.g., "north" → "North Field", "central" → "Central Field")
        3. If the user mentions an actuator, use the get_actuator_by_id tool to identify which field it belongs to
        4. If the user mentions a crop, look for fields growing that crop
        
        When using tools:
        1. For simple tools with one parameter (like get_farm_details, get_sensor_data), use just the ID as a string: "1"
        2. For tools with no parameters (list_all_farms, get_resource_levels, get_active_actuators), use an empty string
        3. For tools with multiple parameters:
        - control_actuator: Format as JSON with actuator_id and status: {{"actuator_id": "1", "status": "open"}}
        - update_resource_level: Format as JSON with resource_id and new_level: {{"resource_id": "1", "new_level": 75.5}}
        - create_irrigation_schedule: Format as JSON: {{"field_id": "1", "schedule_data": {{"start_time": "06:00", "duration": 30}}}}

        To use a tool, respond with:
        ```tool
        {{
        "tool_name": "name_of_tool",
        "tool_input": "parameter_value" or {{JSON formatted parameters}}
        }}"""
    
    async def run(self, user_input, message_handler=None):
        """
        Run the agent with a user input.
        
        Args:
            user_input: User message
            message_handler: Optional async callback function to handle intermediate messages
            
        Returns:
            Final agent response
        """
        # Add user input to conversation history
        self.conversation_history.append({"role": "user", "content": user_input})
        
        # Prepare the messages for the model
        messages = [
            HumanMessage(content=f"System: {self._get_system_message()}")
        ]
        
        # Add conversation history
        for message in self.conversation_history:
            if message["role"] == "user":
                messages.append(HumanMessage(content=message["content"]))
            else:
                messages.append(AIMessage(content=message["content"]))
        
        # Get response from model
        response = await asyncio.to_thread(self.model.invoke, messages)
        response_content = response.content
        
        # Check if there's a tool call in the response
        tool_call = self._extract_tool_call(response_content)
        
        if tool_call:
            tool_name = tool_call.get("tool_name")
            tool_input = tool_call.get("tool_input", "")
            
            if message_handler:
                await message_handler(f"Using tool: {tool_name}", "tool")
            
            if tool_name in self.tools:
                # Execute the tool
                try:
                    # Handle different tool input types
                    tool_result = await asyncio.to_thread(self._execute_tool, tool_name, tool_input)
                    
                    # Update our global tracking for the UI
                    self._update_tracking(tool_name, tool_input, tool_result)
                    
                    # For controls, always get active actuators to keep our UI in sync
                    if tool_name == "control_actuator":
                        try:
                            if "get_active_actuators" in self.tools:
                                active_results = await asyncio.to_thread(self.tools["get_active_actuators"])
                                self._update_tracking("get_active_actuators", "", active_results)
                            
                            # Also fetch resource levels to keep that updated
                            if "get_resource_levels" in self.tools:
                                resource_results = await asyncio.to_thread(self.tools["get_resource_levels"])
                                self._update_tracking("get_resource_levels", "", resource_results)
                        except Exception as e:
                            logger.error(f"Error fetching updates after control: {str(e)}")
                    
                    if message_handler:
                        await message_handler(f"Tool result: {tool_result}", "result")
                    
                    # Add the tool call and result to the conversation
                    tool_response = f"I've completed the operation using the {tool_name} tool.\n\nResult: {tool_result}"
                    self.conversation_history.append({"role": "assistant", "content": tool_response})
                    
                    # Get final response
                    messages.append(AIMessage(content=response_content))
                    messages.append(HumanMessage(content=f"Tool result: {tool_result}"))
                    final_response = await asyncio.to_thread(self.model.invoke, messages)
                    
                    # Add the final response to conversation history
                    self.conversation_history.append({"role": "assistant", "content": final_response.content})
                    return final_response.content
                except Exception as e:
                    error_msg = f"Error using tool '{tool_name}': {str(e)}"
                    logger.error(f"Debug - {error_msg}", exc_info=True)
                    self.conversation_history.append({"role": "assistant", "content": error_msg})
                    return error_msg
            else:
                error_msg = f"Tool '{tool_name}' not found. Available tools are: {', '.join(self.tools.keys())}"
                self.conversation_history.append({"role": "assistant", "content": error_msg})
                return error_msg
        
        # If no tool call was made, add response to history and return
        self.conversation_history.append({"role": "assistant", "content": response_content})
        return response_content
    
    def _execute_tool(self, tool_name, tool_input):
        """Execute a tool with proper input handling"""
        tool = self.tools[tool_name]
        
        # Tools that we know take no parameters
        if tool_name in ["list_all_farms", "get_resource_levels", "get_active_actuators"]:
            return tool()
        
        # Special case for find_field_by_name which needs to handle spaces in field names
        if tool_name == "find_field_by_name":
            # Make sure we're passing a single string argument
            # Strip any quotes that might be in the input
            clean_input = str(tool_input).strip('"\'')
            return tool(clean_input)
        
        # For tools that expect two parameters
        if tool_name == "control_actuator":
            try:
                # First try to handle it as JSON
                if isinstance(tool_input, str) and tool_input.strip().startswith("{"):
                    params = json.loads(tool_input)
                    return tool(params["actuator_id"], params["status"])
                # If not JSON, see if it's a string with comma separation
                elif isinstance(tool_input, str) and ',' in tool_input:
                    actuator_id, status = [x.strip() for x in tool_input.split(',', 1)]
                    return tool(actuator_id, status)
                else:
                    # Default case - probably won't work but let's try
                    return tool(tool_input)
            except Exception as e:
                return f"Error parsing control_actuator parameters: {str(e)}"
        
        # For tools that expect JSON input
        if tool_name in ["update_resource_level", "create_irrigation_schedule"]:
            try:
                if isinstance(tool_input, str) and tool_input.strip().startswith("{"):
                    params = json.loads(tool_input)
                    
                    if tool_name == "update_resource_level":
                        return tool(params["resource_id"], params["new_level"])
                    elif tool_name == "create_irrigation_schedule":
                        return tool(params["field_id"], json.dumps(params["schedule_data"]))
                else:
                    return tool(tool_input)
            except Exception as e:
                return f"Error parsing parameters for {tool_name}: {str(e)}"
        
        # For all other tools, just pass the input directly
        return tool(tool_input)
    
    def _extract_tool_call(self, text):
        """Extract tool call from model output"""
        if "```tool" in text and "```" in text.split("```tool", 1)[1]:
            tool_json_str = text.split("```tool", 1)[1].split("```", 1)[0].strip()
            try:
                return json.loads(tool_json_str)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool JSON: {tool_json_str}")
                logger.error(f"Error: {str(e)}")
                # Try to extract tool name and input using regex as fallback
                import re
                tool_match = re.search(r'"tool_name":\s*"([^"]+)"', tool_json_str)
                input_match = re.search(r'"tool_input":\s*"([^"]*)"', tool_json_str)
                if tool_match:
                    tool_name = tool_match.group(1)
                    tool_input = input_match.group(1) if input_match else ""
                    return {"tool_name": tool_name, "tool_input": tool_input}
                return None
        return None
        
    def _update_tracking(self, tool_name, tool_input, tool_result):
        """Update global tracking for UI display"""
        global active_operations, resource_levels
        logger.info(f"Updating tracking for {tool_name}")
        
        # Handle control_actuator to track active operations
        if tool_name == "control_actuator":
            try:
                # Extract the actuator ID and status from the input
                actuator_id = None
                status = None
                
                if isinstance(tool_input, str) and tool_input.strip().startswith("{"):
                    try:
                        params = json.loads(tool_input)
                        actuator_id = params.get("actuator_id")
                        status = params.get("status")
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse JSON in control_actuator input: {tool_input}")
                elif isinstance(tool_input, str) and ',' in tool_input:
                    parts = tool_input.split(',', 1)
                    actuator_id = parts[0].strip() if parts else None
                    status = parts[1].strip() if len(parts) > 1 else None
                
                # Now try to parse the result to confirm changes
                result_status = None
                result_id = None
                
                # Debug log the tool result
                logger.info(f"Control actuator result: {tool_result}")
                
                try:
                    # Try to convert string result to dict if needed
                    if isinstance(tool_result, str):
                        # Try to extract any JSON or structured data
                        json_match = re.search(r'{.*}', tool_result, re.DOTALL)
                        if json_match:
                            # Clean the string to make it valid JSON
                            clean_result = json_match.group(0).replace("'", '"')
                            clean_result = clean_result.replace("None", "null")
                            clean_result = clean_result.replace("True", "true")
                            clean_result = clean_result.replace("False", "false")
                            
                            try:
                                parsed_result = json.loads(clean_result)
                                
                                # Extract status and ID from the parsed result
                                if isinstance(parsed_result, dict):
                                    result_status = parsed_result.get("status")
                                    result_id = parsed_result.get("id")
                                    
                                    # Look deeper in status_change if present
                                    status_change = parsed_result.get("status_change")
                                    if status_change and isinstance(status_change, dict):
                                        result_status = status_change.get("to") or result_status
                            except json.JSONDecodeError:
                                logger.error(f"Failed to parse extracted JSON: {clean_result}")
                                
                        # If we couldn't parse JSON, try to extract status through regex
                        if not result_status or not result_id:
                            # Look for typical status patterns in the response
                            id_match = re.search(r'actuator_id["\']:\s*["\']([^"\']+)["\']', tool_result)
                            status_match = re.search(r'status["\']:\s*["\']([^"\']+)["\']', tool_result)
                            
                            if id_match:
                                result_id = id_match.group(1)
                            if status_match:
                                result_status = status_match.group(1)
                            
                    elif isinstance(tool_result, dict):
                        result_status = tool_result.get("status")
                        result_id = tool_result.get("id")
                        
                        # Look deeper in status_change if present
                        status_change = tool_result.get("status_change")
                        if status_change and isinstance(status_change, dict):
                            result_status = status_change.get("to") or result_status
                except Exception as e:
                    logger.error(f"Error parsing control_actuator result: {str(e)}")
                
                # Use result values if available, otherwise fall back to input values
                final_id = result_id or actuator_id
                final_status = result_status or status
                
                # Look for specific actuator IDs and status values in the result string
                if not final_id or not final_status:
                    # Try to extract from the string directly
                    # Look for common patterns like FD-0900 and open/close
                    id_pattern = r'([A-Z]+-\d+)'
                    status_pattern = r'\b(open|close|closed)\b'
                    
                    # Find all actuator IDs and status values in the result
                    if isinstance(tool_result, str):
                        id_matches = re.findall(id_pattern, tool_result)
                        status_matches = re.findall(status_pattern, tool_result, re.IGNORECASE)
                        
                        if id_matches and not final_id:
                            final_id = id_matches[0]  # Use the first match
                            
                        if status_matches and not final_status:
                            status_val = status_matches[0].lower()
                            # Map "closed" to "close" for consistency
                            final_status = "close" if status_val == "closed" else status_val
                
                if final_id and final_status:
                    logger.info(f"Setting actuator {final_id} status to {final_status}")
                    
                    if final_status.lower() == "open":
                        # Add or update the entry
                        active_operations[final_id] = {
                            "type": "actuator",
                            "status": "active",
                            "name": f"Actuator {final_id}"
                        }
                    elif final_status.lower() in ["close", "closed"]:
                        # Remove from active operations if present
                        if final_id in active_operations:
                            logger.info(f"Removing {final_id} from active operations")
                            del active_operations[final_id]
                            
                    # Log the current active operations
                    logger.info(f"Active operations after update: {active_operations}")
            except Exception as e:
                logger.error(f"Error in control_actuator tracking: {str(e)}", exc_info=True)
        
        # Handle get_active_actuators - completely replace our tracking
        elif tool_name == "get_active_actuators":
            try:
                # Reset the active operations dict
                active_operations.clear()
                
                # Parse the result
                if isinstance(tool_result, str):
                    # Try parsing as JSON first
                    clean_result = tool_result.replace("'", '"')
                    clean_result = clean_result.replace("None", "null")
                    clean_result = clean_result.replace("True", "true")
                    clean_result = clean_result.replace("False", "false")
                    
                    # Check if it looks like a JSON array
                    if clean_result.strip().startswith("[") and clean_result.strip().endswith("]"):
                        try:
                            actuator_list = json.loads(clean_result)
                            for actuator in actuator_list:
                                if isinstance(actuator, dict):
                                    actuator_id = actuator.get("id")
                                    if actuator_id:
                                        active_operations[actuator_id] = {
                                            "type": "actuator",
                                            "status": "active",
                                            "name": actuator.get("name", f"Actuator {actuator_id}")
                                        }
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse active actuators JSON: {clean_result}")
                            # Try regex parsing as fallback
                            id_matches = re.findall(r'["\']id["\']:\s*["\']([^"\']+)["\']', tool_result)
                            for actuator_id in id_matches:
                                active_operations[actuator_id] = {
                                    "type": "actuator",
                                    "status": "active",
                                    "name": f"Actuator {actuator_id}"
                                }
                
                logger.info(f"Updated active operations from get_active_actuators: {active_operations}")
            except Exception as e:
                logger.error(f"Error in get_active_actuators tracking: {str(e)}", exc_info=True)
        
        # Handle resource levels updates
        elif tool_name == "get_resource_levels":
            try:
                global resource_levels
                resource_levels = {}  # Reset resources
                
                if isinstance(tool_result, str):
                    # Try to extract and parse JSON
                    json_match = re.search(r'{.*}', tool_result, re.DOTALL)
                    if json_match:
                        clean_result = json_match.group(0).replace("'", '"')
                        clean_result = clean_result.replace("None", "null")
                        clean_result = clean_result.replace("True", "true")
                        clean_result = clean_result.replace("False", "false")
                        
                        try:
                            parsed_levels = json.loads(clean_result)
                            resource_levels = parsed_levels
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse resource levels JSON: {clean_result}")
                
                # Even if we can't parse the JSON, try to extract resource info via regex
                if not resource_levels and isinstance(tool_result, str):
                    # Look for resource IDs and levels
                    resource_pattern = r'["\'](T\d+)["\']\s*:\s*{([^}]+)}'
                    resource_matches = re.findall(resource_pattern, tool_result)
                    
                    for resource_id, resource_data in resource_matches:
                        # Extract name, capacity, and current level
                        name_match = re.search(r'["\'](name)["\']:\s*["\'](.*?)["\']', resource_data)
                        capacity_match = re.search(r'["\'](capacity)["\']:\s*["\'](.*?)["\']', resource_data)
                        level_match = re.search(r'["\'](current_level)["\']:\s*["\'](.*?)["\']', resource_data)
                        
                        resource_levels[resource_id] = {
                            "name": name_match.group(2) if name_match else f"Resource {resource_id}",
                            "capacity": capacity_match.group(2) if capacity_match else "Unknown",
                            "current_level": level_match.group(2) if level_match else "Unknown"
                        }
                
                logger.info(f"Updated resource levels: {resource_levels}")
            except Exception as e:
                logger.error(f"Error in get_resource_levels tracking: {str(e)}", exc_info=True)


@cl.on_chat_start
async def on_chat_start():
    """Initialize the chat session"""
    # Initialize the environment variables
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        await cl.Message(content="OpenAI API key is required. Please set OPENAI_API_KEY environment variable.").send()
        return
    
    # Create the LangChain ChatOpenAI model
    langchain_model = ChatOpenAI(
        api_key=api_key,
        model='gpt-4o',
        temperature=0.1
    )
    
    # Initialize tool collection and agent
    try:
        # Create an initial message
        await cl.Message(content="Connecting to Farm Control Server...").send()
        
        # Initialize server parameters
        server_parameters = StdioServerParameters(
            command="uv",
            args=["run", "farm_control_server.py"],
            env=None,
        )
        
        # Run in a separate thread to not block the event loop
        # We need to use a context manager properly
        def init_tools():
            # Create the context manager
            context_manager = ToolCollection.from_mcp(server_parameters, trust_remote_code=True)
            # Enter the context manager to get the actual tool collection
            tools = context_manager.__enter__()
            return context_manager, tools
        
        # Get both the context manager and the actual tools
        cm, tools = await asyncio.to_thread(init_tools)
        
        # Store both in the session for proper cleanup later
        cl.user_session.set("context_manager", cm)
        cl.user_session.set("tool_collection", tools)
        
        # Create new message with connection status
        tools_info = f"Connected! Loaded {len(tools.tools)} tools from MCP server"
        await cl.Message(content=tools_info).send()
        
        # Create our agent
        agent = SmartFarmAgent(tools=tools.tools, model=langchain_model)
        
        # Store the agent in the user session
        cl.user_session.set("agent", agent)
        
        # Initialize status information
        try:
            # Fetch active actuators
            if "get_active_actuators" in agent.tools:
                active_result = agent.tools["get_active_actuators"]()
                agent._update_tracking("get_active_actuators", "", active_result)
            
            # Fetch resource levels
            if "get_resource_levels" in agent.tools:
                resource_result = agent.tools["get_resource_levels"]()
                agent._update_tracking("get_resource_levels", "", resource_result)
        except Exception as e:
            logger.error(f"Error initializing status information: {str(e)}")
        
        # Create farm status elements
        await update_status_elements()
        
        # Create quick action elements
        await create_quick_actions()
        
        # Welcome message
        welcome_message = """# 🌱 Farm Control Assistant

Welcome to your direct farm management assistant! You can control your farm systems with natural language commands.

**Try these commands:**
- Show me all fields
- Start irrigation in North Field
- What are the water levels?
- Turn off pumps in East Field

The assistant will execute commands immediately without asking for confirmation."""
        
        await cl.Message(content=welcome_message).send()
            
    except Exception as e:
        error_msg = f"Error connecting to Farm Control Server: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await cl.Message(content=error_msg).send()




async def update_status_elements():
    """Create or update status elements in the UI"""
    global active_operations, resource_levels
    
    # Create active operations content
    active_ops_content = "### Active Operations\n\n"
    if active_operations:
        for actuator_id, details in active_operations.items():
            name = details.get("name", actuator_id)
            active_ops_content += f"- {name} ({actuator_id}): {details.get('status', 'active')}\n"
    else:
        active_ops_content += "No active operations\n"
    
    # Create resource content
    resource_content = "\n### Resource Levels\n\n"
    if resource_levels:
        for resource_id, details in resource_levels.items():
            if isinstance(details, dict):
                name = details.get("name", f"Resource {resource_id}")
                current = details.get("current_level", "Unknown")
                capacity = details.get("capacity", "Unknown")
                resource_content += f"- {name} ({resource_id}): {current}/{capacity}\n"
            else:
                # If the value isn't a dict, just display it directly
                resource_content += f"- Resource {resource_id}: {details}\n"
    else:
        resource_content += "Resource level information not available yet\n"
    
    # Send the status message
    status_message = f"{active_ops_content}{resource_content}"
    await cl.Message(content=status_message, author="Status").send()


async def create_quick_actions():
    """Create quick action buttons in the UI"""
    actions_message = """### Quick Actions

Click one of the following actions:

- [Show All Fields](action:show_fields)
- [Check Water Levels](action:check_water)
- [Show Active Irrigation](action:active_irrigation)
- [⚠️ Emergency Stop](action:emergency_stop)
"""
    await cl.Message(content=actions_message).send()


async def message_handler(content, msg_type):
    """Handle intermediate messages during agent processing"""
    if msg_type == "tool":
        await cl.Message(content=content, author="Tool").send()
    elif msg_type == "result":
        await cl.Message(content=content, author="Result").send()


@cl.on_message
async def on_message(message: cl.Message):
    """Process incoming user messages"""
    # Get message content
    msg_content = message.content
    
    # Handle action links
    if msg_content.startswith("action:"):
        action_name = msg_content.replace("action:", "").strip()
        
        if action_name == "show_fields":
            await process_message("Show me all fields")
        elif action_name == "check_water":
            await process_message("What are the current water levels?")
        elif action_name == "active_irrigation":
            await process_message("Show me active irrigation")
        elif action_name == "emergency_stop":
            confirm_msg = "⚠️ Are you sure you want to stop ALL operations? Reply with 'CONFIRM STOP' to execute emergency shutdown."
            await cl.Message(content=confirm_msg).send()
        else:
            await process_message(msg_content)
    # Handle emergency stop confirmation
    elif msg_content.upper() == "CONFIRM STOP":
        await process_message("Emergency stop all operations")
    else:
        # Regular message - process through agent
        await process_message(msg_content)


async def process_message(message_content):
    """Process a message through the agent and update the UI"""
    # Get the agent from the session
    agent = cl.user_session.get("agent")
    if not agent:
        await cl.Message(content="Agent not initialized. Please restart the chat.").send()
        return
        
    # Create a loading message
    msg = cl.Message(content="Processing...")
    await msg.send()
    
    try:
        # Process the message through our agent
        response = await agent.run(message_content, message_handler=message_handler)
        
        # Remove the loading message and send the response as a new message
        await msg.remove()
        await cl.Message(content=response).send()
        
        # Update status elements
        await update_status_elements()
        
    except Exception as e:
        error_msg = f"Error processing message: {str(e)}"
        logger.error(error_msg, exc_info=True)
        # Remove the loading message and send the error as a new message
        await msg.remove()
        await cl.Message(content=error_msg).send()

# Also fix the cleanup method
@cl.on_stop
async def on_stop():
    """Clean up when the user stops the conversation"""
    # Get the context manager from the session
    context_manager = cl.user_session.get("context_manager")
    if context_manager:
        try:
            # Exit the context manager properly
            await asyncio.to_thread(
                lambda: context_manager.__exit__(None, None, None)
            )
            logger.info("Tool collection closed successfully")
        except Exception as e:
            logger.error(f"Error closing tool collection: {str(e)}", exc_info=True)


if __name__ == "__main__":
    # Start the Chainlit app
    import uvicorn
    import sys
    
    port = int(os.environ.get("CHAINLIT_PORT", 8000))
    
    # Check if we're running with chainlit
    if "chainlit" in sys.argv[0]:
        # Running through chainlit command
        pass
    else:
        # Direct execution
        uvicorn.run("chainlit_app:app", host="0.0.0.0", port=port)