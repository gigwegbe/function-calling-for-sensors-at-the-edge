# """"
# Initial step. 
# To run this code, First make sure thingsboard container is running
# run python rulechain.py

# """"

#++++++++++++++++++++++++++++++++++++++========================================================================== problem with fetching/ remember metadata

# import requests
# import json
# import uuid
# from datetime import datetime

# # ThingsBoard settings
# THINGSBOARD_URL = "http://localhost:8080"
# USERNAME = "tenant@thingsboard.org"
# PASSWORD = "tenant"

# # Function to get JWT token
# def get_jwt_token():
#     url = f"{THINGSBOARD_URL}/api/auth/login"
#     payload = {
#         "username": USERNAME,
#         "password": PASSWORD
#     }
#     response = requests.post(url, json=payload)
#     if response.status_code == 200:
#         return response.json().get("token")
#     else:
#         print("Failed to authenticate:", response.text)
#         return None

# # Function to create a UUID
# def generate_uuid():
#     return str(uuid.uuid4())

# # Function to create a rule chain directly
# def create_rule_chain(jwt_token, rule_chain_data):
#     url = f"{THINGSBOARD_URL}/api/ruleChain"
    
#     headers = {
#         "Content-Type": "application/json",
#         "X-Authorization": f"Bearer {jwt_token}"
#     }
    
#     try:
#         response = requests.post(url, headers=headers, json=rule_chain_data)
#         print(f"Response status: {response.status_code}")
#         print(f"Response content: {response.text}")
        
#         if response.status_code == 200:
#             print("Success! Rule chain created successfully.")
#             return response.json()
#         else:
#             print(f"Failed to create rule chain: {response.status_code}")
#             print(response.text)
#     except Exception as e:
#         print(f"Exception occurred: {str(e)}")
    
#     return None

# # Create rule chain with nodes for temperature monitoring
# def build_temperature_rule_chain():
#     # Generate filter node ID - we'll use this as the first rule node
#     filter_node_id = generate_uuid()
    
#     # Create rule chain object
#     rule_chain = {
#         "name": "Temperature Alert Rule Chain",
#         "type": "CORE",
#         "firstRuleNodeId": {
#             "id": filter_node_id,
#             "entityType": "RULE_NODE"
#         },
#         "root": False,
#         "debugMode": False,
#         "configuration": {},
#         "additionalInfo": {}
#     }
    
#     return rule_chain, filter_node_id

# # Create metadata separately
# def build_rule_chain_metadata(rule_chain_id, first_node_id):
#     # Generate node IDs for other nodes
#     create_alarm_node_id = generate_uuid()
#     clear_alarm_node_id = generate_uuid()
    
#     # Current timestamp in milliseconds
#     current_time = int(datetime.now().timestamp() * 1000)
    
#     # Create nodes array for metadata
#     nodes = [
#         {
#             "id": {
#                 "id": first_node_id,
#                 "entityType": "RULE_NODE"
#             },
#             "createdTime": current_time,
#             "ruleChainId": {
#                 "id": rule_chain_id,
#                 "entityType": "RULE_CHAIN"
#             },
#             "type": "org.thingsboard.rule.engine.filter.TbJsFilterNode",
#             "name": "Temperature Filter",
#             "debugMode": False,
#             "singletonMode": False,
#             "queueName": "",
#             "configuration": {
#                 "jsScript": "return msg.temperature > 28;"
#             },
#             "additionalInfo": {
#                 "layoutX": 260,
#                 "layoutY": 151,
#                 "description": "Checks if temperature exceeds 28"
#             }
#         },
#         {
#             "id": {
#                 "id": create_alarm_node_id,
#                 "entityType": "RULE_NODE"
#             },
#             "createdTime": current_time,
#             "ruleChainId": {
#                 "id": rule_chain_id,
#                 "entityType": "RULE_CHAIN"
#             },
#             "type": "org.thingsboard.rule.engine.action.TbCreateAlarmNode",
#             "name": "Create High Temp Alarm",
#             "debugMode": False,
#             "singletonMode": False,
#             "queueName": "",
#             "configuration": {
#                 "alarmType": "High Temperature",
#                 "alarmDetailsBuildJs": "var details = {}; details = metadata.deviceName + ' temperature is too high: ' + msg.temperature; return details;",
#                 "severity": "CRITICAL",
#                 "propagate": True,
#                 "useMessageAlarmData": False
#             },
#             "additionalInfo": {
#                 "layoutX": 400,
#                 "layoutY": 100
#             }
#         },
#         {
#             "id": {
#                 "id": clear_alarm_node_id,
#                 "entityType": "RULE_NODE"
#             },
#             "createdTime": current_time,
#             "ruleChainId": {
#                 "id": rule_chain_id,
#                 "entityType": "RULE_CHAIN"
#             },
#             "type": "org.thingsboard.rule.engine.action.TbClearAlarmNode",
#             "name": "Clear High Temp Alarm",
#             "debugMode": False,
#             "singletonMode": False,
#             "queueName": "",
#             "configuration": {
#                 "alarmType": "High Temperature",
#                 "alarmDetailsBuildJs": "var details = {}; details = metadata.deviceName + ' temperature is back to normal: ' + msg.temperature; return details;"
#             },
#             "additionalInfo": {
#                 "layoutX": 400,
#                 "layoutY": 250
#             }
#         }
#     ]
    
