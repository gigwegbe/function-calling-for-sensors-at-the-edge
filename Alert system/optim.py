import requests
import json
import uuid
from datetime import datetime

# ThingsBoard settings
THINGSBOARD_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"
ROOT_RULE_CHAIN_ID = "cf80ba30-1847-11f0-9b77-45d09c1e5989"

# Function to get JWT token
def get_jwt_token():
    url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {
        "username": USERNAME,
        "password": PASSWORD
    }
    print("Authenticating with ThingsBoard...")
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("Authentication successful.")
        return response.json().get("token")
    else:
        print("Failed to authenticate:", response.text)
        return None

# Function to create a UUID
def generate_uuid():
    return str(uuid.uuid4())

# Function to create a rule chain directly
def create_rule_chain(jwt_token, rule_chain_data):
    url = f"{THINGSBOARD_URL}/api/ruleChain"
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }
    print("Creating rule chain with the following data:")
    print(json.dumps(rule_chain_data, indent=2))

    try:
        response = requests.post(url, headers=headers, json=rule_chain_data)
        print(f"Response status: {response.status_code}")
        print(f"Response content: {response.text}")

        if response.status_code == 200:
            print("Success! Rule chain created successfully.")
            return response.json()
        else:
            print(f"Failed to create rule chain: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Exception occurred: {str(e)}")

    return None

# Function to update rule chain metadata
def update_rule_chain_metadata(jwt_token, rule_chain_id, metadata):
    url = f"{THINGSBOARD_URL}/api/ruleChain/metadata"
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }
    print(f"Updating metadata for rule chain {rule_chain_id} with data:")
    print(json.dumps(metadata, indent=2))

    try:
        response = requests.post(url, headers=headers, json=metadata)
        print(f"Response status: {response.status_code}")
        print(f"Response content: {response.text}")

        if response.status_code == 200:
            print("Success! Metadata updated successfully.")
            return response.json()
        else:
            print(f"Failed to update metadata: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Exception occurred: {str(e)}")

    return None

# Function to get rule chain metadata
def get_rule_chain_metadata(jwt_token, rule_chain_id):
    url = f"{THINGSBOARD_URL}/api/ruleChain/{rule_chain_id}/metadata"
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }

    try:
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            print("Success! Retrieved rule chain metadata.")
            return response.json()
        else:
            print(f"Failed to get rule chain metadata: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Exception occurred: {str(e)}")

    return None

# Function to add a forwarding node to the root rule chain metadata
def add_forwarding_node(metadata, custom_rule_chain_id):
    current_time = int(datetime.now().timestamp() * 1000)

    forwarding_node = {
        "type": "org.thingsboard.rule.engine.flow.TbRuleChainInputNode",
        "name": "Check the condition",
        "configuration": {
            "forwardMsgToDefaultRuleChain": False,
            "ruleChainId": custom_rule_chain_id
        },
        "additionalInfo": {
            "description": "",
            "layoutX": 964,
            "layoutY": 145
        }
    }

    # Adding the forwarding node to the nodes list
    metadata["nodes"].append(forwarding_node)

    # Connection from the "Save Timeseries" node to the new forwarding node
    timeseries_node_index = next((index for (index, d) in enumerate(metadata["nodes"]) if d["type"] == "org.thingsboard.rule.engine.telemetry.TbMsgTimeseriesNode"), None)
    if timeseries_node_index is not None:
        metadata["connections"].append({
            "fromIndex": timeseries_node_index,
            "toIndex": len(metadata["nodes"]) - 1,
            "type": "Success"
        })
    else:
        print("Error: Could not find 'Save Timeseries' node.")

    return metadata

# Create rule chain with nodes for temperature monitoring [soil moisture,....]
def build_temperature_rule_chain():
    rule_chain_data = {
        "name": "Tem",
        "type": "CORE",
        "root": False,
        "debugMode": False,
        "tenantId": {
            "id": "337c4a58-be4d-45d6-9daf-f2e08991f0fd",
            "entityType": "TENANT"
        },
        "configuration": {},
        "additionalInfo": {}
    }
    return rule_chain_data

