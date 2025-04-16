#!/bin/bash

# Remove existing database if it exists
rm -f /app/farm_control.db
rm -f /app/data/farm_control.db

# Create empty database file with proper permissions
touch /app/farm_control.db
chmod 666 /app/farm_control.db

# Execute the main application
exec "$@"