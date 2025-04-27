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

# Function to build the rule chain data
def build_temperature_rule_chain(sensor_field, tenant_id):
    rule_chain_data = {
        "name": f"{sensor_field.capitalize()} Monitoring Rule Chain",
        "type": "CORE",
        "root": False,
        "debugMode": False,
        "tenantId": {
            "id": tenant_id,
            "entityType": "TENANT"
        },
        "configuration": {},
        "additionalInfo": {}
    }
    return rule_chain_data

# Function to build the rule chain metadata
def build_rule_chain_metadata(rule_chain_id, sensor_field, threshold_value):
    """Build the metadata for the rule chain with appropriate nodes"""
    js_filter_script = f"return msg.{sensor_field} > {threshold_value};"

    nodes = [
        {
            "type": "org.thingsboard.rule.engine.filter.TbJsFilterNode",
            "name": f"{sensor_field.capitalize()} Filter",
            "configuration": {
                "jsScript": js_filter_script
            },
            "additionalInfo": {
                "layoutX": 260,
                "layoutY": 151,
                "description": f"Checks if {sensor_field} exceeds {threshold_value}"
            }
        },
        {
            "type": "org.thingsboard.rule.engine.action.TbCreateAlarmNode",
            "name": f"Create High {sensor_field.capitalize()} Alarm",
            "configuration": {
                "alarmType": f"High {sensor_field.capitalize()}",
                "alarmDetailsBuildJs": f"""
                var details = {{}};
                if (metadata.prevAlarmDetails) {{
                    details = JSON.parse(metadata.prevAlarmDetails);
                    // Remove prevAlarmDetails from metadata
                    delete metadata.prevAlarmDetails;
                    // Now metadata is the same as it comes IN this rule node
                }}
                details.sensor = "{sensor_field}";
                details.threshold = {threshold_value};
                details.value = msg.{sensor_field};
                details.timestamp = new Date().toISOString();
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
            "name": f"Clear High {sensor_field.capitalize()} Alarm",
            "configuration": {
                "alarmType": f"High {sensor_field.capitalize()}",
                "alarmDetailsBuildJs": f"""
                var details = {{}};
                if (metadata.prevAlarmDetails) {{
                    details = JSON.parse(metadata.prevAlarmDetails);
                    // Remove prevAlarmDetails from metadata
                    delete metadata.prevAlarmDetails;
                    // Now metadata is the same as it comes IN this rule node
                }}
                return details;
                """,
            },
            "additionalInfo": {
                "layoutX": 400,
                "layoutY": 250
            }
        },
        {
            "type": "org.thingsboard.rule.engine.transform.TbTransformMsgNode",
            "name": "transform",
            "configuration": {
                "scriptLang": "JS",
                "jsScript": """
                var newMsg = {
                  notificationId: metadata.notificationId || 'N/A',
                  type: metadata.notificationType || 'ALARM',
                  subject: metadata.notificationSubject || 'No subject',
                  text: metadata.notificationText || msg,
                  originatorId: metadata.originatorId,
                  originatorType: metadata.originatorType,
                  severity: metadata.severity || 'CRITICAL',
                  timestamp: Date.now(),
                  originalMessage: msg
                };

                // Set content type header if not already set
                metadata.contentType = 'application/json';

                return {msg: newMsg, metadata: metadata, msgType: msgType};
                """
            },
            "additionalInfo": {
                "description": "",
                "layoutX": 525,
                "layoutY": 219
            }
        }
        ,
        {
            "type": "org.thingsboard.rule.engine.rest.TbRestApiCallNode",
            "name": "Send to Flask Webhook",
            "configuration": {
                "restEndpointUrlPattern": "http://localhost:5000/thingsboard/notifications",
                "requestMethod": "POST",
                "useSimpleClientHttpFactory": True,
                "parseToPlainText": False,
                "ignoreRequestBody": False,
                "enableProxy": False,
                "useSystemProxyProperties": False,
                "headers": {
                    "Content-Type": "application/json"
                },
                "credentials": {
                    "type": "anonymous"
                },
                "maxInMemoryBufferSizeInKb": 256,
                "body": "${metadata.prevAlarmDetails}"
            },
            "additionalInfo": {
                "layoutX": 600,
                "layoutY": 150
            }
        }
    ]

    connections = [
        {"fromIndex": 0, "toIndex": 1, "type": "True"},
        {"fromIndex": 0, "toIndex": 2, "type": "False"},
        {"fromIndex": 1, "toIndex": 3, "type": "Created"},
        {"fromIndex": 3, "toIndex": 4, "type": "Success"}
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


# Main function
def main():
    # Step 1: Get user input
    print("Available sensors: soil_moisture, soil_temperature, soil_electroconductivity, humidity")
    sensor_field = input("Enter the sensor field (e.g., soil_moisture): ").strip().lower().replace(" ", "_")
    threshold_value = float(input("Enter the threshold value: "))
    tenant_id = input("Enter your tenant ID: ").strip()

    jwt_token = get_jwt_token()
    if not jwt_token:
        print("Authentication failed. Exiting.")
        return

    # Step 2: Build and create the custom rule chain
    rule_chain_data = build_temperature_rule_chain(sensor_field, tenant_id)
    created_rule_chain = create_rule_chain(jwt_token, rule_chain_data)

    if created_rule_chain:
        custom_rule_chain_id = created_rule_chain.get("id", {}).get("id")
        if custom_rule_chain_id:
            # Update metadata for the custom rule chain
            metadata = build_rule_chain_metadata(custom_rule_chain_id, sensor_field, threshold_value)
            update_rule_chain_metadata(jwt_token, custom_rule_chain_id, metadata)

            # Get the existing metadata for the hardcoded root rule chain
            root_metadata = get_rule_chain_metadata(jwt_token, ROOT_RULE_CHAIN_ID)
            if root_metadata:
                # Add the forwarding node to the root rule chain metadata
                updated_root_metadata = add_forwarding_node(root_metadata, custom_rule_chain_id)

                # Update the root rule chain metadata
                update_rule_chain_metadata(jwt_token, ROOT_RULE_CHAIN_ID, updated_root_metadata)
            else:
                print("Failed to retrieve root rule chain metadata.")
        else:
            print("Could not extract custom rule chain ID from response.")
    else:
        print("Failed to create custom rule chain.")

if __name__ == "__main__":
    main()