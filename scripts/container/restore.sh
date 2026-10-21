#!/usr/bin/env bash
set -euo pipefail

name=${BACKUP_NAME:?BACKUP_NAME is required}
[[ "$name" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo "Invalid backup name." >&2; exit 1; }
source="/backups/$name"
test -f "$source/COMPLETE" || { echo "Backup is incomplete." >&2; exit 1; }
(
    cd "$source"
    test "$(wc -l < SHA256SUMS)" -eq 3
    grep -Eq '^[0-9a-f]{64}  database.dump$' SHA256SUMS
    grep -Eq '^[0-9a-f]{64}  attachments.tar.gz$' SHA256SUMS
    grep -Eq '^[0-9a-f]{64}  manifest.txt$' SHA256SUMS
    sha256sum --check --strict SHA256SUMS
)
grep -qx 'format=1' "$source/manifest.txt"
test -z "$(find /attachments -mindepth 1 -print -quit)" || { echo "Attachment volume must be empty." >&2; exit 1; }
tables=$(psql --no-psqlrc --tuples-only --no-align --command="SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
test "$tables" = 0 || { echo "Database must be empty. Existing data was not changed." >&2; exit 1; }
tar --list --gzip --file="$source/attachments.tar.gz" > /tmp/ruris-archive-files
while IFS= read -r entry; do
    [[ "$entry" = ./ || "$entry" = ./objects/ || "$entry" = ./staging/ || "$entry" =~ ^\./objects/[0-9a-f]{64}$ ]] \
        || { echo "Unexpected attachment archive path." >&2; exit 1; }
done < /tmp/ruris-archive-files
tar --list --verbose --gzip --file="$source/attachments.tar.gz" | awk 'substr($0,1,1)!="-" && substr($0,1,1)!="d" {exit 1}'
# PostgreSQL creates public in an empty database; retain that existing schema.
pg_restore --list "$source/database.dump" | awk '!($4 == "SCHEMA" && $5 == "-" && $6 == "public")' > /tmp/ruris-restore-list
pg_restore --exit-on-error --single-transaction --no-owner --no-acl --use-list=/tmp/ruris-restore-list --dbname="$PGDATABASE" "$source/database.dump"
tar --extract --gzip --file="$source/attachments.tar.gz" --directory=/attachments --no-same-owner
chown -R 10001:10001 /attachments
echo "Database and attachments restored. Verify attachments before starting the portal."