#     # Create connections
#     connections = [
#         {
#             "fromIndex": 0,
#             "toIndex": 1,
#             "type": "True"
#         },
#         {
#             "fromIndex": 0,
#             "toIndex": 2,
#             "type": "False"
#         }
#     ]
    
#     # Assemble metadata
#     metadata = {
#         "ruleChainId": {
#             "id": rule_chain_id,
#             "entityType": "RULE_CHAIN"
#         },
#         "firstNodeIndex": 0,
#         "nodes": nodes,
#         "connections": connections,
#         "ruleChainConnections": []
#     }
    
#     return metadata

# # Function to save rule chain metadata
# def save_rule_chain_metadata(jwt_token, metadata):
#     url = f"{THINGSBOARD_URL}/api/ruleChain/metadata"
    
#     headers = {
#         "Content-Type": "application/json",
#         "X-Authorization": f"Bearer {jwt_token}"
#     }
    
#     # For debug purposes: print the metadata JSON
#     print("Sending metadata:")
#     print(json.dumps(metadata, indent=2))
    
#     try:
#         response = requests.post(url, headers=headers, json=metadata)
#         print(f"Metadata Response status: {response.status_code}")
#         print(f"Metadata Response content: {response.text}")
        
#         if response.status_code == 200:
#             print("Success! Rule chain metadata saved successfully.")
#             return response.json()
#         else:
#             print(f"Failed to save rule chain metadata: {response.status_code}")
#             print(response.text)
#     except Exception as e:
#         print(f"Exception occurred during metadata save: {str(e)}")
    
#     return None

# # Main function
# def main():
#     jwt_token = get_jwt_token()
#     if not jwt_token:
#         print("Authentication failed. Exiting.")
#         return
    
#     # First create the rule chain
#     rule_chain, first_node_id = build_temperature_rule_chain()
#     rule_chain_response = create_rule_chain(jwt_token, rule_chain)
    
#     if rule_chain_response:
#         # Get the rule chain ID from the response
#         rule_chain_id = rule_chain_response.get("id", {}).get("id")
#         if rule_chain_id:
#             # Build metadata with the rule chain ID and first node ID
#             metadata = build_rule_chain_metadata(rule_chain_id, first_node_id)
#             if metadata:
#                 save_rule_chain_metadata(jwt_token, metadata)
#             else:
#                 print("Failed to build metadata.")
#         else:
#             print("Could not extract rule chain ID from response.")
#     else:
#         print("Failed to create rule chain.")

# if __name__ == "__main__":
#     main()

#++++++++++++++++++++++++++++============================================================================================


# TO be able to create nodes inside chain rule I utilized the /api/ruleChain/metadata endpoint 
# to update the rule chain metadata, which includes nodes and connections:
# Create the Rule Chain: Use the /api/ruleChain endpoint to create the rule chain structure.
# Update Metadata: Use the /api/ruleChain/metadata endpoint to update the rule chain with nodes and connections.



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

# function to create a UUID dynamically
def generate_uuid():
    return str(uuid.uuid4())

#create a rule chain directly
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

#updateing  rule chain metadata {this is very neccessary as it defines node connections}
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

