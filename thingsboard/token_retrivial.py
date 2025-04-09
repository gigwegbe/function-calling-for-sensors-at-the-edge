import requests

# ThingsBoard settings
THINGSBOARD_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"

# Function to get JWT token
def get_jwt_token():
    url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {
        "username": USERNAME,
        "password": PASSWORD
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json().get("token")
    else:
        print("Failed to authenticate:", response.text)
        return None

# Main function
def main():
    jwt_token = get_jwt_token()
    if jwt_token:
        print("JWT Token:", jwt_token)
    else:
        print("Failed to get JWT token.")

if __name__ == "__main__":
    main()