import json
from typing import Dict, List, Tuple, Optional, Union
from load_and_process_farm_model import LoadAndProcessFarmModel

class FarmControlSystem(LoadAndProcessFarmModel):
    def __init__(self):
        super().__init__()
        self.actuator_registry = {}  # Maps actuator IDs to their locations and states
        self.resource_connections = {}  # Maps actuators to resources they use
        
    def build_actuator_registry(self):
        """Build a registry of all actuators and their states across the farm"""
        if not self.farm_data:
            raise ValueError("Farm data not loaded. Call load_from_json first.")
            
        for field_entry in self.farm_data["farm"]["fields"]:
            for field_id, field_data in field_entry.items():
                field_name = field_data["name"]
                
                # Process each actuator type (pumps, valves, dispensers)
                for actuator_type, actuators in field_data["actuators"].items():
                    for actuator in actuators:
                        actuator_id = self._get_actuator_id(actuator, actuator_type)
                        
                        self.actuator_registry[actuator_id] = {
                            "type": actuator_type,
                            "field_id": field_id,
                            "field_name": field_name,
                            "status": actuator.get("status"),
                            "details": actuator
                        }
                        
                        # Track connections between pumps and valves
                        if actuator_type == "pumps" and "linked_valves" in actuator:
                            for linked_valve in actuator["linked_valves"]:
                                if linked_valve not in self.actuator_registry:
                                    # The linked valve will be processed later
                                    self.actuator_registry[linked_valve] = {"linked_to": [actuator_id]}
                                else:
                                    if "linked_to" not in self.actuator_registry[linked_valve]:
                                        self.actuator_registry[linked_valve]["linked_to"] = []
                                    self.actuator_registry[linked_valve]["linked_to"].append(actuator_id)
        
        return self.actuator_registry
    
    def map_resources_to_actuators(self):
        """Map which resources each actuator is connected to based on type and location"""
        # Define the resource mapping rules
        resource_mappings = {
            "water_valves": "water",
            "fertilizer_dispensers": ["fertilizer_slurry", "liquid_fertilizer"]
        }
        
        for actuator_id, actuator_info in self.actuator_registry.items():
            if "type" not in actuator_info:
                continue  # Skip placeholder entries
                
            actuator_type = actuator_info["type"]
            if actuator_type in resource_mappings:
                resource_type = resource_mappings[actuator_type]
                self.resource_connections[actuator_id] = resource_type
                
                # For pumps, check what they're linked to
                if actuator_type == "pumps" and "details" in actuator_info:
                    pump_details = actuator_info["details"]
                    if "linked_valves" in pump_details:
                        linked_resources = []
                        for valve_id in pump_details["linked_valves"]:
                            if valve_id in self.resource_connections:
                                linked_resources.append(self.resource_connections[valve_id])
                        if linked_resources:
                            self.resource_connections[actuator_id] = linked_resources
        
        return self.resource_connections
    
    def get_actuator_state(self, actuator_id: str) -> Dict:
        """Get the current state and details of a specific actuator"""
        if actuator_id not in self.actuator_registry:
            raise ValueError(f"Actuator {actuator_id} not found in registry")
        return self.actuator_registry[actuator_id]
    
    def get_field_actuators(self, field_id: str) -> Dict[str, List]:
        """Get all actuators for a specific field"""
        field_actuators = {}
        for actuator_id, info in self.actuator_registry.items():
            if "field_id" in info and info["field_id"] == field_id:
                actuator_type = info["type"]
                if actuator_type not in field_actuators:
                    field_actuators[actuator_type] = []
                field_actuators[actuator_type].append({actuator_id: info})
        return field_actuators
    
    def get_active_actuators(self) -> Dict[str, Dict]:
        """Get all actuators with 'open' status"""
        return {
            actuator_id: info 
            for actuator_id, info in self.actuator_registry.items()
            if "status" in info and info["status"] == "open"
        }
    
    def get_resource_level(self, resource_id: str) -> Dict:
        """Get the current level of a specific resource"""
        if not self.farm_data or "resources" not in self.farm_data["farm"]:
            raise ValueError("Farm data not loaded or doesn't contain resource information")
            
        resources = self.farm_data["farm"]["resources"]
        for category, items in resources.items():
            if category == "tanks":
                for tank_type, tank_data in items.items():
                    if tank_data.get("id") == resource_id:
                        return tank_data
        
        raise ValueError(f"Resource {resource_id} not found")
    
    def get_resource_dependent_actuators(self, resource_id: str) -> List[str]:
        """Find actuators dependent on a specific resource"""
        resource_types = self._get_resource_type_by_id(resource_id)
        dependent_actuators = []
        
        for actuator_id, resource_type in self.resource_connections.items():
            if isinstance(resource_type, list):
                if any(r in resource_type for r in resource_types):
                    dependent_actuators.append(actuator_id)
            elif resource_type in resource_types:
                dependent_actuators.append(actuator_id)
                
        return dependent_actuators
    
    def _get_actuator_id(self, actuator: Dict, actuator_type: str) -> str:
        """Extract the appropriate ID field based on actuator type"""
        if actuator_type == "pumps":
            return actuator.get("pump_id")
        elif actuator_type in ["water_valves", "fertilizer_dispensers"]:
            return actuator.get("valve_id")
        else:
            # Generic fallback
            for key in actuator:
                if '_id' in key:
                    return actuator[key]
            raise ValueError(f"Could not determine ID for actuator: {actuator}")
    
    def _get_resource_type_by_id(self, resource_id: str) -> List[str]:
        """Get resource type based on its ID"""
        if not self.farm_data:
            return []
            
        resource_types = []
        tanks = self.farm_data["farm"]["resources"]["tanks"]
        for tank_type, tank_data in tanks.items():
            if tank_data.get("id") == resource_id:
                resource_types.append(tank_type)
                
        return resource_types
    
    def simulate_actuator_change(self, actuator_id: str, new_status: str) -> Dict:
        """Simulate changing an actuator's status and return its new state"""
        if actuator_id not in self.actuator_registry:
            raise ValueError(f"Actuator {actuator_id} not found in registry")
            
        valid_states = self.farm_data["farm"]["details"]["actuator_states"]
        if new_status not in valid_states:
            raise ValueError(f"Invalid status '{new_status}'. Valid states are: {valid_states}")
            
        # Update status in registry
        self.actuator_registry[actuator_id]["status"] = new_status
        
        # If this is a valve with linked pumps, we might need to update pump states
        if "linked_to" in self.actuator_registry[actuator_id]:
            for pump_id in self.actuator_registry[actuator_id]["linked_to"]:
                # Logic for how pump states should change based on valve changes
                # This is simplified - real implementation would depend on your requirements
                if new_status == "open":
                    self.actuator_registry[pump_id]["status"] = "open"
                elif new_status == "close":
                    # Check if any other linked valves are still open
                    pump_details = self.actuator_registry[pump_id]["details"]
                    if "linked_valves" in pump_details:
                        other_valves_open = False
                        for valve_id in pump_details["linked_valves"]:
                            if valve_id != actuator_id and self.actuator_registry.get(valve_id, {}).get("status") == "open":
                                other_valves_open = True
                                break
                        
                        if not other_valves_open:
                            self.actuator_registry[pump_id]["status"] = "close"
        
        return self.actuator_registry[actuator_id]



if __name__ == "__main__":
    control_system = FarmControlSystem()
    control_system.load_from_json("farm_model.json")
    
    # Build the actuator registry and resource connections
    control_system.build_actuator_registry()
    control_system.map_resources_to_actuators()
    
    # Get all active actuators
    active_actuators = control_system.get_active_actuators()
    print(f"Currently active actuators: {len(active_actuators)} which are: {active_actuators}")
    
    # Get all actuators for a specific field
    field_actuators = control_system.get_field_actuators("F001")
    print(f"Field F001 has {sum(len(actuators) for actuators in field_actuators.values())} actuators")
    
    # Simulate opening a water valve
    valve_id = "WV-0100"
    new_state = control_system.simulate_actuator_change(valve_id, "open")
    print(f"Changed {valve_id} to state: {new_state['status']}")
    
    # Check if linked pump was affected
    pump_id = "PUMP-0100"
    pump_state = control_system.get_actuator_state(pump_id)
    print(f"Linked pump {pump_id} is now in state: {pump_state['status']}")
    
    # Get actuators dependent on water tank
    water_dependent = control_system.get_resource_dependent_actuators("T001")
    print(f"{len(water_dependent)} actuators depend on water tank T001")