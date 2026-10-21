#!/usr/bin/env bash
set -euo pipefail
umask 077

name=${BACKUP_NAME:?BACKUP_NAME is required}
[[ "$name" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo "Invalid backup name." >&2; exit 1; }
destination="/backups/$name"
mkdir "$destination"
pg_dump --format=custom --no-owner --no-acl --file="$destination/database.dump"
tar --create --gzip --file="$destination/attachments.tar.gz" --directory=/attachments .
version=$(psql --no-psqlrc --tuples-only --no-align --command='SELECT version_num FROM alembic_version')
printf 'format=1\nproject=%s\ndatabase=%s\nmigration=%s\ncreated_utc=%s\n' "$BACKUP_PROJECT" "$PGDATABASE" "$version" "$(date -u +%FT%TZ)" > "$destination/manifest.txt"
(
    cd "$destination"
    sha256sum database.dump attachments.tar.gz manifest.txt > SHA256SUMS
    touch COMPLETE
)
echo "Backup saved: $name"
