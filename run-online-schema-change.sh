#!/bin/bash

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

DRY_RUN=false
AUTO_APPROVE=false

TABLE_NAME="audit_logs"
COLUMN_NAME="event_source"
COLUMN_TYPE="STRING"
COLUMN_DEFAULT="iam-demo"
INDEX_NAME="audit_logs_action_timestamp_idx"

usage() {
    echo "Usage: $0 [--dry-run] [--yes]"
    echo ""
    echo "Applies two online schema changes to iam_demo:"
    echo "  1. Adds ${TABLE_NAME}.${COLUMN_NAME} as ${COLUMN_TYPE} NOT NULL DEFAULT '${COLUMN_DEFAULT}'"
    echo "  2. Creates index ${INDEX_NAME} on ${TABLE_NAME} (action, timestamp DESC)"
    echo ""
    echo "Connection environment variables checked in this order:"
    echo "  CRDB_URI, CRDB_CERT_URL, CRDB_URL, DB_URI"
    echo ""
    echo "Options:"
    echo "  --dry-run   Print the SQL without executing it"
    echo "  --yes       Skip the confirmation prompt"
    echo "  -h, --help  Show this help"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            ;;
        --yes)
            AUTO_APPROVE=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown argument '$1'${NC}"
            echo ""
            usage
            exit 1
            ;;
    esac
    shift
done

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo -e "${RED}Error: Required command '$1' was not found${NC}"
        exit 1
    fi
}

resolve_raw_url() {
    if [ -n "${CRDB_URI:-}" ]; then
        printf '%s\n' "$CRDB_URI"
        return 0
    fi

    if [ -n "${CRDB_CERT_URL:-}" ]; then
        printf '%s\n' "$CRDB_CERT_URL"
        return 0
    fi

    if [ -n "${CRDB_URL:-}" ]; then
        printf '%s\n' "$CRDB_URL"
        return 0
    fi

    if [ -n "${DB_URI:-}" ]; then
        printf '%s\n' "$DB_URI"
        return 0
    fi

    echo -e "${RED}Error: No database connection string found in CRDB_URI, CRDB_CERT_URL, CRDB_URL, or DB_URI${NC}" >&2
    exit 1
}

normalize_cli_url() {
    printf '%s\n' "$1" | sed \
        -e 's|^cockroachdb+psycopg://|postgresql://|' \
        -e 's|^cockroachdb://|postgresql://|'
}

read -r -d '' APPLY_SQL <<EOF || true
USE iam_demo;

ALTER TABLE ${TABLE_NAME}
    ADD COLUMN IF NOT EXISTS ${COLUMN_NAME} ${COLUMN_TYPE} NOT NULL DEFAULT '${COLUMN_DEFAULT}';

CREATE INDEX IF NOT EXISTS ${INDEX_NAME}
    ON ${TABLE_NAME} (action, "timestamp" DESC);
EOF

read -r -d '' VERIFY_SQL <<EOF || true
USE iam_demo;

SELECT column_name, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = '${TABLE_NAME}'
  AND column_name = '${COLUMN_NAME}';

SHOW INDEXES FROM ${TABLE_NAME};
EOF

require_command cockroach

RAW_URL="$(resolve_raw_url)"
CLI_URL="$(normalize_cli_url "$RAW_URL")"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}IAM Demo Online Schema Change${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Target database: iam_demo"
echo "Target table:    ${TABLE_NAME}"
echo "Add column:      ${COLUMN_NAME} ${COLUMN_TYPE} NOT NULL DEFAULT '${COLUMN_DEFAULT}'"
echo "Create index:    ${INDEX_NAME} ON ${TABLE_NAME} (action, timestamp DESC)"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}Dry run only. SQL that would be executed:${NC}"
    echo ""
    printf '%s\n' "$APPLY_SQL"
    exit 0
fi

if [ "$AUTO_APPROVE" != true ]; then
    read -r -p "Apply this schema change now? [y/N] " REPLY
    case "$REPLY" in
        [yY]|[yY][eE][sS])
            ;;
        *)
            echo "Cancelled."
            exit 0
            ;;
    esac
fi

echo ""
echo "Applying schema changes..."
cockroach sql --url "$CLI_URL" --execute "$APPLY_SQL"

echo ""
echo "Verifying results..."
cockroach sql --url "$CLI_URL" --execute "$VERIFY_SQL"

echo ""
echo -e "${GREEN}Schema changes completed successfully.${NC}"
echo "The demo app can continue writing to ${TABLE_NAME} while CockroachDB performs these online changes."
