#!/bin/sh
# The hosted server's start: unpack a newly uploaded data bundle (deploy/bundle.py) into the volume, then serve. With no
# data yet it waits, so the machine stays up for the upload (fly ssh sftp shell).
set -e
if [ -f /data/bundle.tgz ]; then
  echo "Unpacking the data bundle..."
  tar -xzf /data/bundle.tgz -C /data && rm /data/bundle.tgz
fi
while [ ! -f /data/db/current.json ]; do
  echo "No data yet: upload data/deploy/bundle.tgz to /data/bundle.tgz (deploy/README.md), then restart the machine."
  sleep 60
done
exec python app/server/main.py --mode hosted --host 0.0.0.0 --port 8080
