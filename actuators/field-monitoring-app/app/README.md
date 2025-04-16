# Field Monitoring Application


## Setup Instructions

### Option 1: Run Locally

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd field-monitoring-app
   ```

2. **Create a virtual environment** (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**:
   ```bash
   python app/main.py --import data/farm_model.json
   ```

### Option 2: Run with Docker

1. **Build the Docker image**:
   ```bash
   docker build -t field-monitoring-app .
   ```

2. **Run the Docker container**:
   ```bash
   docker run -p 8060:8060 field-monitoring-app
   ```

3. The application will be available at `http://localhost:8060`.

### Option 3: Use Docker Compose

1. **Run the application with Docker Compose**:
   ```bash
   docker-compose up -d --build
   ```

2. The application will be available at `http://localhost:8060` in docker envernoment but `http://localhost:8090` out of docker env

3. Accessing the API documentation, go to `host:port/docs`
---
