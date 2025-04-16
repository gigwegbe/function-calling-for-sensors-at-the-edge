import requests
import json
import os
from typing import Dict, Any, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

class ActuatorControlClient:
    """Client for interacting with the Actuator Control LLM API."""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or "http://localhost:8085"
        self.session = requests.Session()
        self.conversation_history = []
    
    def chat(self, message: str) -> Dict[str, Any]:
        """Send a message to the chat endpoint and return the response."""
        endpoint = f"{self.base_url}/chat"
        try:
            response = self.session.post(
                endpoint,
                json={"content": message}
            )
            response.raise_for_status()
            data = response.json()
            
            # Add to conversation history
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": data["response"]})
            
            # Display the response
            self._display_chat_response(data)
            
            return data
        except requests.RequestException as e:
            console.print(f"[bold red]Error communicating with API:[/bold red] {str(e)}")
            return {"error": str(e)}
    
    def get_actuators(self) -> List[Dict[str, Any]]:
        """Get all actuators from the API."""
        endpoint = f"{self.base_url}/actuators"
        try:
            response = self.session.get(endpoint)
            response.raise_for_status()
            actuators = response.json()
            
            # Display the actuators
            self._display_actuators(actuators)
            
            return actuators
        except requests.RequestException as e:
            console.print(f"[bold red]Error getting actuators:[/bold red] {str(e)}")
            return []
    
    def update_actuator_state(self, actuator_id: str, state: bool) -> Dict[str, Any]:
        """Update the state of an actuator."""
        endpoint = f"{self.base_url}/actuators/{actuator_id}/state"
        try:
            response = self.session.put(
                endpoint,
                json={"state": state}
            )
            response.raise_for_status()
            result = response.json()
            
            # Display the result
            console.print(
                f"[bold green]Actuator {result['name']} state updated to "
                f"{'ON' if result['state'] else 'OFF'}[/bold green]"
            )
            
            return result
        except requests.RequestException as e:
            console.print(f"[bold red]Error updating actuator state:[/bold red] {str(e)}")
            return {"error": str(e)}
    
    def create_actuator(self, name: str, actuator_type: str, label: str, info: Dict = None) -> Dict[str, Any]:
        """Create a new actuator."""
        endpoint = f"{self.base_url}/actuators"
        data = {
            "name": name,
            "type": actuator_type,
            "label": label,
            "additionalInfo": info or {}
        }
        
        try:
            response = self.session.post(
                endpoint,
                json=data
            )
            response.raise_for_status()
            result = response.json()
            
            # Display the result
            console.print(f"[bold green]Actuator created:[/bold green] {result['name']}")
            
            return result
        except requests.RequestException as e:
            console.print(f"[bold red]Error creating actuator:[/bold red] {str(e)}")
            return {"error": str(e)}
    
    def _display_chat_response(self, data: Dict[str, Any]) -> None:
        """Display the chat response and actuator states in a nice format."""
        # Display the chat response
        console.print(Panel(
            data["response"],
            title="[bold blue]Assistant Response[/bold blue]",
            border_style="blue",
            expand=False
        ))
        
        # Display actuator states if available
        if data.get("actuator_states"):
            self._display_actuator_states(data["actuator_states"])
    
    def _display_actuators(self, actuators: List[Dict[str, Any]]) -> None:
        """Display a list of actuators in a table."""
        table = Table(title="Actuators", box=box.ROUNDED)
        
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Type", style="blue")
        table.add_column("State", style="magenta")
        table.add_column("Monitoring", style="yellow")
        
        for actuator in actuators:
            table.add_row(
                actuator["id"],
                actuator["name"],
                actuator["type"],
                "ON" if actuator["state"] else "OFF",
                "Active" if actuator["monitoring_active"] else "Paused"
            )
        
        console.print(table)
    
    def _display_actuator_states(self, states: Dict[str, Dict[str, Any]]) -> None:
        """Display actuator states in a concise table."""
        table = Table(title="Current Actuator States", box=box.SIMPLE)
        
        table.add_column("Name", style="green")
        table.add_column("State", style="bold")
        
        for actuator_id, info in states.items():
            table.add_row(
                info["name"],
                "[bold green]ON[/bold green]" if info["state"] else "[bold red]OFF[/bold red]"
            )
        
        console.print(table)

    def interactive(self):
        """Start an interactive session with the actuator control system."""
        console.print("[bold green]Welcome to the Actuator Control System![/bold green]")
        console.print("Type 'exit' to quit, 'help' for commands")
        
        while True:
            user_input = console.input("[bold blue]> [/bold blue]")
            
            if user_input.lower() in ("exit", "quit"):
                break
            elif user_input.lower() == "help":
                self._display_help()
            elif user_input.lower() == "list":
                self.get_actuators()
            else:
                self.chat(user_input)
    
    def _display_help(self):
        """Display help information."""
        help_text = """
        [bold]Available Commands:[/bold]
        - [cyan]help[/cyan]: Show this help message
        - [cyan]list[/cyan]: List all actuators and their states
        - [cyan]exit[/cyan] or [cyan]quit[/cyan]: Exit the application
        
        [bold]Natural Language Examples:[/bold]
        - "Turn on the irrigation pump"
        - "What's the state of all actuators?"
        - "Create a new pump actuator called 'Greenhouse Pump'"
        - "Stop monitoring the field irrigation system"
        - "Is the main pump running right now?"
        """
        console.print(Panel(help_text, title="[bold]Help[/bold]", border_style="blue"))


if __name__ == "__main__":
    # Get API URL from environment or use default
    api_url = os.environ.get("ACTUATOR_API_URL", "http://localhost:8085")
    
    client = ActuatorControlClient(api_url)
    client.interactive()