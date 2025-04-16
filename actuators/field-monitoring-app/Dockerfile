# Use the official Python image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY app .

# Expose the port FastAPI will run on
EXPOSE 8060

# Install SQLite tools for debugging
RUN apt-get update && apt-get install -y sqlite3

# Create data directory and ensure database is removed
RUN mkdir -p /app/data && \
    rm -f /app/farm_control.db && \
    rm -f /app/data/farm_control.db && \
    touch /app/farm_control.db && \
    chmod 666 /app/farm_control.db

# Add an initialization script
COPY init.sh /app/
RUN chmod +x /app/init.sh

# Use the init script as entrypoint
ENTRYPOINT ["/app/init.sh"]
CMD ["python3", "main.py", "--import", "data/farm_model.json"]