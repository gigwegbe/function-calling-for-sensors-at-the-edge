# Backup TB Dashboards

## Exporting the Dashboard

- Login to the Thingsboard Web UI
- Go to the dashboard on the left pane
- Click on the Export Icon for the dashboard(s) of interest
- Select the option that embeds the images etc--*you should get a JSON file*

## Importing the Dashboards

- Load up your thingsboard and access UI via port 8080 on your browser
- Go to the dashboard on the left pane
- Click on the plus '+' button on the top right of the dashboard section
- Select "import dashboard" option NOT "create new dashboard"
- Select "browse files" located at "/integration/thingsboard/dashboard/" in the pop-up window and select the JSON file of interest and "open"
- Repeat the process for all dashboard JSONs of interest