#rrule chain with nodes for temperature monitoring
def build_temperature_rule_chain():
    # define object
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

# creating metadata for the rule chain {patterns from Json files}
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

# defining main function
def main():
    jwt_token = get_jwt_token()
    if not jwt_token:
        print("Authentication failed. Exiting.")
        return

    #build and create the rule chain
    rule_chain_data = build_temperature_rule_chain()
    created_rule_chain = create_rule_chain(jwt_token, rule_chain_data)

    if created_rule_chain:
        rule_chain_id = created_rule_chain.get("id", {}).get("id")
        if rule_chain_id:
            #update metadata for the rule chain (important step)
            metadata = build_rule_chain_metadata(rule_chain_id)
            update_rule_chain_metadata(jwt_token, rule_chain_id, metadata)
        else:
            print("Could not extract rule chain ID from response.")
    else:
        print("Failed to create rule chain.")

if __name__ == "__main__":
    main()


#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++============================================== connecting to the root chain

# """"
# I was trying to configure  newly created rule chain as the root rule chain, you can use 
# the /api/ruleChain/{ruleChainId}/root endpoint. This endpoint allows you to set 
# a specific rule chain as the root rule chain, which will process messages from 
# all devices and entities by default. BUT this makes the created chain rule the root chain,
# it does not append it to the system root chain which is what is required
# """"


# import requests
# import json
# import uuid
# from datetime import datetime

# # ThingsBoard settings
# THINGSBOARD_URL = "http://localhost:8080"
# USERNAME = "tenant@thingsboard.org"
# PASSWORD = "tenant"

# # Function to get JWT token
# def get_jwt_token():
#     url = f"{THINGSBOARD_URL}/api/auth/login"
#     payload = {
#         "username": USERNAME,
#         "password": PASSWORD
#     }
#     print("Authenticating with ThingsBoard...")
#     response = requests.post(url, json=payload)
#     if response.status_code == 200:
#         print("Authentication successful.")
#         return response.json().get("token")
#     else:
#         print("Failed to authenticate:", response.text)
#         return None

# # function to create a UUID dynamically
# def generate_uuid():
#     return str(uuid.uuid4())

# #  create a rule chain directly
# def create_rule_chain(jwt_token, rule_chain_data):
#     url = f"{THINGSBOARD_URL}/api/ruleChain"

#     headers = {
#         "Content-Type": "application/json",
#         "X-Authorization": f"Bearer {jwt_token}"
#     }

#     print("Creating rule chain with the following data:")
#     print(json.dumps(rule_chain_data, indent=2))

#     try:
#         response = requests.post(url, headers=headers, json=rule_chain_data)
#         print(f"Response status: {response.status_code}")
#         print(f"Response content: {response.text}")

#         if response.status_code == 200:
#             print("Success! Rule chain created successfully.")
#             return response.json()
#         else:
#             print(f"Failed to create rule chain: {response.status_code}")
#             print(response.text)
#     except Exception as e:
#         print(f"Exception occurred: {str(e)}")

#     return None

# #updateing  rule chain metadata {this is very neccessary as it defines node connections}
# def update_rule_chain_metadata(jwt_token, rule_chain_id, metadata):
#     url = f"{THINGSBOARD_URL}/api/ruleChain/metadata"

#     headers = {
#         "Content-Type": "application/json",
#         "X-Authorization": f"Bearer {jwt_token}"
#     }

#     print(f"Updating metadata for rule chain {rule_chain_id} with data:")
#     print(json.dumps(metadata, indent=2))

#     try:
#         response = requests.post(url, headers=headers, json=metadata)
#         print(f"Response status: {response.status_code}")
#         print(f"Response content: {response.text}")

#         if response.status_code == 200:
#             print("Success! Metadata updated successfully.")
#             return response.json()
#         else:
#             print(f"Failed to update metadata: {response.status_code}")
#             print(response.text)
#     except Exception as e:
#         print(f"Exception occurred: {str(e)}")

#     return None

# #set a rule chain as the root rule chain
# def set_root_rule_chain(jwt_token, rule_chain_id):
#     url = f"{THINGSBOARD_URL}/api/ruleChain/{rule_chain_id}/root"

#     headers = {
#         "Content-Type": "application/json",
#         "X-Authorization": f"Bearer {jwt_token}"
#     }

