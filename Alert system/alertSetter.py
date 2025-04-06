import requests
import json
import uuid
from datetime import datetime

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

# function to create a rule chain directly
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

#function to update rule chain metadata
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

#unction to get rule chain metadata
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

# Function to create a default root rule chain
def create_default_root_rule_chain(jwt_token, rule_chain_name):
    url = f"{THINGSBOARD_URL}/api/ruleChain/device/default"
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }
    payload = {
        "name": rule_chain_name
    }

    print(f"Creating default root rule chain with name: {rule_chain_name}")

    try:
        response = requests.post(url, headers=headers, json=payload)
        print(f"Response status: {response.status_code}")
        print(f"Response content: {response.text}")

        if response.status_code == 200:
            print("Success! Default root rule chain created successfully.")
            return response.json()
        else:
            print(f"Failed to create default root rule chain: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Exception occurred: {str(e)}")

    return None

# define to set a rule chain as the root rule chain with;
def set_root_rule_chain(jwt_token, rule_chain_id):
    url = f"{THINGSBOARD_URL}/api/ruleChain/{rule_chain_id}/root"
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }

    print(f"Setting rule chain {rule_chain_id} as the root rule chain.")

    try:
        response = requests.post(url, headers=headers)
        print(f"Response status: {response.status_code}")
        print(f"Response content: {response.text}")

        if response.status_code == 200:
            print("Success! Rule chain set as root successfully.")
            return response.json()
        else:
            print(f"Failed to set rule chain as root: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Exception occurred: {str(e)}")

    return None

# retriaval rule chain through a forwarding node to the root rule chain metadata [save time serie data linker]
def add_forwarding_node(metadata, custom_rule_chain_id):
    current_time = int(datetime.now().timestamp() * 1000)

    forwarding_node = {
        "type": "org.thingsboard.rule.engine.flow.TbRuleChainInputNode",
        "name": "Check if temp is above 28",
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

    # sdding  the forwarding node to the nodes list
    metadata["nodes"].append(forwarding_node)

    #  connection frorm the "Save Timeseries" node to the new forwarding node
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

#  metadata for the rule chain and defining inside node
def build_rule_chain_metadata(rule_chain_id):
    current_time = int(datetime.now().timestamp() * 1000)

    nodes = [
        {
            "type": "org.thingsboard.rule.engine.filter.TbJsFilterNode",
            "name": "Temperature Filter",
            "configuration": {
                "jsScript": "return msg.temperature > 28;"
            },
            "additionalInfo": {
                "layoutX": 260,
                "layoutY": 151,
                "description": "Checks if temperature exceeds 28"
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
                    // Remove prevAlarmDetails from metadata
                    delete metadata.prevAlarmDetails;
                    // Now metadata is the same as it comes IN this rule node
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
                    // Remove prevAlarmDetails from metadata
                    delete metadata.prevAlarmDetails;
                    // Now metadata is the same as it comes IN this rule node
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

# this is the main function
def main():
    jwt_token = get_jwt_token()
    if not jwt_token:
        print("Authentication failed. Exiting.")
        return

    # build and create the rule chain
    rule_chain_data = build_temperature_rule_chain()
    created_rule_chain = create_rule_chain(jwt_token, rule_chain_data)

    if created_rule_chain:
        rule_chain_id = created_rule_chain.get("id", {}).get("id")
        if rule_chain_id:
            # Update metadata for the rule chain
            metadata = build_rule_chain_metadata(rule_chain_id)
            update_rule_chain_metadata(jwt_token, rule_chain_id, metadata)

            # Define the name for the new root rule chain
            root_rule_chain_name = "Custom Root Rule Chain"

            # Create the default root rule chain
            created_root_rule_chain = create_default_root_rule_chain(jwt_token, root_rule_chain_name)

            if created_root_rule_chain:
                root_rule_chain_id = created_root_rule_chain.get("id", {}).get("id")
                if root_rule_chain_id:
                    # Get the existing metadata for the root rule chain
                    root_metadata = get_rule_chain_metadata(jwt_token, root_rule_chain_id)
                    if root_metadata:
                        # Add the forwarding node to the root rule chain metadata
                        updated_root_metadata = add_forwarding_node(root_metadata, rule_chain_id)

                        # Update the root rule chain metadata
                        update_rule_chain_metadata(jwt_token, root_rule_chain_id, updated_root_metadata)

                        # Set the root rule chain
                        set_root_rule_chain(jwt_token, root_rule_chain_id)

                        #debugging wholestically
                    else:
                        print("Failed to retrieve root rule chain metadata.")
                else:
                    print("Could not extract root rule chain ID from response.")
            else:
                print("Failed to create default root rule chain.")
        else:
            print("Could not extract rule chain ID from response.")
    else:
        print("Failed to create rule chain.")

if __name__ == "__main__":
    main()
