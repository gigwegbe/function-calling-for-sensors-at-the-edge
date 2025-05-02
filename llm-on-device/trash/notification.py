from tb_rest_client.rest_client_ce import RestClientCE

import requests
import json  # Import the json module

BASE_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"

THINGSBOARD_URL = "http://localhost:8080"

def authenticate():
    auth_url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {'username': USERNAME, 'password': PASSWORD}
    try:
        response = requests.post(auth_url, json=payload)
        response.raise_for_status()
        return response.json()['token']
    except requests.exceptions.RequestException as e:
        print(f"Error during authentication: {e}")
        return None

def get_user_notifications(access_token, page_size=100, page=0, unread_only=False):
    headers = {
        "X-Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"{THINGSBOARD_URL}/api/notification/inbox"
    payload = {
        "pageSize": page_size,
        "page": page,
        "unreadOnly": unread_only
    }
    try:
        response = requests.post(url, headers=headers, json=payload)  # **NOW USING POST**
        response.raise_for_status()
        return response.json().get('data', [])
    except requests.exceptions.RequestException as e:
        print(f"Error retrieving notifications: {e}")
        return []

def get_all_tenant_admins(access_token, page_size=100):
    headers = {
        "X-Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"{THINGSBOARD_URL}/api/tenant/users"  # Assuming this is correct after doc check
    all_admins = []
    page = 0
    while True:
        params = {'pageSize': page_size, 'page': page}
        try:
            response = requests.get(url, headers=headers, params=params)  # Keep GET for now, but CHECK DOCS
            response.raise_for_status()
            data = response.json().get('data', [])
            if not data:
                break
            all_admins.extend(data)
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"Error fetching tenant admins (page {page}): {e}")
            break
    return all_admins

def get_all_customers(access_token, page_size=100):
    headers = {
        "X-Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"{THINGSBOARD_URL}/api/customers"  # Assuming this is correct after doc check
    all_customers = []
    page = 0
    while True:
        params = {'pageSize': page_size, 'page': page}
        try:
            response = requests.get(url, headers=headers, params=params)  # Keep GET for now, but CHECK DOCS
            response.raise_for_status()
            data = response.json().get('data', [])
            if not data:
                break
            all_customers.extend(data)
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"Error fetching customers (page {page}): {e}")
            break
    return all_customers

def get_customer_users(access_token, customer_id, page_size=100):
    headers = {
        "X-Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"{THINGSBOARD_URL}/api/customer/{customer_id}/users"  # Assuming this is correct after doc check
    all_users = []
    page = 0
    while True:
        params = {'pageSize': page_size, 'page': page}
        try:
            response = requests.get(url, headers=headers, params=params)  # Keep GET for now, but CHECK DOCS
            response.raise_for_status()
            data = response.json().get('data', [])
            if not data:
                break
            all_users.extend(data)
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"Error fetching customer users (page {page}) for customer {customer_id}: {e}")
            break
    return all_users

if __name__ == "__main__":
    token = authenticate()
    if token:
        all_notifications = []

        # Get all tenant administrators and their notifications
        tenant_admins = get_all_tenant_admins(token)
        if tenant_admins:
            for admin in tenant_admins:
                user_id = admin['id']['id']
                notifications = get_user_notifications(token, unread_only=False)  # Get all notifications for the authenticated user
                print(f"Retrieved {len(notifications)} notifications for Tenant Admin: {admin['email']}")
                all_notifications.extend(notifications)

        # Get all customers and their users' notifications
        customers = get_all_customers(token)
        if customers:
            for customer in customers:
                customer_users = get_customer_users(token, customer['id']['id'])
                if customer_users:
                    for user in customer_users:
                        # Assuming you want notifications for each customer user.
                        # You might need a way to associate a platform user ID with a customer user ID
                        # or if the notifications are tied to the authenticated user's scope.
                        # The get_user_notifications endpoint typically retrieves notifications for the logged-in user.
                        # If you need notifications for *other* users, ThingsBoard's API might have different
                        # mechanisms (e.g., specific admin APIs or impersonation).
                        notifications = get_user_notifications(token, unread_only=False) # Get all notifications for the authenticated user
                        print(f"Retrieved {len(notifications)} notifications for Customer User: {user['email']} (Customer: {customer['title']})")
                        all_notifications.extend(notifications)

        print(f"\nTotal notifications retrieved: {len(all_notifications)}")
        # Process the all_notifications list
    else:
        print("Authentication failed. Cannot retrieve notifications.")