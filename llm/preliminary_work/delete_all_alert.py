from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import Runnable
from langchain.chains.openai_functions import create_openai_fn_runnable
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import os
import requests
from dotenv import load_dotenv
from langgraph.prebuilt import create_react_agent
from datetime import datetime, timedelta
from time import time
import pytz

import plotly.graph_objects as go
from langchain_core.tools import tool
from plotly.subplots import make_subplots
from langgraph_supervisor import create_supervisor

THINGSBOARD_URL = "http://localhost:8080"
# --- Configuration ---
BASE_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"

import requests
import json

# API_TOKEN = "your_api_token"
ROOT_CHAIN_NAME = "b92f3e10-ed12-11ef-9b10-65e5e6a48f42"



# Authenticate with ThingsBoard
def authenticate():
    auth_url = f"{BASE_URL}/api/auth/login"
    payload = {'username': USERNAME, 'password': PASSWORD}
    response = requests.post(auth_url, json=payload)
    response.raise_for_status()
    return response.json()['token']

API_TOKEN = authenticate()
print(API_TOKEN)


# Set the headers for the API requests
headers = {
    'Content-Type': 'application/json',
    'X-Authorization': f'Bearer {API_TOKEN}'
}

# Function to get the list of rule chains
def get_rule_chains():
    url = f"{BASE_URL}/api/ruleChains"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print("Error fetching rule chains:", response.status_code)
        return []

# Function to delete a rule chain by its ID
def delete_rule_chain(rule_chain_id):
    url = f"{BASE_URL}/api/ruleChains/{rule_chain_id}"
    response = requests.delete(url, headers=headers)
    if response.status_code == 200:
        print(f"Deleted rule chain with ID: {rule_chain_id}")
    else:
        print(f"Error deleting rule chain {rule_chain_id}: {response.status_code}")

# Get all rule chains and delete all except the root
rule_chains = get_rule_chains()
if rule_chains:
    for chain in rule_chains:
        if chain['name'] != ROOT_CHAIN_NAME:
            delete_rule_chain(chain['id'])
