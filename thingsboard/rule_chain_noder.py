# import requests
# import json

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

# # Function to create a rule chain
# def create_rule_chain(jwt_token, rule_chain_name):
#     url = f"{THINGSBOARD_URL}/api/ruleChain"
#     headers = {
#         "Content-Type": "application/json",
#         "X-Authorization": f"Bearer {jwt_token}"
#     }
#     payload = {
#         "name": rule_chain_name,
#         "firstRuleNodeId": None,
#         "root": False,
#         "debugMode": False,
#         "configuration": None
#     }
#     response = requests.post(url, headers=headers, json=payload)
#     if response.status_code == 200:
#         return response.json()
#     else:
#         print("Failed to create rule chain:", response.text)
#         return None

# # Function to create a rule node within a rule chain
# def create_rule_node(jwt_token, rule_chain_id, node_config):
#     url = f"{THINGSBOARD_URL}/api/ruleChain/{rule_chain_id}/ruleNode"
#     headers = {
#         "Content-Type": "application/json",
#         "X-Authorization": f"Bearer {jwt_token}"
#     }
#     payload = {
#         "ruleChainId": rule_chain_id,
#         "type": node_config["type"],
#         "name": node_config["name"],
#         "debugMode": False,
#         "configuration": node_config["configuration"]
#     }
#     response = requests.post(url, headers=headers, json=payload)
#     if response.status_code == 200:
#         return response.json()
#     else:
#         print("Failed to create rule node:", response.text)
#         return None

# # Function to connect rule nodes
# def connect_rule_nodes(jwt_token, rule_chain_id, from_node_id, to_node_id, relation_type):
#     url = f"{THINGSBOARD_URL}/api/ruleChain/{rule_chain_id}/ruleNode/{from_node_id}/connection/{relation_type}"
#     headers = {
#         "Content-Type": "application/json",
#         "X-Authorization": f"Bearer {jwt_token}"
#     }
#     payload = {
#         "toNodeId": to_node_id
#     }
#     response = requests.post(url, headers=headers, json=payload)
#     if response.status_code == 200:
#         return response.json()
#     else:
#         print("Failed to connect rule nodes:", response.text)
#         return None

# # Main function
# def main():
#     jwt_token = get_jwt_token()
#     if not jwt_token:
#         print("Authentication failed. Exiting.")
#         return

#     # Create a new rule chain
#     rule_chain_name = "Temperature Sensor Rule Chain"
#     rule_chain = create_rule_chain(jwt_token, rule_chain_name)
#     if not rule_chain:
#         print("Failed to create rule chain. Exiting.")
#         return

#     rule_chain_id = rule_chain["id"]["id"]

#     # Create Emergency Alarm rule node
#     emergency_alarm_config = {
#         "type": "org.thingsboard.rule.engine.filter.TbMsgTypeFilter",
#         "name": "Emergency Alarm",
#         "configuration": {
#             "script": "return msg.temperature > 10;"
#         }
#     }
#     emergency_alarm_node = create_rule_node(jwt_token, rule_chain_id, emergency_alarm_config)
#     if not emergency_alarm_node:
#         print("Failed to create Emergency Alarm node. Exiting.")
#         return

#     # Create Emergency Trigger rule node
#     emergency_trigger_config = {
#         "type": "org.thingsboard.rule.engine.action.TbLogNode",
#         "name": "Emergency Trigger",
#         "configuration": {
#             "jsScript": """
#             var details = {};
#             details = metadata.deviceName + ' temperature change to HI';
#             return details;
#             """
#         }
#     }
#     emergency_trigger_node = create_rule_node(jwt_token, rule_chain_id, emergency_trigger_config)
#     if not emergency_trigger_node:
#         print("Failed to create Emergency Trigger node. Exiting.")
#         return

#     # Create Clear Emergency Trigger rule node
#     clear_emergency_trigger_config = {
#         "type": "org.thingsboard.rule.engine.action.TbLogNode",
#         "name": "Clear Emergency Trigger",
#         "configuration": {
#             "jsScript": """
#             var details = {};
#             if (metadata.prevAlarmDetails != null) {
#                 details = JSON.parse(metadata.prevAlarmDetails);
#             }
#             return details;
#             """
#         }
#     }
#     clear_emergency_trigger_node = create_rule_node(jwt_token, rule_chain_id, clear_emergency_trigger_config)
#     if not clear_emergency_trigger_node:
#         print("Failed to create Clear Emergency Trigger node. Exiting.")
#         return

#     # Connect Emergency Alarm to Emergency Trigger
#     connect_rule_nodes(jwt_token, rule_chain_id, emergency_alarm_node["id"]["id"], emergency_trigger_node["id"]["id"], "True")

#     # Connect Emergency Alarm to Clear Emergency Trigger
#     connect_rule_nodes(jwt_token, rule_chain_id, emergency_alarm_node["id"]["id"], clear_emergency_trigger_node["id"]["id"], "False")

#     print("Rule chain and nodes created successfully.")

# if __name__ == "__main__":
#     main()