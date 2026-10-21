#!/usr/bin/env bash
set -euo pipefail
test -d /import/objects
test -z "$(find /attachments -mindepth 1 -print -quit)" || { echo "Destination attachment volume must be empty." >&2; exit 1; }
test -z "$(find /import -type l -print -quit)" || { echo "Source must not contain symbolic links." >&2; exit 1; }
tar --create --file=- --directory=/import . | tar --extract --file=- --directory=/attachments --no-same-owner
chown -R 10001:10001 /attachments
echo "Local attachment files copied. Source files were not changed."
