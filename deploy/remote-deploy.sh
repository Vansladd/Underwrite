#!/bin/bash
# Runs on the box via SSM. Refreshes manifests, pins the image, restarts the unit.
set -euxo pipefail

image="${1:?usage: remote-deploy.sh <ecr-image-ref:tag>}"

cd /opt/underwrite
git pull --ff-only
sed -i "s|^API_IMAGE=.*|API_IMAGE=${image}|" .env
docker compose -f docker-compose.prod.yml pull
systemctl restart underwrite.service
