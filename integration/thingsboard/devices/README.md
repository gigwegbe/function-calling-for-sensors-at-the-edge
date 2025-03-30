# Exporting Thingsboard devices 

Export via the Web UI using the Export Button does not work for the Community Edition of Thingsboard.

## Export Devices via REST API (Bulk Export)

If you have many devices, you can use the REST API to export them.

If you have tenant administrator access, you can export all devices using the REST API.

Steps to Export Devices via API:

1️⃣ Get an authentication token using your ThingsBoard username/password:

```bash
curl -X POST "http://localhost:8080/api/auth/login" \
-H "Content-Type: application/json" \
-d '{"username":"your_username", "password":"your_password"}'
```
username could be tenant@thingsboard.org; password would be tenant

This will return a response like:
```json
{
  "token": "YOUR_ACCESS_TOKEN"
}
```
Copy the "token" value for the next step.

2️⃣ Fetch and Export Devices to JSON:

Steps:
- Get an access token (JWT) using your sysadmin or tenant credentials.
- Use the following cURL command to export all devices:

```bash
curl -X GET "http://localhost:8080/api/tenant/devices?pageSize=1000&page=0" \
  -H "Content-Type: application/json" \
  -H "X-Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### Ensure there are no quotes around the YOUR_ACCESS_TOKEN for the devices data retrieval

🔹 Replace YOUR_THINGSBOARD_URL with your ThingsBoard server address.
🔹 Replace YOUR_ACCESS_TOKEN with your authentication token.
🔹 Change pageSize=1000 to adjust the number of devices fetched per request.