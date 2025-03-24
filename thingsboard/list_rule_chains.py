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

# Function to get user details
def get_user_details(jwt_token):
    url = f"{THINGSBOARD_URL}/api/auth/user"
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print("Failed to get user details:", response.text)
        return None

# Main function
def main():
    jwt_token = get_jwt_token()
    if not jwt_token:
        print("Authentication failed. Exiting.")
        return

    user_details = get_user_details(jwt_token)
    if user_details:
        print("User Details:")
        print(f"Username: {user_details['name']}")
        print(f"Email: {user_details['email']}")
        print(f"Authority: {user_details['authority']}")
    else:
        print("Failed to retrieve user details.")

if __name__ == "__main__":
    main()