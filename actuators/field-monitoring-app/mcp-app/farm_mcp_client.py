# farm_mcp_client.py

import os
import json
import asyncio
import logging
import subprocess
from typing import Dict, List, Optional, Any, Union

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("farm_mcp_client")

class FarmMCPClient:
    """Client for interacting with the Farm Control MCP Server"""
    
    def __init__(self):
        self.process = None
        self.session = None
        self.available_tools = []
        self.stdin = None
        self.stdout = None
        
    async def connect_to_server(self, server_script_path: str) -> bool:
        """
        Start the MCP server process and establish a connection.
        
        Args:
            server_script_path: Path to the server script to run
            
        Returns:
            True if connection was successful
        """
        logger.info(f"Connecting to MCP server: {server_script_path}")
        
        try:
            # Start the server process
            self.process = await asyncio.create_subprocess_exec(
                "python3", server_script_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            self.stdin = self.process.stdin
            self.stdout = self.process.stdout
            
            # Wait for the server to initialize
            await asyncio.sleep(1)
            
            # Get available tools
            self.available_tools = await self._get_available_tools()
            
            self.session = {
                "connected": True,
                "tools": self.available_tools
            }
            
            logger.info(f"Connected to MCP server. Available tools: {len(self.available_tools)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            if self.process:
                try:
                    self.process.terminate()
                except:
                    pass
                self.process = None
            return False
    
    async def _get_available_tools(self) -> List[str]:
        """Get a list of available tools from the server"""
        if not self.process or not self.stdin or not self.stdout:
            return []
        
        try:
            # Send a handshake message to get tools
            handshake_msg = json.dumps({"type": "handshake", "version": "1.0"}) + "\n"
            self.stdin.write(handshake_msg.encode())
            await self.stdin.drain()
            
            # Read the response
            response_line = await self.stdout.readline()
            if not response_line:
                return []
                
            response = json.loads(response_line.decode().strip())
            if "tools" in response:
                return response["tools"]
            return []
            
        except Exception as e:
            logger.error(f"Failed to get available tools: {e}")
            return []
    
    async def process_message(self, message: str) -> str:
        """
        Process a message through the MCP server.
        
        Args:
            message: User message to process
            
        Returns:
            Response from the server
        """
        if not self.process or not self.stdin or not self.stdout:
            await self.connect_to_server("farm_control_server_enhanced.py")
        
        try:
            # Send the message to the server
            request = json.dumps({
                "type": "request",
                "message": message
            }) + "\n"
            
            self.stdin.write(request.encode())
            await self.stdin.drain()
            
            # Read the response
            response_line = await self.stdout.readline()
            if not response_line:
                return "No response from server"
                
            response = json.loads(response_line.decode().strip())
            return response.get("response", "Unknown response")
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return f"Error: {str(e)}"
    
    async def get_active_operations(self) -> str:
        """Get the currently active farm operations"""
        try:
            return await self.process_message("Show me the active operations")
        except Exception as e:
            logger.error(f"Error getting active operations: {e}")
            return "Error fetching active operations"
    
    async def get_resource_levels(self) -> str:
        """Get current resource levels"""
        try:
            return await self.process_message("What are the resource levels?")
        except Exception as e:
            logger.error(f"Error getting resource levels: {e}")
            return "Error fetching resource levels"
    
    async def execute_quick_action(self, action_type: str) -> str:
        """
        Execute a quick action.
        
        Args:
            action_type: Type of quick action to execute
            
        Returns:
            Response from the server
        """
        quick_actions = {
            'show_fields': 'Show me all fields',
            'check_water': 'What\'s the water level?',
            'active_irrigation': 'Show active irrigation',
            'stop_all': 'Emergency stop all'
        }
        
        if action_type not in quick_actions:
            return f"Unknown quick action: {action_type}"
        
        return await self.process_message(quick_actions[action_type])
    
    async def control_field_irrigation(self, field_name: str, action: str) -> str:
        """
        Control irrigation for a specific field.
        
        Args:
            field_name: Name of the field
            action: "start" or "stop"
            
        Returns:
            Response from the server
        """
        command = f"{action} irrigation in {field_name}"
        return await self.process_message(command)
    
    async def control_actuator(self, actuator_id: str, status: str) -> str:
        """
        Control a specific actuator directly.
        
        Args:
            actuator_id: ID of the actuator
            status: "open" or "close"
            
        Returns:
            Response from the server
        """
        command = f"Set actuator {actuator_id} to {status}"
        return await self.process_message(command)
    
    async def batch_control_field(self, field_name: str, action: str) -> str:
        """
        Control all actuators in a field.
        
        Args:
            field_name: Name of the field
            action: "start" or "stop"
            
        Returns:
            Response from the server
        """
        command = f"{action} all systems in {field_name}"
        return await self.process_message(command)
    
    async def close(self) -> None:
        """Close the connection to the server"""
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
            finally:
                self.process = None
                self.session = None
                self.stdin = None
                self.stdout = None