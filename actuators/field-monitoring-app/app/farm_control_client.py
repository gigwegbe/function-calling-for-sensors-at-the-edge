#!/usr/bin/env python3
"""
Enhanced client for interacting with the Farm Management System API.
"""

import requests
import json
import os
import sys
import uuid
import time
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.prompt import Prompt, Confirm
from rich.markdown import Markdown
from datetime import datetime

console = Console()

class FarmManagementClient:
    """Client for interacting with the Farm Management System API."""
    
    def __init__(self, base_url: str = None, session_id: Optional[str] = None):
        self.base_url = base_url or "http://localhost:8060"
        self.session = requests.Session()
        self.chat_session_id = session_id or str(uuid.uuid4())
        self.conversation_history = []
        
    def chat(self, message: str, use_session: bool = True) -> Dict[str, Any]:
        """Send a message to the chat endpoint and return the response."""
        if use_session:
            endpoint = f"{self.base_url}/chat/{self.chat_session_id}"
        else:
            endpoint = f"{self.base_url}/chat"
            
        payload = {"message": message}
        
        try:
            console.print(f"[dim]Sending to API...[/dim]")
            response = self.session.post(endpoint, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            # Save to conversation history
            self.conversation_history.append({
                "user": message,
                "assistant": data["response"],
                "timestamp": datetime.now().isoformat()
            })
            
            # Display the response
            self._display_chat_response(data)
            return data
        except requests.RequestException as e:
            console.print(f"[bold red]Error communicating with API:[/bold red] {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                console.print(f"[bold red]Server response:[/bold red] {e.response.text}")
            return {"error": str(e), "response": "Sorry, I encountered an error communicating with the farm system."}
    
    def get_system_overview(self) -> Dict[str, Any]:
        """Get an overview of the farm system."""
        endpoint = f"{self.base_url}/system/overview"
        
        try:
            response = self.session.get(endpoint, timeout=20)
            response.raise_for_status()
            data = response.json()
            return data
        except requests.RequestException as e:
            console.print(f"[bold red]Error getting system overview:[/bold red] {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                console.print(f"[bold red]Server response:[/bold red] {e.response.text}")
            return {"error": str(e)}
    
    def get_fields(self) -> List[Dict[str, Any]]:
        """Get all fields in the farm system."""
        endpoint = f"{self.base_url}/fields"
        
        try:
            response = self.session.get(endpoint, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data
        except requests.RequestException as e:
            console.print(f"[bold red]Error getting fields:[/bold red] {str(e)}")
            return []
    
    def get_active_actuators(self) -> List[Dict[str, Any]]:
        """Get all active actuators in the farm system."""
        endpoint = f"{self.base_url}/actuators/active"
        
        try:
            response = self.session.get(endpoint, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data
        except requests.RequestException as e:
            console.print(f"[bold red]Error getting active actuators:[/bold red] {str(e)}")
            return []
    
    def get_resource_levels(self) -> Dict[str, Any]:
        """Get resource levels in the farm system."""
        endpoint = f"{self.base_url}/resources/levels"
        
        try:
            response = self.session.get(endpoint, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data
        except requests.RequestException as e:
            console.print(f"[bold red]Error getting resource levels:[/bold red] {str(e)}")
            return {}
    
    def save_conversation(self, filename: str = None) -> None:
        """Save the conversation history to a file."""
        if not self.conversation_history:
            console.print("[yellow]No conversation to save.[/yellow]")
            return
            
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"farm_conversation_{timestamp}.json"
            
        try:
            with open(filename, 'w') as f:
                json.dump(self.conversation_history, f, indent=2)
            console.print(f"[green]Conversation saved to {filename}[/green]")
        except Exception as e:
            console.print(f"[bold red]Error saving conversation:[/bold red] {str(e)}")
    
    # Display methods
    def _display_chat_response(self, data: Dict[str, Any]) -> None:
        """Display the chat response and system states."""
        response_text = data["response"]
        
        # Check if the response is markdown content and render accordingly
        if "```" in response_text or "**" in response_text or "#" in response_text:
            console.print(Panel(Markdown(response_text), title="[bold blue]Farm Assistant[/bold blue]", border_style="blue"))
        else:
            console.print(Panel(response_text, title="[bold blue]Farm Assistant[/bold blue]", border_style="blue"))
        
        # Check if there's execution data and display it
        if "metadata" in data and data["metadata"]:
            metadata = data["metadata"]
            
            # Display intent if available
            if metadata.get("intent"):
                intent = metadata["intent"]
                intent_type = intent.get("intent_type", "unknown")
                action = intent.get("action", "unknown")
                console.print(f"[dim]Intent: {intent_type}, Action: {action}[/dim]")
            
            # Display execution results if available
            if metadata.get("execution_results"):
                console.print("\n[bold cyan]Execution Results:[/bold cyan]")
                
                # Create a table for execution results
                table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
                table.add_column("Result")
                table.add_column("Details")
                
                for result in metadata["execution_results"]:
                    success = result.get("success", False)
                    details = result.get("details", {})
                    error = result.get("error")
                    
                    if success:
                        status = "[green]✓ Success[/green]"
                    else:
                        status = f"[red]✗ Failed: {error}[/red]"
                    
                    details_str = str(details) if details else "No details"
                    if len(details_str) > 50:
                        details_str = details_str[:47] + "..."
                        
                    table.add_row(status, details_str)
                
                console.print(table)
    
    def display_system_overview(self) -> None:
        """Display a comprehensive overview of the farm system."""
        overview = self.get_system_overview()
        
        if "error" in overview:
            console.print(f"[bold red]Error:[/bold red] {overview['error']}")
            return
        
        console.print("\n[bold blue]Farm System Overview[/bold blue]")
        
        # Display farm info
        farm_info = overview.get("farm_info", {})
        if farm_info:
            console.print("\n[bold cyan]Farm Information:[/bold cyan]")
            console.print(f"• Total Farms: {farm_info.get('total_farms', 0)}")
            console.print(f"• Total Fields: {farm_info.get('total_fields', 0)}")
            console.print(f"• Total Equipment: {farm_info.get('total_equipment', 0)}")
            console.print(f"• Total Sensors: {farm_info.get('total_sensors', 0)}")
        
        # Display active equipment
        active_equipment = overview.get("active_equipment", {})
        if active_equipment:
            console.print("\n[bold cyan]Active Equipment:[/bold cyan]")
            console.print(f"• Total Active: {active_equipment.get('count', 0)}")
            
            # Show by type
            by_type = active_equipment.get("by_type", {})
            for equip_type, count in by_type.items():
                equip_name = equip_type.replace("_", " ").title()
                console.print(f"• {equip_name}: {len(count) if isinstance(count, list) else count}")
        
        # Display field status
        field_status = overview.get("field_status", {})
        if field_status:
            console.print("\n[bold cyan]Field Status:[/bold cyan]")
            
            # Create field status table
            table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
            table.add_column("Field")
            table.add_column("Crop")
            table.add_column("Status")
            table.add_column("Area")
            
            for field_name, status in field_status.items():
                irrigating = status.get("is_irrigating", False)
                status_text = "[green]Irrigating[/green]" if irrigating else "[yellow]Not Irrigating[/yellow]"
                crop = status.get("crop", "Unknown")
                area = status.get("area", "Unknown")
                
                table.add_row(field_name, crop, status_text, area)
            
            console.print(table)
        
        # Display resource levels
        resource_levels = overview.get("resource_levels", {})
        if resource_levels:
            console.print("\n[bold cyan]Resource Levels:[/bold cyan]")
            
            # Create resource table
            table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
            table.add_column("Resource")
            table.add_column("Content")
            table.add_column("Level")
            table.add_column("Capacity")
            
            for resource_name, resource in resource_levels.items():
                content = resource.get("content", "Unknown")
                current = resource.get("current_level", "Unknown")
                capacity = resource.get("capacity", "Unknown")
                
                table.add_row(resource_name, content, current, capacity)
            
            console.print(table)

def handle_command(command: str, client: FarmManagementClient) -> bool:
    """Handle special commands and return True if handled."""
    # Strip the command character and trim
    cmd = command.strip()
    
    if cmd.startswith("/"):
        cmd = cmd[1:].strip()
    else:
        return False
    
    if cmd in ["help", "h", "?"]:
        console.print("\n[bold green]Available Commands:[/bold green]")
        console.print("  /help          - Show this help message")
        console.print("  /overview      - Show farm system overview")
        console.print("  /fields        - List all fields")
        console.print("  /active        - Show active equipment")
        console.print("  /resources     - Show resource levels")
        console.print("  /save [file]   - Save conversation history")
        console.print("  /clear         - Clear the screen")
        console.print("  /exit          - Exit the application")
        return True
        
    elif cmd == "overview":
        client.display_system_overview()
        return True
        
    elif cmd == "fields":
        fields = client.get_fields()
        if fields:
            console.print("\n[bold cyan]Farm Fields:[/bold cyan]")
            table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
            table.add_column("Name")
            table.add_column("ID")
            table.add_column("Crop")
            table.add_column("Area")
            
            for field in fields:
                table.add_row(
                    field.get("name", "Unknown"),
                    field.get("id", "Unknown"),
                    field.get("crop", "Unknown"),
                    field.get("area", "Unknown")
                )
            
            console.print(table)
        else:
            console.print("[yellow]No fields found.[/yellow]")
        return True
        
    elif cmd == "active":
        actuators = client.get_active_actuators()
        if actuators:
            console.print("\n[bold cyan]Active Equipment:[/bold cyan]")
            table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
            table.add_column("Name")
            table.add_column("ID")
            table.add_column("Type")
            table.add_column("Status")
            
            for actuator in actuators:
                table.add_row(
                    actuator.get("name", "Unknown"),
                    actuator.get("id", "Unknown"),
                    actuator.get("type", "Unknown").replace("_", " ").title(),
                    actuator.get("status", "Unknown")
                )
            
            console.print(table)
        else:
            console.print("[yellow]No active equipment found.[/yellow]")
        return True
        
    elif cmd == "resources":
        resources = client.get_resource_levels()
        if resources:
            console.print("\n[bold cyan]Resource Levels:[/bold cyan]")
            table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
            table.add_column("Resource")
            table.add_column("Level")
            table.add_column("Capacity")
            
            for resource_id, resource in resources.items():
                table.add_row(
                    resource.get("name", "Unknown"),
                    resource.get("current_level", "Unknown"),
                    resource.get("capacity", "Unknown")
                )
            
            console.print(table)
        else:
            console.print("[yellow]No resources found.[/yellow]")
        return True
        
    elif cmd.startswith("save"):
        # Extract filename if provided
        parts = cmd.split(maxsplit=1)
        filename = parts[1] if len(parts) > 1 else None
        client.save_conversation(filename)
        return True
        
    elif cmd == "clear":
        os.system('cls' if os.name == 'nt' else 'clear')
        console.print("[bold blue]Farm Management System[/bold blue]")
        console.print("[bold green]Type your commands below to interact with the system.[/bold green]")
        console.print("[bold green]Type /help for available commands.[/bold green]")
        return True
        
    elif cmd in ["exit", "quit"]:
        if client.conversation_history:
            if Confirm.ask("Would you like to save this conversation before exiting?"):
                client.save_conversation()
        console.print("[bold blue]Goodbye![/bold blue]")
        sys.exit(0)
        
    else:
        console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
        console.print("Type /help to see available commands.")
        return True
        
    return False  # Not handled

def main():
    """Main entry point for the client application."""
    # Get API URL from environment or use default
    api_url = os.environ.get("FARM_API_URL", "http://localhost:8060")
    
    # Create client
    session_id = str(uuid.uuid4())
    client = FarmManagementClient(api_url, session_id)
    
    console.print("[bold blue]===== Farm Management System =====")
    console.print("[bold green]Type your questions or commands below to interact with your farm.[/bold green]")
    console.print("[bold green]Type /help for available commands or /exit to quit.[/bold green]\n")
    
    # Get initial system overview
    console.print("[dim]Getting initial system overview...[/dim]")
    with console.status("[bold green]Connecting to the farm system...[/bold green]", spinner="dots"):
        try:
            client.display_system_overview()
        except Exception as e:
            console.print(f"[yellow]Could not retrieve initial overview: {str(e)}[/yellow]")
    
    # Welcome message
    welcome_message = client.chat("Hello, I'm a farmer. Give me an overview of my farm system.")
    
    # Main interaction loop
    while True:
        # Prompt the user for input
        user_input = Prompt.ask("[bold yellow]You[/bold yellow]")
        
        # Check if this is a special command
        if user_input.strip().startswith("/"):
            if handle_command(user_input, client):
                continue
        
        # Show a loading indicator while waiting for the response
        with console.status("[bold green]Processing your request...[/bold green]", spinner="dots"):
            response = client.chat(user_input)
        
        # If there was an error, it was already displayed by the chat method
        if "error" in response:
            continue

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold blue]Goodbye! Farm management system connection closed.[/bold blue]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]An unexpected error occurred: {str(e)}[/bold red]")
        sys.exit(1)