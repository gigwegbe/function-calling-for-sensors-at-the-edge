# farm_control_server_enhanced.py

from mcp.server.fastmcp import FastMCP
from models.models import Farm, Field, Sensor, Actuator, Resource, get_session_factory, init_db
from services.farm_control_service import FarmControlService
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('farm_control_server')

# Initialize database and session factory
session_factory = get_session_factory(init_db())
farm_service = FarmControlService(session_factory)

# Create FastMCP instance
mcp = FastMCP("farm_control_server")

# Track active operations for UI
active_operations = {}

@mcp.prompt()
def direct_control_instruction() -> str:
    """
    Provides instructions for direct, no-confirmation farm control operations.
    """
    return """You are a direct farm control assistant. When users request actions like starting irrigation or turning on pumps:
    
    1. Execute operations immediately without asking for confirmation
    2. Use control_actuator tool directly when users say things like "water the field", "irrigate", "turn on/off"
    3. When the user mentions a field by name, find the correct actuators and control them
    4. Do not ask clarifying questions unless absolutely necessary
    5. Focus your responses on what was done, rather than what will be done
    6. Keep your responses concise and action-oriented
    """

@mcp.resource("farms://search/{farm_name}")
def search_farms(farm_name: str) -> str:
    """
    Find farms whose names match or contain the search term.

    Args:
        farm_name: e.g. "Green Valley"

    Returns:
        JSON list of matching farms
    """
    farms = farm_service.get_all_farms()
    matching_farms = [farm for farm in farms if farm_name.lower() in farm['name'].lower()]
    return str(matching_farms)

@mcp.resource("farms://all")
def all_farms() -> str:
    """List all farms in the system."""
    farms = farm_service.get_all_farms()
    return str(farms)

@mcp.tool()
def list_all_farms() -> str:
    """Get a list of all registered farms."""
    farms = farm_service.get_all_farms()
    return str(farms)

@mcp.tool()
def get_farm_overview() -> str:
    """
    Get a summary of all farms, including their status and key metrics.
    This is a high-level overview.
    Returns:
        JSON object with farm summaries
    """
    farms = farm_service.get_all_farms()
    farm_summaries = []
    for farm in farms:
        summary = {
            "id": farm.get("id"),
            "name": farm.get("name"),
            "location": farm.get("location"),
            "status": farm.get("status"),
            "fields_count": len(farm.get("fields", [])),
            "resources": farm.get("resources", {}),
        }
        farm_summaries.append(summary)
    return str(farm_summaries)
    
@mcp.tool()
def get_farm_details(farm_id: str) -> str:
    """
    Get complete information about a specific farm.

    Args:
        farm_id: e.g. "1"

    Returns:
        JSON object with farm details
    """
    farm = farm_service.get_farm_by_id(farm_id)
    return str(farm)

@mcp.tool()
def get_fields_for_farm(farm_id: str) -> str:
    """
    Get all fields for a specific farm.

    Args:
        farm_id: e.g. "1"

    Returns:
        JSON list of field information
    """
    farm = farm_service.get_farm_by_id(farm_id)
    if farm and 'fields' in farm:
        return str(farm['fields'])
    return "No fields found for this farm"

@mcp.tool()
def get_sensor_data(sensor_id: str) -> str:
    """
    Retrieve latest sensor readings for a given sensor.

    Args:
        sensor_id: e.g. "1"

    Returns:
        JSON object with sensor metrics
    """
    sensor = farm_service.get_sensor_by_id(sensor_id)
    return str(sensor)

@mcp.tool()
def control_actuator(actuator_id: str, status: str) -> str:
    """
    Change the state of any actuator (e.g., pumps, dispensers) without confirmation.

    Args:
        actuator_id: e.g. "FD-0900"
        status: "open" or "close"

    Returns:
        Confirmation message or error details
    """
    logger.info(f"Controlling actuator {actuator_id} to {status}")
    
    # Update active operations tracking
    if status == "open":
        active_operations[actuator_id] = {"type": "actuator", "status": "active"}
    else:
        if actuator_id in active_operations:
            del active_operations[actuator_id]
    
    result = farm_service.update_actuator_status(actuator_id, status)
    return str(result)

