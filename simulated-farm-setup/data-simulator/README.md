# Installation of IBA Data Simulator
To install the simulator, follow the steps provided in the official repository's [Installation Guide](https://github.com/IBA-Group-IT/IoT-data-simulator/tree/master)

# Importing existing sessions into IBA Data Simulator as JSON files

- Confirm the location of the JSON files for the session. In this repository, it is stored at /integration/data-simulator/

- Start up your data-simulator using the docker compose up command and access the UI on port 8090 on your browser

- Click on the upload button (i.e. blue arrow up button beside the red "Create New Session" button) on the top left of the data-simulator UI

- Select all json files in the backup folder (/integration/data-simulator) and upload. You could also select them individually if multiple selection not available&mdash;*do not worry about duplicate sessions, the simulator would not create a session if the session/json file name is already available in the UI*.

- Start all sessions&mdash;*or those you need!*
