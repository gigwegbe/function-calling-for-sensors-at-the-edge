#!/usr/bin/env python3
# memory_agent_debug.py

import json
import os
import sys
import traceback
from pathlib import Path
from services.memory_control_agent import MemoryControlAgent
from services.farm_control_service import FarmControlService
from models.models import init_db, get_session_factory
# Add better error handling and logging
import logging
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG for detailed logs
    format="%(asctime)s - %(levelname)s - %(message)s"
)

engine = init_db()
SessionFactory = get_session_factory(engine)

# Create service
farm_control_service = FarmControlService(SessionFactory)

def create_agent():
    """Create the memory control agent with detailed error tracing"""
    try:
        # Get the directory of this script
        script_dir = Path(__file__).parent.absolute()
        
        # Construct the path to the RAG data file
        rag_path = os.path.join(script_dir, "data", "control_rag_data.json")
        
        # Check if the file exists
        if not os.path.exists(rag_path):
            logging.error(f"RAG data file not found at: {rag_path}")
            alternative_paths = [
                os.path.join(script_dir, "control_rag_data.json"),
                os.path.join(Path.home(), "data", "control_rag_data.json"),
                os.path.join(script_dir, "..", "data", "control_rag_data.json")
            ]
            
            # Try alternative paths
            for alt_path in alternative_paths:
                if os.path.exists(alt_path):
                    logging.info(f"Found RAG data at alternative path: {alt_path}")
                    rag_path = alt_path
                    break
            else:
                # If file still not found, raise an error
                raise FileNotFoundError(f"RAG data file not found. Tried: {rag_path} and {alternative_paths}")
        
        logging.info(f"Creating agent with RAG data from: {rag_path}")
        
        
        # Create the agent with debug mode enabled
        agent = MemoryControlAgent(rag_path,farm_control_service)
        
        # Test the most basic agent functionality
        logging.info("Testing basic agent initialization...")
        system_info = agent.system_info
        logging.info(f"Agent system_info: {json.dumps(system_info, default=str)[:100]}...")
        
        # Debug the key internal components
        logging.info("Debugging agent components...")
        if not hasattr(agent, 'vector_search') or not agent.vector_search:
            logging.error("Vector search component is missing or not initialized")
        else:
            logging.info(f"Vector search initialized with {len(agent.vector_search.examples)} examples")
        
        if not hasattr(agent, 'llm') or not agent.llm:
            logging.error("LLM component is missing or not initialized")
        else:
            logging.info(f"LLM initialized: {agent.llm}")
        
        # Verify the graph is properly compiled
        logging.info("Testing graph compilation...")
        if hasattr(agent, 'graph') and agent.graph:
            logging.info("Graph successfully compiled.")
            
            # Inspect nodes in the graph
            if hasattr(agent.graph, '_nodes'):
                logging.info(f"Graph nodes: {list(agent.graph._nodes.keys())}")
            else:
                logging.warning("Cannot inspect graph nodes - unexpected graph structure")
        else:
            logging.error("Graph is not properly compiled or missing")
            
        return agent
        
    except Exception as e:
        logging.error(f"Error creating agent: {e}")
        traceback.print_exc()
        raise

def patch_run_method(agent):
    """
    Apply a monkey patch to the run method to get better error visibility
    """
    original_run = agent.run
    
    def patched_run(user_request):
        logging.info(f"Running agent with request: {user_request}")
        try:
            # Add a test to make sure the graph is working
            logging.info("Testing graph invocation...")
            
            # This simple test bypasses the main run logic to test the graph directly
            test_result = agent.graph.invoke({"user_request": "test"})
            logging.info(f"Graph test result: {type(test_result)}")
            
            # Now try the actual request
            logging.info(f"Invoking graph with actual request: {user_request}")
            result = original_run(user_request)
            return result
        except Exception as e:
            logging.error(f"Detailed error in agent.run: {e}")
            logging.error(traceback.format_exc())
            return {
                "user_request": user_request,
                "intent_category": "error",
                "error": str(e),
                "function_calls": [],
                "user_response": f"Error processing request: {str(e)}"
            }
    
    # Replace the original method with our patched version
    agent.run = patched_run
    return agent

def debug_parse_intent(agent, user_request):
    """Debug the parse_intent function specifically"""
    try:
        # Create a test state and manually run the parse_intent function
        test_state = {"user_request": user_request}
        
        # Find the parse_intent function
        if hasattr(agent, '_build_graph'):
            # This is tricky since the function is defined inside _build_graph
            # Let's try extracting it
            parse_intent = None
            for name, method in agent.__class__.__dict__.items():
                if name == 'parse_intent':
                    parse_intent = method.__get__(agent, agent.__class__)
                    break
            
            if not parse_intent:
                # Try to get it from the graph if compiled
                if hasattr(agent.graph, '_nodes') and 'parse_intent' in agent.graph._nodes:
                    parse_intent = agent.graph._nodes['parse_intent']
            
            if parse_intent:
                logging.info("Running parse_intent directly...")
                result = parse_intent(test_state)
                logging.info(f"parse_intent result: {json.dumps(result, default=str)}")
                return result
            else:
                logging.error("Could not find parse_intent function for debugging")
        else:
            logging.error("Agent does not have _build_graph method")
        
    except Exception as e:
        logging.error(f"Error in debug_parse_intent: {e}")
        traceback.print_exc()
    
    return None

def debug_resolve_user_intent(agent, user_request):
    """Debug the resolve_user_intent method directly"""
    try:
        if hasattr(agent, 'resolve_user_intent'):
            logging.info("Testing resolve_user_intent directly...")
            result = agent.resolve_user_intent(user_request)
            logging.info(f"resolve_user_intent result: {json.dumps(result, default=str)[:200]}...")
            return result
        else:
            logging.error("Agent does not have resolve_user_intent method")
    except Exception as e:
        logging.error(f"Error in resolve_user_intent: {e}")
        traceback.print_exc()
    
    return None

def main():
    try:
        # Create the agent
        agent = create_agent()
        
        # Apply debugging patch to run method
        agent = patch_run_method(agent)
        
        # Debug the resolve_user_intent method directly
        test_request = "Turn off everything in the East Field"
        debug_result = debug_resolve_user_intent(agent, test_request)
        if debug_result:
            logging.info("resolve_user_intent works directly")
        else:
            logging.error("resolve_user_intent failed")
        
        # Test inputs
        inputs = [
            "Switch off the actuator FD-0900",
            "Turn off everything in the East Field",
            "How much water do we have left?",
            "Start the system",
            "Irrigate the first field",
            "Turn off all water_valves components",
            "Can you turn on fertilizer dispensers FD-0900 in field F009?",
            "Can you turn on the components in Central Field?",
            "can you turn on the actuator FD-0900",
        ]
        
        # Process each input
        for req in inputs:
            print(f"\n>  {req}")
            try:
                # Try to run the request
                result = agent.run(req)
                logging.info(f"Raw result: {json.dumps(result, default=str)[:200]}...")
                print(f"Result: {result.get('user_response') if result else 'No response'}")
            except Exception as e:
                logging.error(f"Error processing request '{req}': {e}")
                traceback.print_exc()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        traceback.print_exc()
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())