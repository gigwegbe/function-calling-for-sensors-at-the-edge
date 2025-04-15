#!/bin/bash

# Ensure get_token.sh is executable
chmod +x get_token.sh

# Step 1: Run get_token.sh and capture the token
echo "Fetching ThingsBoard API token..."
ACCESS_TOKEN=$(bash get_token.sh)

# Check if the token was successfully retrieved
if [ -z "$ACCESS_TOKEN" ]; then
    echo "Failed to retrieve the API token. Exiting."
    exit 1
fi
echo "Token retrieved: $ACCESS_TOKEN"

# Step 2: Run devices_import.py with the token
echo "Importing devices..."
python3 devices_import.py "$ACCESS_TOKEN"