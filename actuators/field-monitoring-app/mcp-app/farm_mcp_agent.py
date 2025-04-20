# Import required libraries
from smolagents import ToolCollection
from mcp import StdioServerParameters
from dotenv import load_dotenv
load_dotenv()
import os
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
import inspect

class DirectFarmAgent:
    """An improved agent that handles tool calling with minimal confirmation steps"""
    
    def __init__(self, tools, model):
        self.tools = {tool.name: tool for tool in tools}
        self.model = model
        self.tool_descriptions = self._generate_tool_descriptions()
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
    
    def run(self, user_input):
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
        response = self.model.invoke(messages)
        response_content = response.content
        
        # Check if there's a tool call in the response
        tool_call = self._extract_tool_call(response_content)
        
        if tool_call:
            tool_name = tool_call.get("tool_name")
            tool_input = tool_call.get("tool_input", "")
            
            if tool_name in self.tools:
                # Execute the tool
                try:
                    # Handle different tool input types
                    tool_result = self._execute_tool(tool_name, tool_input)
                    
                    # Add the tool call and result to the conversation
                    tool_response = f"I've completed the operation using the {tool_name} tool.\n\nResult: {tool_result}"
                    self.conversation_history.append({"role": "assistant", "content": tool_response})
                    
                    # Get final response
                    messages.append(AIMessage(content=response_content))
                    messages.append(HumanMessage(content=f"Tool result: {tool_result}"))
                    final_response = self.model.invoke(messages)
                    
                    # Add the final response to conversation history
                    self.conversation_history.append({"role": "assistant", "content": final_response.content})
                    return final_response.content
                except Exception as e:
                    error_msg = f"Error using tool '{tool_name}': {str(e)}"
                    print(f"Debug - {error_msg}")
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
                print(f"Failed to parse tool JSON: {tool_json_str}")
                print(f"Error: {str(e)}")
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

def main():
    # Initialize the environment variables
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key is required")
    
    # Create the LangChain ChatOpenAI model
    langchain_model = ChatOpenAI(
        api_key=api_key,
        model='gpt-4o',
        temperature=0.1
    )
    
    # Define the server parameters
    server_parameters = StdioServerParameters(
        command="uv",  # Using uv to run the script
        args=["run", "farm_control_server.py"],  # The server script we created
        env=None,
    )
    
    # Run the agent with farm control tools
    try:
        with ToolCollection.from_mcp(server_parameters, trust_remote_code=True) as tool_collection:
            # Print tools available for debugging
            print(f"Loaded {len(tool_collection.tools)} tools from MCP server")
            for i, tool in enumerate(tool_collection.tools):
                print(f"Tool {i+1}: {tool.name}")
            
            # Use our improved direct agent
            agent = DirectFarmAgent(tools=tool_collection.tools, model=langchain_model)
            
            # Start the conversation with the user
            print("\nFarm Control Agent is ready. Type 'exit' to quit.")
            user_input = input("What would you like to do? ")
            
            while user_input.lower() != 'exit':
                try:
                    response = agent.run(user_input)
                    print("\nAgent response:", response)
                except Exception as e:
                    print(f"\nError occurred: {str(e)}")
                
                user_input = input("\nWhat would you like to do next? ")
    except Exception as e:
        print(f"Error during initialization: {str(e)}")


if __name__ == "__main__":
    main()