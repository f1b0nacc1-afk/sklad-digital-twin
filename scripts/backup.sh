#!/usr/bin/env sh
# НФТ-Н-04: резервная копия БД. Восстановление:
#   gunzip -c backups/sklad_YYYYmmdd_HHMMSS.sql.gz | docker compose exec -T db psql -U sklad -d sklad
set -eu
cd "$(dirname "$0")/.."
mkdir -p backups
file="backups/sklad_$(date +%Y%m%d_%H%M%S).sql.gz"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' | gzip > "$file"
echo "backup: $file"
