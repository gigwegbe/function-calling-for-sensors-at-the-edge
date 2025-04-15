# Thingsboard Database Backup and Restore Process

## Restoring Database in Another Thingsboard Setup

- Confirm the name of your thingsboard container (the default based on the startup code for thingsboard is **mytb**), use that in place of **mytb**

- Copy the backup file into the new container using "**docker cp thingsboard_backup.sqlc mytb:/tmp/**"

- Restore the database from inside the container using "**docker exec -i mytb pg_restore -U thingsboard -d thingsboard -c < thingsboard_backup.sqlc**"

- Restart ThingsBoard using "**docker restart mytb**"

## Exporting the Thingsboard Database

Since PostgreSQL is running inside mytb, you can back up the ThingsBoard database from inside the container.

- Run pg_dump inside the Docker Container using "**docker exec -t mytb pg_dump -U thingsboard -F c -d thingsboard > thingsboard_backup.sqlc**"

Meaning of code snippet above:

- docker exec -t mytb: Run command inside the mytb container

- pg_dump -U thingsboard -F c -d thingsboard: Dump the database

- thingsboard_backup.sqlc: Save the backup outside the container

*After running this, you should see thingsboard_backup.sqlc in your current directory. You can verify using "**ls -lh thingsboard_backup.sqlc**".If the file is empty or too small, the backup may have failed.*