@mcp.tool()
def batch_control_actuators(field_id: str, actuator_type: str, status: str) -> str:
    """
    Control multiple actuators in a field at once.
    
    Args:
        field_id: e.g. "F001"
        actuator_type: "all", "pumps", "water_valves", or "fertilizer_dispensers"
        status: "open" or "close"
        
    Returns:
        JSON object with operation results
    """
    logger.info(f"Batch controlling actuators in field {field_id}, type {actuator_type}, status {status}")
    
    # Get all actuators for the field
    actuators = farm_service.get_actuators_by_field(field_id)
    
    # Filter by type if specified
    if actuator_type != "all":
        filtered_actuators = []
        for actuator in actuators:
            if "type" in actuator and actuator_type in actuator["type"]:
                filtered_actuators.append(actuator)
        actuators = filtered_actuators
    
    # Control each actuator
    results = {}
    for actuator in actuators:
        actuator_id = actuator.get("id")
        if actuator_id:
            # Update tracking
            if status == "open":
                active_operations[actuator_id] = {"type": "actuator", "status": "active", "field": field_id}
            else:
                if actuator_id in active_operations:
                    del active_operations[actuator_id]
            
            result = farm_service.update_actuator_status(actuator_id, status)
            results[actuator_id] = result
    
    return str(results)

@mcp.tool()
def field_irrigation_control(field_name: str, action: str) -> str:
    """
    Control irrigation for a field by name with simplified commands.
    
    Args:
        field_name: e.g. "North Field"
        action: "start" or "stop"
        
    Returns:
        JSON object with operation results
    """
    logger.info(f"Controlling irrigation for field {field_name}, action {action}")
    
    # Map action to status
    status = "open" if action == "start" else "close"
    
    # Find field by name
    field = farm_service.get_field_by_name(field_name)
    if not field:
        return f"Field '{field_name}' not found"
    
    field_id = field.get("id")
    
    # Get irrigation actuators for the field (pumps and water valves)
    actuators = farm_service.get_actuators_by_field(field_id)
    
    # Control irrigation actuators
    results = {}
    for actuator in actuators:
        actuator_id = actuator.get("id")
        actuator_type = actuator.get("type")
        
        # Only control water-related actuators (pumps and water valves)
        if actuator_type in ["pumps", "water_valves"]:
            # Update tracking
            if status == "open":
                active_operations[actuator_id] = {"type": "actuator", "status": "active", "field": field_id}
            else:
                if actuator_id in active_operations:
                    del active_operations[actuator_id]
                    
            result = farm_service.update_actuator_status(actuator_id, status)
            results[actuator_id] = result
    
    return str(results)

@mcp.tool()
def get_field_actuators(field_id: str) -> str:
    """
    Get all actuators associated with a field.

    Args:
        field_id: e.g. "1"

    Returns:
        JSON list of actuators
    """
    actuators = farm_service.get_actuators_by_field(field_id)
    return str(actuators)

@mcp.tool()
def get_field_sensors(field_id: str) -> str:
    """
    Get all sensors associated with a field.

    Args:
        field_id: e.g. "1"

    Returns:
        JSON list of sensors
    """
    sensors = farm_service.get_sensors_by_field(field_id)
    return str(sensors)

@mcp.tool()
def get_resource_levels() -> str:
    """List current levels of all resources like water or fertilizer."""
    levels = farm_service.get_resource_levels()
    return str(levels)

@mcp.tool()
def update_resource_level(resource_id: str, new_level: float) -> str:
    """
    Set a new level for a resource.

    Args:
        resource_id: e.g. "1"
        new_level: e.g. 75.5

    Returns:
        Confirmation or error message
    """
    result = farm_service.update_resource_level(resource_id, new_level)
    return str(result)

