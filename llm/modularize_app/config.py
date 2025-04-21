# config.py
import os
from dotenv import load_dotenv

load_dotenv()

THINGSBOARD_URL = os.environ.get("THINGSBOARD_URL", "http://localhost:8080")
USERNAME = os.environ.get("THINGSBOARD_USERNAME", "tenant@thingsboard.org")
PASSWORD = os.environ.get("THINGSBOARD_PASSWORD", "tenant")
DASHBOARD_ID = os.environ.get("THINGSBOARD_DASHBOARD_ID", "http://localhost:8080/tenants")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "thingsboard")
DB_USER = os.environ.get("DB_USER", "thingsboard")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

OPENAI_API_KEY = os.getenv('OPENAI_PROJECT_API_KEY')
OPENWEATHERMAP_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')

FARM_METADATA_PATH = "/Users/george/Documents/final_push/function-calling-for-sensors-at-the-edge/farm_model_small_v2.json"