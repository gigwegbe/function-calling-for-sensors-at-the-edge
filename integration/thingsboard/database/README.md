# Thingsboard Database Backup and Restore Process

## Exporting the Thingsboard Database

Since PostgreSQL is running inside mytb, you can back up the ThingsBoard database from inside the container.

- Run pg_dump Inside the Docker Container

Run the following command from your host machine:

```bash
docker exec -t mytb pg_dump -U thingsboard -F c -d thingsboard > thingsboard_backup.sqlc
```

📌 Explanation:
docker exec -t mytb: Run command inside the mytb container.
pg_dump -U thingsboard -F c -d thingsboard: Dump the database.
thingsboard_backup.sqlc: Save the backup outside the container.

✅ After running this, you should see thingsboard_backup.sqlc in your current directory.

- Verify the Backup File

```bash
ls -lh thingsboard_backup.sqlc
```

If the file is empty or too small, the backup may have failed.

## Restoring Database in Another Thingsboard Setup

If you want to restore the backup in another ThingsBoard container:

1️⃣ Copy the backup file into the new container:

```bash
docker cp thingsboard_backup.sqlc mytb:/tmp/
```

2️⃣ Restore the database from inside the container:

```bash
docker exec -i mytb pg_restore -U thingsboard -d thingsboard -c < thingsboard_backup.sqlc
```

3️⃣ Restart ThingsBoard:

```bash
docker restart mytb
```

🔥 Automate Backup with Cron Job
To schedule daily backups, add this to your crontab:

```bash
0 2 * * * docker exec -t mytb pg_dump -U thingsboard -F c -d thingsboard > /backups/thingsboard_backup_$(date +\%Y\%m\%d).sqlc
```

This will create a backup every day at 2 AM.