# Metadata for the rule chain and defining inside node
def build_rule_chain_metadata(rule_chain_id):
    current_time = int(datetime.now().timestamp() * 1000)
    

    nodes = [
        {
            "type": "org.thingsboard.rule.engine.filter.TbJsFilterNode",
            "name": "Temperature Filter",
            "configuration": {
                "jsScript": "return msg.humidity > 20;"
            },
            "additionalInfo": {
                "layoutX": 260,
                "layoutY": 151,
                "description": "Checks if temperature exceeds 20"
            }
        },
        {
            "type": "org.thingsboard.rule.engine.action.TbCreateAlarmNode",
            "name": "Create High Temp Alarm",
            "configuration": {
                "alarmType": "High Temperature",
                "alarmDetailsBuildJs": """
                var details = {};
                if (metadata.prevAlarmDetails) {
                    details = JSON.parse(metadata.prevAlarmDetails);
                    //remove prevAlarmDetails from metadata
                    delete metadata.prevAlarmDetails;
                    //now metadata is the same as it comes IN this rule node
                }


                return details;
                
                """,


                "severity": "CRITICAL",
                "propagate": True,
                "useMessageAlarmData": False
            },
            "additionalInfo": {
                "layoutX": 400,
                "layoutY": 100
            }
        },
        {
            "type": "org.thingsboard.rule.engine.action.TbClearAlarmNode",
            "name": "Clear High Temp Alarm",
            "configuration": {
                "alarmType": "High Temperature",
                "alarmDetailsBuildJs": """
                var details = {};
                if (metadata.prevAlarmDetails) {
                    details = JSON.parse(metadata.prevAlarmDetails);
                    //remove prevAlarmDetails from metadata
                    delete metadata.prevAlarmDetails;
                    //now metadata is the same as it comes IN this rule node
                }


                return details;
                
                """,


                "propagate": True
            },
            "additionalInfo": {
                "layoutX": 400,
                "layoutY": 250
            }
        }
    ]

    connections = [
        {
            "fromIndex": 0,
            "toIndex": 1,
            "type": "True"
        },
        {
            "fromIndex": 0,
            "toIndex": 2,
            "type": "False"
        }
    ]

    metadata = {
        "ruleChainId": {
            "id": rule_chain_id,
            "entityType": "RULE_CHAIN"
        },
        "version": 1,
        "firstNodeIndex": 0,
        "nodes": nodes,
        "connections": connections,
        "ruleChainConnections": []
    }

    return metadata

# This is the main function
def main():
    jwt_token = get_jwt_token()
    if not jwt_token:
        print("Authentication failed. Exiting.")
        return

    # Build and create the rule chain
    rule_chain_data = build_temperature_rule_chain()
    created_rule_chain = create_rule_chain(jwt_token, rule_chain_data)

    if created_rule_chain:
        rule_chain_id = created_rule_chain.get("id", {}).get("id")
        if rule_chain_id:
            # Update metadata for the rule chain
            metadata = build_rule_chain_metadata(rule_chain_id)
            update_rule_chain_metadata(jwt_token, rule_chain_id, metadata)

            # Get the existing metadata for the root rule chain
            root_metadata = get_rule_chain_metadata(jwt_token, ROOT_RULE_CHAIN_ID)
            if root_metadata:
                # Add the forwarding node to the root rule chain metadata
                updated_root_metadata = add_forwarding_node(root_metadata, rule_chain_id)

                # Update the root rule chain metadata
                update_rule_chain_metadata(jwt_token, ROOT_RULE_CHAIN_ID, updated_root_metadata)
            else:
                print("Failed to retrieve root rule chain metadata.")
        else:
            print("Could not extract rule chain ID from response.")
    else:
        print("Failed to create rule chain.")

if __name__ == "__main__":
    main()
