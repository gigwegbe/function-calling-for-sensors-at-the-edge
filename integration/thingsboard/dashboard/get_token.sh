#!/bin/bash

THINGSBOARD_URL="http://localhost:8080"
USERNAME="tenant@thingsboard.org"
PASSWORD="tenant"

# Fetch the token and extract only the "token" field
curl -s -X POST "$THINGSBOARD_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$USERNAME\", \"password\":\"$PASSWORD\"}" | grep -o '"token":"[^"]*"' | awk -F':' '{print $2}' | tr -d '"'