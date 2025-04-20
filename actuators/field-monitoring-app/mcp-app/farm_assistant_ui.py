from flask import Flask, render_template, request, jsonify
import asyncio
import os
import json
import logging
from dotenv import load_dotenv
from farm_mcp_client import FarmMCPClient

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('web_client.log')
    ]
)
logger = logging.getLogger('farm_web_client')

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='static')

# Global client instance and lock
client = FarmMCPClient()
client_lock = asyncio.Lock()

# Path to server script
SERVER_SCRIPT_PATH = os.environ.get("SERVER_SCRIPT_PATH", "farm_control_server_enhanced.py")

@app.route('/')
def index():
    """Render the main UI page"""
    return render_template('index.html')

@app.route('/api/connect', methods=['POST'])
async def connect():
    """Connect to the MCP server"""
    async with client_lock:
        if client.session is not None:
            return jsonify({'status': 'already_connected'})
        
        try:
            await client.connect_to_server(SERVER_SCRIPT_PATH)
            return jsonify({'status': 'connected', 'tools': client.available_tools})
        except Exception as e:
            logger.error(f"Error connecting to server: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/send_message', methods=['POST'])
async def send_message():
    """Send a message to the MCP server and get a response"""
    data = request.json
    user_message = data.get('message', '')
    
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400
    
    async with client_lock:
        if client.session is None:
            try:
                await client.connect_to_server(SERVER_SCRIPT_PATH)
            except Exception as e:
                logger.error(f"Error connecting to server: {e}")
                return jsonify({'error': f"Failed to connect to server: {str(e)}"}), 500
        
        try:
            # Process message without confirmations
            result = await client.process_message(user_message)
            
            # Clean up the result for better UI display
            result = result.replace('\\n', '\n').replace('\\t', '    ')
            
            # Remove any trailing "Do you want to proceed?" type questions
            confirmation_phrases = [
                "Would you like to proceed?",
                "Should I proceed?",
                "Do you want to proceed?",
                "Shall I continue?",
                "Do you want me to perform this action?",
                "Would you like me to execute this?",
                "Should I execute this command?"
            ]
            
            for phrase in confirmation_phrases:
                if phrase in result:
                    result = result.split(phrase)[0].strip()
            
            return jsonify({'message': result})
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/farm_status')
async def farm_status():
    """Get current farm status information"""
    async with client_lock:
        if client.session is None:
            try:
                await client.connect_to_server(SERVER_SCRIPT_PATH)
            except Exception as e:
                logger.error(f"Error connecting to server: {e}")
                return jsonify({'error': f"Failed to connect to server: {str(e)}"}), 500
        
        try:
            # Get active operations directly using the specialized tool
            try:
                active_operations = await client.process_message("get_active_operations")
                # Parse JSON if it's a JSON string
                if active_operations.startswith('[') or active_operations.startswith('{'):
                    active_operations_list = json.loads(active_operations)
                    active_operations = "\n".join(active_operations_list)
            except:
                logger.warning("Failed to get active operations, falling back to general query")
                active_operations = await client.process_message("What operations are currently active?")
            
            # Get resource levels
            resource_levels = await client.process_message("get_resource_levels")
            
            # Format the resource levels for better display
            try:
                resource_data = json.loads(resource_levels.replace("'", '"'))
                formatted_resources = []
                
                for resource_id, details in resource_data.items():
                    name = details.get("name", f"Resource {resource_id}")
                    level = details.get("current_level", "Unknown")
                    capacity = details.get("capacity", "Unknown")
                    
                    formatted_resources.append(f"{name}: {level}/{capacity}")
                
                resource_levels = "\n".join(formatted_resources)
            except:
                # If parsing fails, just use the raw string
                pass
            
            return jsonify({
                'active_operations': active_operations,
                'resource_levels': resource_levels
            })
        except Exception as e:
            logger.error(f"Error getting farm status: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/quick_action', methods=['POST'])
async def quick_action():
    """Execute a predefined quick action"""
    data = request.json
    action_type = data.get('action_type', '')
    
    quick_actions = {
        'show_fields': 'Show me all fields',
        'check_water': 'What\'s the water level?',
        'active_irrigation': 'Show active irrigation',
        'stop_all': 'Emergency stop all'
    }
    
    if action_type not in quick_actions:
        return jsonify({'error': 'Invalid action type'}), 400
    
    action_message = quick_actions[action_type]
    
    async with client_lock:
        if client.session is None:
            try:
                await client.connect_to_server(SERVER_SCRIPT_PATH)
            except Exception as e:
                logger.error(f"Error connecting to server: {e}")
                return jsonify({'error': f"Failed to connect to server: {str(e)}"}), 500
        
        try:
            # For emergency stop, use direct method without confirmations
            if action_type == 'stop_all':
                result = await client.process_message("emergency_stop_all")
                # Add a clear confirmation message
                result = "Emergency stop executed. All systems have been shut down.\n\n" + result
            else:
                result = await client.process_message(action_message)
            
            return jsonify({
                'message': result,
                'action': action_message
            })
        except Exception as e:
            logger.error(f"Error executing quick action: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/control_actuator', methods=['POST'])
async def control_actuator():
    """Directly control an actuator"""
    data = request.json
    actuator_id = data.get('actuator_id', '')
    status = data.get('status', '')
    
    if not actuator_id or status not in ['open', 'close']:
        return jsonify({'error': 'Invalid actuator ID or status'}), 400
    
    async with client_lock:
        if client.session is None:
            try:
                await client.connect_to_server(SERVER_SCRIPT_PATH)
            except Exception as e:
                logger.error(f"Error connecting to server: {e}")
                return jsonify({'error': f"Failed to connect to server: {str(e)}"}), 500
        
        try:
            result = await client.control_actuator(actuator_id, status)
            return jsonify({'message': result})
        except Exception as e:
            logger.error(f"Error controlling actuator: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/field_irrigation', methods=['POST'])
async def field_irrigation():
    """Control irrigation for a field"""
    data = request.json
    field_name = data.get('field_name', '')
    action = data.get('action', '')
    
    if not field_name or action not in ['start', 'stop']:
        return jsonify({'error': 'Invalid field name or action'}), 400
    
    async with client_lock:
        if client.session is None:
            try:
                await client.connect_to_server(SERVER_SCRIPT_PATH)
            except Exception as e:
                logger.error(f"Error connecting to server: {e}")
                return jsonify({'error': f"Failed to connect to server: {str(e)}"}), 500
        
        try:
            result = await client.control_field_irrigation(field_name, action)
            return jsonify({'message': result})
        except Exception as e:
            logger.error(f"Error controlling field irrigation: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/disconnect', methods=['POST'])
async def disconnect():
    """Disconnect from the MCP server"""
    async with client_lock:
        if client.session is None:
            return jsonify({'status': 'not_connected'})
        
        try:
            await client.close()
            return jsonify({'status': 'disconnected'})
        except Exception as e:
            logger.error(f"Error disconnecting from server: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("WEB_PORT", 8070))
    
    # Flask doesn't natively support asyncio, so we need a compatible server
    import uvicorn
    
    uvicorn.run(app, host="0.0.0.0", port=port)