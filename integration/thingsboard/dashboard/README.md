# Backup TB Dashboards

## Exporting the Dashboard

- Login to the Thingsboard Web UI
- Go to the dashboard on the left pane
- Click on the Export Icon for the dashboard(s) of interest
- Select the option that embeds the images etc--*you should get a JSON file*

## Importing the Dashboards

NB: Importing Dashboard after importing the devices NOT before

- Load up your thingsboard and access UI via port 8080 on your browser
- Update the dashboard JSONs files with current device information by making the update_dashboard_files.sh script executable and running it:

```bash
chmod +x update_dashboard_files.sh

./update_dashboard_files.sh
```

- Go to the dashboard on the left pane
- Click on the plus '+' button on the top right of the dashboard section
- Select "import dashboard" option NOT "create new dashboard"
- Select "browse files" located at "/integration/thingsboard/dashboard/" in the pop-up window and select the JSON file of interest and "open"
- Repeat the process for all dashboard JSONs of interest