@mcp.tool()
def get_actuator_status(actuator_id: str) -> str:
    """
    Check the current status of a specific actuator.

    Args:
        actuator_id: e.g. "1"

    Returns:
        JSON object with actuator status
    """
    actuator = farm_service.get_actuator_by_id(actuator_id)
    return str(actuator)

@mcp.tool()
def get_active_actuators() -> str:
    """List all actuators that are currently turned on (open)."""
    actuators = farm_service.get_active_actuators()
    return str(actuators)

@mcp.tool()
def find_field_by_name(field_name: str) -> str:
    """
    Look up field info by field name.

    Args:
        field_name: e.g. "South Field"

    Returns:
        JSON object with field data
    """
    field = farm_service.get_field_by_name(field_name)
    return str(field)

@mcp.tool()
def create_irrigation_schedule(field_id: str, schedule_data: str) -> str:
    """
    Set a new irrigation schedule for a field.

    Args:
        field_id: ID of the field
        schedule_data: JSON string with time and days

    Example:
        {"field_id": "1", "schedule_data": {"start_time": "06:00", "duration": 30, "days": ["Monday", "Wednesday"]}}

    Returns:
        Confirmation or scheduling errors
    """
    result = farm_service.create_irrigation_schedule(field_id, schedule_data)
    return str(result)

@mcp.tool()
def emergency_stop_all() -> str:
    """
    Stop all actuators immediately (emergency shutdown).
    
    Returns:
        JSON object with operation results
    """
    logger.info("Emergency stop triggered - stopping all actuators")
    
    # Get all active actuators
    actuators = farm_service.get_active_actuators()
    
    # Stop each one
    results = {}
    for actuator in actuators:
        actuator_id = actuator.get("id")
        if actuator_id:
            result = farm_service.update_actuator_status(actuator_id, "close")
            results[actuator_id] = result
            
            # Update tracking
            if actuator_id in active_operations:
                del active_operations[actuator_id]
    
    # Clear the active operations tracking
    active_operations.clear()
    
    return str(results)

@mcp.tool()
def get_active_operations() -> str:
    """
    Get a list of currently active operations for the UI.
    
    Returns:
        JSON object with active operations
    """
    # Format active operations for display
    formatted_operations = []
    
    for actuator_id, operation in active_operations.items():
        # Get actuator details
        actuator = farm_service.get_actuator_by_id(actuator_id)
        if actuator:
            actuator_name = actuator.get("name", actuator_id)
            actuator_type = actuator.get("type", "unknown")
            field_id = operation.get("field", "unknown")
            
            # Get field name if possible
            field_name = "Unknown Field"
            if field_id != "unknown":
                field = farm_service.get_field_by_id(field_id)
                if field:
                    field_name = field.get("name", field_id)
            
            # Format the operation description
            operation_type = "Unknown operation"
            if actuator_type == "pumps":
                operation_type = "Pumping"
            elif actuator_type == "water_valves":
                operation_type = "Watering"
            elif actuator_type == "fertilizer_dispensers":
                operation_type = "Fertilizing"
            
            formatted_operations.append(f"{operation_type} in {field_name} ({actuator_name})")
    
    return json.dumps(formatted_operations)

@mcp.tool()
def get_field_crop_info(field_name: str) -> str:
    """
    Get crop information for a specific field.
    
    Args:
        field_name: e.g. "North Field"
        
    Returns:
        JSON object with crop details
    """
    field = farm_service.get_field_by_name(field_name)
    if not field:
        return f"Field '{field_name}' not found"
    
    crop_info = {
        "field_name": field.get("name"),
        "crop_type": field.get("crop", "Unknown"),
        "area": field.get("area", "Unknown"),
        "sensors": {}
    }
    
    # Get sensor data if available
    field_id = field.get("id")
    sensors = farm_service.get_sensors_by_field(field_id)
    
    for sensor in sensors:
        sensor_type = sensor.get("type")
        if sensor_type:
            crop_info["sensors"][sensor_type] = {
                "value": sensor.get("value", "No data"),
                "unit": sensor.get("unit", "")
            }
    
    return json.dumps(crop_info)

if __name__ == "__main__":
    mcp.run(transport="stdio")