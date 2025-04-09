import requests
import json

# ThingsBoard settings
THINGSBOARD_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"

# Function to get JWT token
def get_jwt_token():
    url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {
        "username": USERNAME,
        "password": PASSWORD
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json().get("token")
    else:
        print("Failed to authenticate:", response.text)
        return None

# Function to import a rule chain from a JSON file
def import_rule_chain(jwt_token, rule_chain_json):
    # Try different endpoints
    endpoints = [
        # "/api/ruleChain/import",     # Singular version without query param
        "/api/ruleChains/import",    # Plural version without query param
        # "/api/ruleChain/import?overwrite=true",  # Singular with overwrite
        # "/api/ruleChains/import?overwrite=true"  # Plural with overwrite
    ]
    
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }
    
    # ry both sending as a direct object and as an array
    payloads = [
        rule_chain_json,  # Direct JSON object
        [rule_chain_json]  # JSON wrapped in array
    ]
    
    # Try all combinations
    for endpoint in endpoints:
        for payload in payloads:
            url = f"{THINGSBOARD_URL}{endpoint}"
            print(f"\nTrying endpoint: {url}")
            print(f"Payload type: {'Array' if isinstance(payload, list) else 'Object'}")
            
            try:
                response = requests.post(url, headers=headers, json=payload)
                print(f"Response status: {response.status_code}")
                print(f"Response content: {response.text}")
                
                if response.status_code == 200:
                    print("Success! Rule chain imported successfully.")
                    return response.json()
            except Exception as e:
                print(f"Exception occurred: {str(e)}")
    
    print("All import attempts failed.")
    return None

# function to format the rule chain data correctly
def format_rule_chain_data(json_data):
    # Check if the data is in the expected format
    if isinstance(json_data, dict) and "ruleChain" in json_data and "metadata" in json_data:
        # Data is likely already in the correct format
        return json_data
    
    # If it's just a rule chain object
    if isinstance(json_data, dict) and "name" in json_data:
        # Wrap it in the expected structure
        return {
            "ruleChain": json_data,
            "metadata": {
                "nodes": [],
                "connections": []
            }
        }
    
    # If it's an array, try to extract the first item
    if isinstance(json_data, list) and len(json_data) > 0:
        return format_rule_chain_data(json_data[0])
    
    # Return as is if we can't determine the format
    return json_data

# Main function
def main():
    jwt_token = get_jwt_token()
    if not jwt_token:
        print("Authentication failed. Exiting.")
        return

    # Load the rule chain JSON file
    try:
        with open("temperature_rule_chain.json", "r") as file:
            rule_chain_json = json.load(file)
            # Try to format the data correctly
            formatted_data = format_rule_chain_data(rule_chain_json)
            print("Rule chain JSON loaded and formatted.")
    except Exception as e:
        print(f"Failed to load rule chain JSON file: {e}")
        return

    # Import the rule chain
    import_rule_chain(jwt_token, formatted_data)

if __name__ == "__main__":
    main()






