import json
import traceback
from functools import wraps

def mcp_error_handler(func):
    """Decorator to handle errors in MCP tools and return formatted error messages"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            error_info = {
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            return json.dumps({"status": "error", "details": error_info})
    return wrapper

def format_response(data):
    """Format complex Python objects for return from MCP tools"""
    try:
        # If it's already a string, return it
        if isinstance(data, str):
            return data
            
        # Convert to JSON string
        return json.dumps(data, default=str)
    except Exception as e:
        return f"Error formatting response: {str(e)}"