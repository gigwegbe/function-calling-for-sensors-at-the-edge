import chainlit as cl
from mcp import StdioServerParameters, ClientSession
from typing import Dict, Any, List
import asyncio
import json
import os
from langchain_openai import ChatOpenAI
from mcp.types import CallToolResult, TextContent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

# Initialize conversation history and tools cache
conversation_history = []
mcp_tools_cache = {}

@cl.on_chat_start
async def start():
    """Initialize the chat session with the farm control MCP server."""
    # Initialize system message
    cl.user_session.set(
        "message_history",
        [
            {
                "role": "system",
                "content": "You are a helpful AI assistant that can control farm systems. You have access to tools that can monitor and control farm equipment."
            }
        ]
    )

    # Set up the server parameters for farm control
    server_parameters = StdioServerParameters(
        command="uv",
        args=["run", "farm_control_server.py"],
        env=None,
    )

    # Send a loading message
    startup_message = cl.Message(content="Connecting to Farm Control System...")
    await startup_message.send()

@cl.on_mcp_connect
async def on_mcp_connect(connection, session: ClientSession):
    """Handle MCP server connection."""
    await cl.Message(f"Connected to MCP server: {connection.name}").send()
    cl.user_session.set("mcp_session", session)

    try:
        result = await session.list_tools()
        
        tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.inputSchema,
            }
            for t in result.tools
        ]
        
        mcp_tools_cache[connection.name] = tools
        
        mcp_tools = cl.user_session.get("mcp_tools", {})
        mcp_tools[connection.name] = tools
        cl.user_session.set("mcp_tools", mcp_tools)
        
        tool_names = [tool["name"] for tool in tools]
        await cl.Message(
            content=f"✅ Found {len(tools)} tools from {connection.name}:\n{', '.join(tool_names)}"
        ).send()
    except Exception as e:
        await cl.Message(content=f"Error listing tools from MCP server: {str(e)}").send()

@cl.on_mcp_disconnect
async def on_mcp_disconnect(name: str, session: ClientSession):
    """Handle MCP server disconnection."""
    if name in mcp_tools_cache:
        del mcp_tools_cache[name]

    mcp_tools = cl.user_session.get("mcp_tools", {})
    if name in mcp_tools:
        del mcp_tools[name]
        cl.user_session.set("mcp_tools", mcp_tools)

    await cl.Message(f"Disconnected from MCP server: {name}").send()

@cl.step(type="tool")
async def execute_tool(tool_name: str, tool_input: Dict[str, Any]):
    """Execute an MCP tool."""
    print("Executing tool:", tool_name)
    print("Tool input:", tool_input)
    
    mcp_name = None
    mcp_tools = cl.user_session.get("mcp_tools", {})

    for conn_name, tools in mcp_tools.items():
        if any(tool["name"] == tool_name for tool in tools):
            mcp_name = conn_name
            break

    if not mcp_name:
        return {"error": f"Tool '{tool_name}' not found in any connected MCP server"}

    mcp_session, _ = cl.context.session.mcp_sessions.get(mcp_name)

    try:
        result = await mcp_session.call_tool(tool_name, tool_input)
        return result
    except Exception as e:
        return {"error": f"Error calling tool '{tool_name}': {str(e)}"}
    

