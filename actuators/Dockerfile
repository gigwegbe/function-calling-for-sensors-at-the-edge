FROM python:3.9-slim

WORKDIR /app
COPY create_actuator.py .
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python3", "create_actuator.py"]