#!/bin/bash

# Ensure get_token.sh is executable
chmod +x get_token.sh

# Step 1: Fetch the access token using get_token.sh
ACCESS_TOKEN=$(bash get_token.sh)

# Check if the token was successfully retrieved
if [ -z "$ACCESS_TOKEN" ]; then
    echo "Failed to retrieve the API token. Exiting."
    exit 1
fi
echo "Token retrieved: $ACCESS_TOKEN"

# Step 2: Use the token in the GET request
curl -X GET "http://localhost:8080/api/tenant/devices?pageSize=1000&page=0" \
  -H "Content-Type: application/json" \
  -H "X-Authorization: Bearer $ACCESS_TOKEN" \
  -o devices.json

echo "Devices exported to devices.json."