@cl.on_message
async def on_message(message: cl.Message):
    """Process user message and generate a response using farm control tools."""
    
    # Get message history and convert to LangChain message format
    raw_history = cl.user_session.get("message_history", [])
    messages = []
    
    # Convert message history to LangChain format
    for msg in raw_history:
        if msg["role"] == "system":
            messages.append(SystemMessage(content=msg["content"]))
        elif msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            if msg.get("tool_calls"):
                messages.append(AIMessage(
                    content=msg.get("content"),
                    additional_kwargs={"tool_calls": msg["tool_calls"]}
                ))
            else:
                messages.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "tool":
            messages.append(ToolMessage(
                content=msg["content"],
                tool_call_id=msg.get("tool_call_id")
            ))
    
    # Add current user message
    messages.append(HumanMessage(content=message.content))
    
    # Check for OpenAI API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        await cl.Message(content="⚠️ OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.").send()
        return
    
    # Access MCP sessions directly from context
    mcp_sessions = cl.context.session.mcp_sessions
    if not mcp_sessions:
        await cl.Message(content="Farm Control System is not connected. Please restart the chat.").send()
        return
    
    # Initialize the model
    model = ChatOpenAI(
        api_key=api_key,
        model="gpt-4",
        temperature=0.1
    )
    
    # Format tools for the model
    mcp_tools = cl.user_session.get("mcp_tools", {})
    all_tools = []
    for connection_tools in mcp_tools.values():
        all_tools.extend(connection_tools)
    
    
    #print("All tools found:", all_tools)
    # Format tools for OpenAI format
    openai_tools = await format_tools_for_openai(all_tools)
    
    # print("Formatted tools for OpenAI:", openai_tools)
    
    try:
        # Send thinking message
        thinking = cl.Message(content="Processing your request...")
        await thinking.send()
        
        # Get response from model
        response = await model.ainvoke(
        input=messages,  # Add the required input argument
        tools=openai_tools,
        tool_choice="auto"  # Changed from function_call to tool_choice
      )
 
   
        # Handle tool calls
                # Handle tool calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tool_call in response.tool_calls:
                try:
                    print("Tool call:", tool_call)
                    # Extract tool name and arguments - tool_call is a dict
                    tool_name = tool_call["name"]
                    # Use 'args' instead of 'arguments' and handle empty args
                    tool_args = tool_call.get("args", {})
                    if isinstance(tool_args, str):
                        tool_args = json.loads(tool_args)
                        
                    print("Tool name:", tool_name)
                    print("Tool arguments:", tool_args)
                    
                    # Execute tool
                    tool_result = await execute_tool(tool_name, tool_args)
                    
                    # Add tool call to history
                    raw_history.append({
                        "role": "assistant",
                        "content": "",  # Changed from None to empty string
                        "tool_calls": [{
                            "id": tool_call["id"],
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args)
                            }
                        }]
                    })
                                        
            
                    
                    # Show tool result
                    await cl.Message(
                        content=f"Raw Result:\n```json\n{json.dumps(serialize_tool_result(tool_result), indent=2)}\n```",
                        author="Debug"
                    ).send()
                    
                    interpretation = interpret_tool_result(tool_name, tool_result)
                    await cl.Message(
                        content=interpretation,
                        author="Assistant"
                    ).send()
                    
                    raw_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(serialize_tool_result(tool_result))
                    })
                    raw_history.append({
                        "role": "assistant",
                        "content": interpretation
                    })
                    
                    # Get follow-up response
                    messages.append(AIMessage(
                        content="",  # Changed from None to empty string
                        additional_kwargs={
                            "tool_calls": [{
                                "id": tool_call["id"],
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "args": json.dumps(tool_args)
                                }
                            }]
                        }
                    ))
                    messages.append(ToolMessage(
                        content=json.dumps(serialize_tool_result(tool_result)),
                        tool_call_id=tool_call["id"]
                    ))
                except Exception as e:
                    await cl.Message(content=f"Error executing tool: {str(e)}").send()
                    import traceback
                    print("Tool execution error:", traceback.format_exc())
                    
            msg = cl.Message(content="")
            await msg.send()
            
            for char in response.content:
                await msg.stream_token(char)
                await asyncio.sleep(0.005)
            
            raw_history.append({
                "role": "assistant",
                "content": response.content
            })
        
        # Update session history
        cl.user_session.set("message_history", raw_history)
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        await cl.Message(content=f"Error: {str(e)}\n```\n{error_details}\n```").send()
   
def serialize_tool_result(result):
    """Helper function to serialize tool results."""
    if isinstance(result, dict):
        return result
    elif isinstance(result, TextContent):
        return {
            "type": result.type,
            "text": result.text
        }
    elif hasattr(result, "content") and isinstance(result.content, list):
        # Handle case where content is a list of TextContent objects
        serialized_content = []
        for item in result.content:
            if isinstance(item, TextContent):
                serialized_content.append({
                    "type": item.type,
                    "text": item.text
                })
            else:
                serialized_content.append(str(item))
        return {"content": serialized_content}
    elif hasattr(result, "__dict__"):
        return result.__dict__
    return str(result)

def interpret_tool_result(tool_name: str, result: Any) -> str:
    """Have the model interpret the tool result in a human-friendly way."""
    try:
        # Get only the relevant parts of the result
        if isinstance(result, dict):
            # Extract only key status information
            relevant_data = {k: v for k, v in result.items() 
                           if k in ['status', 'name', 'type', 'text', 'value', 'level']}
        else:
            relevant_data = serialize_tool_result(result)
        
        serialized_result = json.dumps(relevant_data, indent=2)
        
        # Keep interpretation prompt minimal
        interpretation_messages = [
            HumanMessage(content=f"Briefly explain in simple terms what this {tool_name} shows:\n{serialized_result}")
        ]
        
        # Use gpt-3.5-turbo with strict limits
        model = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0,
            max_tokens=100
        )
        
        # Get quick interpretation
        interpretation = model.invoke(interpretation_messages)
        return interpretation.content

    except Exception as e:
        return f"Error interpreting result: {str(e)}"
     
async def format_tools_for_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format MCP tools to OpenAI function format."""
    openai_tools = []
    
    for tool in tools:
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            }
        }
        openai_tools.append(openai_tool)
    
    return openai_tools

@cl.on_stop
async def cleanup():
    """Clean up resources when the chat stops."""
    # Get the MCP session from user session
    mcp_session = cl.user_session.get("mcp_session")
    if mcp_session:
        try:
            # Close the session
            await mcp_session.close()
            print("MCP session closed successfully")
        except Exception as e:
            print(f"Error closing MCP session: {str(e)}")

if __name__ == "__main__":
    print("Starting Farm Control Chainlit app...")