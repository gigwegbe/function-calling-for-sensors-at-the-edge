import os
import argparse
import uuid
from dotenv import load_dotenv
from withchat import chat_with_agent

# Load environment variables from .env file if available
load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="ThingsBoard Alarm Setup Assistant CLI")
    parser.add_argument("--new-session", action="store_true", help="Start a new conversation session")
    args = parser.parse_args()
    
    # Check for OpenAI API Key
    if not os.environ.get("OPENAI_PROJECT_API_KEY"):
        api_key = input("Please enter your OpenAI API key: ").strip()
        os.environ["OPENAI_PROJECT_API_KEY"] = api_key
    
    # Generate or load session ID
    session_file = ".session_id"
    if args.new_session or not os.path.exists(session_file):
        session_id = str(uuid.uuid4())
        with open(session_file, "w") as f:
            f.write(session_id)
        print("\n--- Starting new conversation ---\n")
    else:
        with open(session_file, "r") as f:
            session_id = f.read().strip()
        print("\n--- Continuing existing conversation ---\n")
    
    print("ThingsBoard Alarm Setup Assistant")
    print("Type 'exit' to quit, or 'new' to start a new conversation\n")
    
    # Show initial message about what the assistant can help with
    initial_message = (
        "Hi! I'm your farming and facility management assistant. I can help you set up alarms in ThingsBoard "
        "for monitoring sensors like soil moisture, soil temperature, soil_conductivity, and field_air_humidity. "
        "How can I help you today?"
    )
    print("Assistant:", initial_message)
    
    # Main conversation loop
    while True:
        user_input = input("\nYou: ").strip()
        
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("\nThank you for using the ThingsBoard Alarm Setup Assistant. Goodbye!")
            break
        
        if user_input.lower() == "new":
            session_id = str(uuid.uuid4())
            with open(session_file, "w") as f:
                f.write(session_id)
            print("\n--- Starting new conversation ---\n")
            continue
        
        # Process the user input
        try:
            response, session_id = chat_with_agent(user_input, session_id)
            print("\nAssistant:", response)
            
            # Update session ID file
            with open(session_file, "w") as f:
                f.write(session_id)
                
        except Exception as e:
            print(f"\nAn error occurred: {str(e)}")

if __name__ == "__main__":
    main()