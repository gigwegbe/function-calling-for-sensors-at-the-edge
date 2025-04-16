import requests
import json
import os
from typing import Dict, Any, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.prompt import Prompt, Confirm

console = Console()

class TankFarmActuatorClient:
    """Client for interacting with the Tank Farm Actuator Control API."""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or "http://localhost:8085"
        self.session = requests.Session()
    
    def chat(self, message: str) -> Dict[str, Any]:
        """Send a message to the chat endpoint and return the response."""
        endpoint = f"{self.base_url}/chat"
        try:
            response = self.session.post(endpoint, json={"content": message})
            response.raise_for_status()
            data = response.json()
            
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
            response = self.session.put(endpoint, json={"state": state})
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
    
    def create_actuator(self, name: str, actuator_type: str, location: str = None, 
                        flow_rate: float = None, power_consumption: float = None) -> Dict[str, Any]:
        """Create a new actuator."""
        endpoint = f"{self.base_url}/actuators"
        data = {
            "name": name,
            "type": actuator_type,
            "location": location,
            "flow_rate": flow_rate,
            "power_consumption": power_consumption,
            "additionalInfo": {}
        }
        try:
            response = self.session.post(endpoint, json=data)
            response.raise_for_status()
            result = response.json()
            
            # Display the result
            console.print(f"[bold green]Actuator created:[/bold green] {result['name']}")
            return result
        except requests.RequestException as e:
            console.print(f"[bold red]Error creating actuator:[/bold red] {str(e)}")
            return {"error": str(e)}
    
    def get_resources(self) -> Dict[str, Any]:
        """Get all tank resources."""
        endpoint = f"{self.base_url}/resources"
        try:
            response = self.session.get(endpoint)
            response.raise_for_status()
            resources = response.json()
            
            # Display the resources
            self._display_resources(resources["resources"])
            return resources
        except requests.RequestException as e:
            console.print(f"[bold red]Error getting tank resources:[/bold red] {str(e)}")
            return {"resources": {}}
    
    def get_irrigation_status(self) -> Dict[str, Any]:
        """Get status of active irrigation sessions."""
        endpoint = f"{self.base_url}/irrigation/status"
        try:
            response = self.session.get(endpoint)
            response.raise_for_status()
            status = response.json()
            
            # Display the status
            self._display_irrigation_status(status)
            return status
        except requests.RequestException as e:
            console.print(f"[bold red]Error getting irrigation status:[/bold red] {str(e)}")
            return {"active_sessions": 0, "sessions": {}}
    
    def start_irrigation(self, pump_id: str, valve_ids: List[str], tank_id: str) -> Dict[str, Any]:
        """Start a new irrigation session."""
        endpoint = f"{self.base_url}/irrigation/start"
        try:
            response = self.session.post(
                endpoint,
                json={"pump_id": pump_id, "valve_ids": valve_ids, "tank_id": tank_id}
            )
            response.raise_for_status()
            result = response.json()
            
            # Display the result
            if result.get("success"):
                console.print(f"[bold green]Irrigation started:[/bold green] Session ID {result['session_id']}")
                console.print(f"Estimated runtime: {result['estimated_runtime']:.1f} minutes")
            else:
                console.print(f"[bold red]Failed to start irrigation:[/bold red] {result.get('error', 'Unknown error')}")
            return result
        except requests.RequestException as e:
            console.print(f"[bold red]Error starting irrigation:[/bold red] {str(e)}")
            return {"error": str(e)}
    
    def stop_irrigation(self, session_id: str) -> Dict[str, Any]:
        """Stop an active irrigation session."""
        endpoint = f"{self.base_url}/irrigation/stop/{session_id}"
        try:
            response = self.session.post(endpoint)
            response.raise_for_status()
            result = response.json()
            
            # Display the result
            if result.get("success"):
                console.print(f"[bold green]Irrigation stopped:[/bold green] Used {result['water_used']:.1f} liters over {result['duration_minutes']:.1f} minutes")
            else:
                console.print(f"[bold red]Failed to stop irrigation:[/bold red] {result.get('error', 'Unknown error')}")
            return result
        except requests.RequestException as e:
            console.print(f"[bold red]Error stopping irrigation:[/bold red] {str(e)}")
            return {"error": str(e)}
    
    def get_recommendations(self) -> List[Dict[str, Any]]:
        """Get system recommendations."""
        endpoint = f"{self.base_url}/recommendations"
        try:
            response = self.session.get(endpoint)
            response.raise_for_status()
            recommendations = response.json()
            
            # Display the recommendations
            self._display_recommendations(recommendations)
            return recommendations
        except requests.RequestException as e:
            console.print(f"[bold red]Error getting recommendations:[/bold red] {str(e)}")
            return []
    
    def get_water_usage_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get water usage statistics."""
        endpoint = f"{self.base_url}/statistics/water-usage?days={days}"
        try:
            response = self.session.get(endpoint)
            response.raise_for_status()
            stats = response.json()
            
            # Display the stats
            self._display_water_usage_stats(stats, days)
            return stats
        except requests.RequestException as e:
            console.print(f"[bold red]Error getting water usage stats:[/bold red] {str(e)}")
            return {}
    
    # Display methods
    def _display_chat_response(self, data: Dict[str, Any]) -> None:
        """Display the chat response and system states."""
        console.print(Panel(data["response"], title="[bold blue]Assistant Response[/bold blue]", border_style="blue"))
    
    def _display_actuators(self, actuators: List[Dict[str, Any]]) -> None:
        """Display a list of actuators in a table."""
        table = Table(title="Actuators", box=box.ROUNDED)
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Type", style="blue")
        table.add_column("State", style="magenta")
        for actuator in actuators:
            table.add_row(
                actuator["id"],
                actuator["name"],
                actuator["type"],
                "ON" if actuator["state"] else "OFF"
            )
        console.print(table)
    
    def _display_resources(self, resources: Dict[str, Dict[str, Any]]) -> None:
        """Display tank resources in a table."""
        table = Table(title="Water Tank Resources", box=box.ROUNDED)
        table.add_column("Name", style="green")
        table.add_column("Level", style="blue")
        table.add_column("Capacity", style="cyan")
        table.add_column("Percentage", style="magenta")
        for tank_id, info in resources.items():
            table.add_row(
                info["name"],
                f"{info['current_level']:.1f} {info.get('units', 'liters')}",
                f"{info['capacity']:.1f} {info.get('units', 'liters')}",
                f"{info['percentage']:.1f}%"
            )
        console.print(table)
    
    def _display_irrigation_status(self, status: Dict[str, Any]) -> None:
        """Display irrigation session status."""
        active_count = status.get("active_sessions", 0)
        if active_count == 0:
            console.print("[bold yellow]No active irrigation sessions[/bold yellow]")
        else:
            console.print(f"[bold green]{active_count} Active Irrigation Sessions:[/bold green]")
    
    def _display_recommendations(self, recommendations: List[Dict[str, Any]]) -> None:
        """Display system recommendations."""
        if not recommendations:
            console.print("[bold yellow]No system recommendations at this time[/bold yellow]")
        else:
            console.print(f"[bold yellow]{len(recommendations)} System Recommendations:[/bold yellow]")
    
    def _display_water_usage_stats(self, stats: Dict[str, Any], days: int) -> None:
        """Display water usage statistics."""
        console.print(f"[bold blue]Water Usage Statistics (Last {days} Days)[/bold blue]")
        console.print(f"Total Water Used: {stats.get('total_water_used', 0):.1f} liters")
        console.print(f"Total Duration: {stats.get('total_duration_minutes', 0):.1f} minutes")
        console.print(f"Sessions: {stats.get('session_count', 0)}")
        
if __name__ == "__main__":
    api_url = os.environ.get("TANK_FARM_API_URL", "http://localhost:8085")
    client = TankFarmActuatorClient(api_url)

    console.print("[bold blue]Welcome to the Tank Farm Actuator Control System![/bold blue]")
    console.print("[bold green]Type your commands below to interact with the system. Type 'exit' to quit.[/bold green]")

    while True:
        # Prompt the user for input
        user_input = Prompt.ask("[bold yellow]You[/bold yellow]")

        # Exit the loop if the user types 'exit'
        if user_input.lower() in ["exit", "quit"]:
            console.print("[bold blue]Goodbye![/bold blue]")
            break

        # Show a loading indicator while waiting for the response
        with console.status("[bold green]Processing your request...[/bold green]", spinner="dots"):
            response = client.chat(user_input)

        # Display the response or error
        if "error" in response:
            console.print(f"[bold red]Error:[/bold red] {response['error']}")