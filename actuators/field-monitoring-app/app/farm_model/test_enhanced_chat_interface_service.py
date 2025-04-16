#!/usr/bin/env python3
"""
Test script to demonstrate the enhanced farm chat interface
"""

import json
import os
from dotenv import load_dotenv
from models import get_session_factory
from farm_control_service import FarmControlService
from improved_farm_chat import EnhancedFarmChatInterface

# Load environment variables
load_dotenv()

def print_divider():
    """Print a divider line"""
    print("\n" + "=" * 80 + "\n")

def main():
    """Run a series of test scenarios with the farm chat interface"""
    # Initialize the farm control service
    session_factory = get_session_factory()
    farm_service = FarmControlService(session_factory)
    
    # Create the chat interface
    farm_chat = EnhancedFarmChatInterface(farm_service, debug_mode=True)
    
    print_divider()
    print("FARM MANAGEMENT CHAT ASSISTANT DEMO")
    print_divider()
    
    # Test Case 1: Simple greeting and overview
    test_greeting(farm_chat)
    
    # Test Case 2: Field irrigation request
    test_irrigation_request(farm_chat)
    
    # Test Case 3: Field monitoring
    test_field_monitoring(farm_chat)
    
    # Test Case 4: Resource status
    test_resource_status(farm_chat)
    
    # Test Case 5: Equipment control
    test_equipment_control(farm_chat)
    
    # Test Case 6: Vague request that needs clarification
    test_vague_request(farm_chat)
    
    # Test Case 7: Bulk operation with confirmation
    test_bulk_operation(farm_chat)
    
    print_divider()
    print("End of demo. All test cases completed.")
    print_divider()

def test_greeting(farm_chat):
    """Test greeting and overview"""
    print("\nTEST CASE 1: GREETING AND OVERVIEW")
    
    query = "Hello, how's my farm doing today?"
    print(f"\nFarmer: {query}")
    
    response = farm_chat.chat(query)
    print(f"\nFarm Assistant: {response['response']}")
    
    print("\nExplanation: The system responds with a friendly greeting and provides a quick overview of the farm status.")

def test_irrigation_request(farm_chat):
    """Test irrigation request for a specific field"""
    print_divider()
    print("\nTEST CASE 2: FIELD IRRIGATION REQUEST")
    
    query = "I need to irrigate the North field"
    print(f"\nFarmer: {query}")
    
    response = farm_chat.chat(query)
    print(f"\nFarm Assistant: {response['response']}")
    
    print("\nExplanation: The system identifies the intent to irrigate a specific field, checks if it's already irrigating, then plans and executes the necessary actions (opening valves and activating pumps).")

def test_field_monitoring(farm_chat):
    """Test field monitoring request"""
    print_divider()
    print("\nTEST CASE 3: FIELD MONITORING")
    
    query = "What's the soil moisture in the South field?"
    print(f"\nFarmer: {query}")
    
    response = farm_chat.chat(query)
    print(f"\nFarm Assistant: {response['response']}")
    
    print("\nExplanation: The system queries moisture sensors in the specified field and presents the readings in a user-friendly format.")

def test_resource_status(farm_chat):
    """Test resource status request"""
    print_divider()
    print("\nTEST CASE 4: RESOURCE STATUS")
    
    query = "How much water do we have left in the tanks?"
    print(f"\nFarmer: {query}")
    
    response = farm_chat.chat(query)
    print(f"\nFarm Assistant: {response['response']}")
    
    print("\nExplanation: The system checks all water resources and provides current levels, capacities, and percentage full.")

def test_equipment_control(farm_chat):
    """Test equipment control request"""
    print_divider()
    print("\nTEST CASE 5: EQUIPMENT CONTROL")
    
    query = "Turn off the water valve in East field"
    print(f"\nFarmer: {query}")
    
    response = farm_chat.chat(query)
    print(f"\nFarm Assistant: {response['response']}")
    
    print("\nExplanation: The system identifies the specific valve, closes it, and reports the status change.")

def test_vague_request(farm_chat):
    """Test a vague request that needs clarification"""
    print_divider()
    print("\nTEST CASE 6: VAGUE REQUEST NEEDING CLARIFICATION")
    
    query = "Check the status"
    print(f"\nFarmer: {query}")
    
    response = farm_chat.chat(query)
    print(f"\nFarm Assistant: {response['response']}")
    
    # Respond to clarification
    follow_up = "I want to know which valves are open"
    print(f"\nFarmer: {follow_up}")
    
    follow_up_response = farm_chat.chat(follow_up)
    print(f"\nFarm Assistant: {follow_up_response['response']}")
    
    print("\nExplanation: The system identifies the request as too vague, asks for clarification, and then processes the clarified request.")

def test_bulk_operation(farm_chat):
    """Test a bulk operation that requires confirmation"""
    print_divider()
    print("\nTEST CASE 7: BULK OPERATION WITH CONFIRMATION")
    
    query = "Start irrigation in all fields"
    print(f"\nFarmer: {query}")
    
    response = farm_chat.chat(query)
    print(f"\nFarm Assistant: {response['response']}")
    
    # Provide confirmation
    confirmation = "Yes, proceed"
    print(f"\nFarmer: {confirmation}")
    
    confirmation_response = farm_chat.chat(confirmation)
    print(f"\nFarm Assistant: {confirmation_response['response']}")
    
    print("\nExplanation: The system identifies this as a bulk operation that requires confirmation, presents the actions it will take, waits for confirmation, and then executes only after approval.")

if __name__ == "__main__":
    main()