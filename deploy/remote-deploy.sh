#!/usr/bin/env bash
# Runs ON the EC2 instance (sent by the CD workflow through SSM Run Command).
# Inputs (env): BACKEND_IMAGE, GIT_SHA, AWS_REGION. Secrets come from SSM Parameter Store.
set -euo pipefail

cd /opt/truckroute

param() {
  aws ssm get-parameter --region "$AWS_REGION" --with-decryption \
    --name "/truckroute/$1" --query Parameter.Value --output text
}

umask 077
cat > .env <<EOF
BACKEND_IMAGE=${BACKEND_IMAGE}
GIT_SHA=${GIT_SHA}
SECRET_KEY=$(param django_secret_key)
ORIGIN_SECRET=$(param origin_secret)
POSTGRES_PASSWORD=$(param postgres_password)
TOM_TOM_API_KEY=$(param tomtom_api_key)
# Caddy only forwards requests that carry the origin secret, so any Host is acceptable here.
ALLOWED_HOSTS=*
EOF

registry="${BACKEND_IMAGE%%/*}"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$registry"

docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --remove-orphans

# Wait until the new build answers with the expected version.
origin_secret="$(grep '^ORIGIN_SECRET=' .env | cut -d= -f2-)"
for _ in $(seq 1 40); do
  body="$(curl -fsS -H "X-Origin-Secret: ${origin_secret}" http://localhost/api/v1/health || true)"
  if [[ "$body" == *"\"${GIT_SHA}\""* ]]; then
    echo "healthy: ${body}"
    exit 0
  fi
  sleep 3
done

echo "health check failed; last response: ${body:-<none>}" >&2
docker compose -f docker-compose.prod.yml logs --tail 50 >&2
exit 1
