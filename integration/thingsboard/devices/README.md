# Exporting Thingsboard devices

## Importing Thingsboard devices and connecting to the data-simulator

NB: Import via the Web UI using the Import Button does not work for the Community Edition of Thingsboard.

- Get the access token for the Thingsboard session by running the ***get_token.sh*** bash script

- Edit the devices_import.py script by changing the ACCESS TOKEN variable with the value from the step above.

- Confirm the imports were successful by checking the devices section&mdash;*go to the left pane of the Thingsboard UI and click on Devices*.

- Get the local IP address using "**hostname -I**" for linux and "**ipconfig getifaddr en0**"

- Update the MQTT ipaddress for the Thingsboard targeting system by going to the Target Session portion of the Data-Simulator UI and select the three-dot radio button of the target system of interest then select "Update" and paste the new ip address. Also, ensure the port matches the port for your Thingsboard. For example: "172.**.**.**.**:1883"

- For each imported devices in the thingsboard devices section:

  - Simply click on the devices in the devices table. Click on "Copy access token" from the popup window that appears.

  - Go to the Devices Section of your Data Simulator, search for the device with exactly the same name as that in the Thingsboard device section that you are currently interested in.

  - Click on the three-dot radio button on the device and select "Update". Select "Proceed" to skip the data definition setup for the device&mdash;*this would take you the "Device Target System" for this device*.

  - Select the three-dot radio button for the device's target system and replace the token in "3. Select Security options" with the one copied on Thingsboard earlier. Click on proceed to save the new token and click on "Proceed" again to save the new device setting.

  - Go to the Session section of the Data-Simulator and restart the related session for the device (using the recycle button). Confirm if the data is been streamed via MQTT to the thingsboard device by checking the terminal section of the Data-Simulator and the status of the device on Thingsboard&mdash;*it should be ACTIVE*.

  - **REPEAT the process for the next device**.

## Export Devices via REST API (Bulk Export)

NB: Export via the Web UI using the Export Button does not work for the Community Edition of Thingsboard.

- Get an authentication token using your ThingsBoard username/password by running the get_token.sh script in the /integration/thingsboard/devices/ folder. Edit the username and password accordingly if the username and password is not "**tenant@thingsboard.org**" and "**tenant**".

- This will return a response as shown below:

```json
{
  "token": "YOUR_ACCESS_TOKEN"
}
```

- Replace the YOUR_ACCESS_TOKEN in the ***devices_export.sh*** script with the access token gotten in the previous step&mdash;*ensure there are no quotes around the YOUR_ACCESS_TOKEN for the devices data retrieval*. This should generate a devices_export.json file in the current directory.