#     print(f"Setting rule chain {rule_chain_id} as the root rule chain.")

#     try:
#         response = requests.post(url, headers=headers)
#         print(f"Response status: {response.status_code}")
#         print(f"Response content: {response.text}")

#         if response.status_code == 200:
#             print("Success! Rule chain set as root successfully.")
#             return response.json()
#         else:
#             print(f"Failed to set rule chain as root: {response.status_code}")
#             print(response.text)
#     except Exception as e:
#         print(f"Exception occurred: {str(e)}")

#     return None

# #rrule chain with nodes for temperature monitoring
# def build_temperature_rule_chain():
#     # define object
#     rule_chain_data = {
#         "name": "Alert Rule Chain",  
#         "type": "CORE",
#         "root": False,
#         "debugMode": False,
#         "tenantId": {
#             "id": "337c4a58-be4d-45d6-9daf-f2e08991f0fd",
#             "entityType": "TENANT"
#         },
#         "configuration": {},
#         "additionalInfo": {}
#     }

#     return rule_chain_data

# # kreating metadata for the rule chain {patterns from Json files}
# def build_rule_chain_metadata(rule_chain_id):
#     current_time = int(datetime.now().timestamp() * 1000)

#     nodes = [
#         {
#             "type": "org.thingsboard.rule.engine.filter.TbJsFilterNode",
#             "name": "Temperature Filter",
#             "configuration": {
#                 "jsScript": "return msg.temperature > 28;"
#             },
#             "additionalInfo": {
#                 "layoutX": 260,
#                 "layoutY": 151,
#                 "description": "Checks if temperature exceeds 28"
#             }
#         },
#         {
#             "type": "org.thingsboard.rule.engine.action.TbCreateAlarmNode",
#             "name": "Create High Temp Alarm",
#             "configuration": {
#                 "alarmType": "High Temperature",
#                 "alarmDetailsBuildJs": "var details = {}; details = metadata.deviceName + ' temperature is too high: ' + msg.temperature; return details;",
#                 "severity": "CRITICAL",
#                 "propagate": True,
#                 "useMessageAlarmData": False
#             },
#             "additionalInfo": {
#                 "layoutX": 400,
#                 "layoutY": 100
#             }
#         },
#         {
#             "type": "org.thingsboard.rule.engine.action.TbClearAlarmNode",
#             "name": "Clear High Temp Alarm",
#             "configuration": {
#                 "alarmType": "High Temperature",
#                 "alarmDetailsBuildJs": "var details = {}; details = metadata.deviceName + ' temperature is back to normal: ' + msg.temperature; return details;"
#             },
#             "additionalInfo": {
#                 "layoutX": 400,
#                 "layoutY": 250
#             }
#         }
#     ]

#     connections = [
#         {
#             "fromIndex": 0,
#             "toIndex": 1,
#             "type": "True"
#         },
#         {
#             "fromIndex": 0,
#             "toIndex": 2,
#             "type": "False"
#         }
#     ]

#     metadata = {
#         "ruleChainId": {
#             "id": rule_chain_id,
#             "entityType": "RULE_CHAIN"
#         },
#         "version": 1,
#         "firstNodeIndex": 0,
#         "nodes": nodes,
#         "connections": connections,
#         "ruleChainConnections": []
#     }

#     return metadata

# # defining main function
# def main():
#     jwt_token = get_jwt_token()
#     if not jwt_token:
#         print("Authentication failed. Exiting.")
#         return

#     #build and create the rule chain
#     rule_chain_data = build_temperature_rule_chain()
#     created_rule_chain = create_rule_chain(jwt_token, rule_chain_data)

#     if created_rule_chain:
#         rule_chain_id = created_rule_chain.get("id", {}).get("id")
#         if rule_chain_id:
#             #update metadata for the rule chain (important step)
#             metadata = build_rule_chain_metadata(rule_chain_id)
#             update_rule_chain_metadata(jwt_token, rule_chain_id, metadata)

#             # Setting the rule chain as the root rule chain
#             set_root_rule_chain(jwt_token, rule_chain_id)
#         else:
#             print("Could not extract rule chain ID from response.")
#     else:
#         print("Failed to create rule chain.")

# if __name__ == "__main__":
#     main()

