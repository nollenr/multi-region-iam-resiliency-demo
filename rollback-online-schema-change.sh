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
INDEX_NAME="audit_logs_action_timestamp_idx"

usage() {
    echo "Usage: $0 [--dry-run] [--yes]"
    echo ""
    echo "Rolls back the demo schema changes in iam_demo:"
    echo "  1. Drops index ${INDEX_NAME} from ${TABLE_NAME}"
    echo "  2. Drops column ${TABLE_NAME}.${COLUMN_NAME}"
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

DROP INDEX IF EXISTS ${TABLE_NAME}@${INDEX_NAME};

ALTER TABLE ${TABLE_NAME}
    DROP COLUMN IF EXISTS ${COLUMN_NAME};
EOF

read -r -d '' VERIFY_SQL <<EOF || true
USE iam_demo;

SELECT column_name
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
echo -e "${GREEN}IAM Demo Schema Change Rollback${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Target database: iam_demo"
echo "Target table:    ${TABLE_NAME}"
echo "Drop index:      ${INDEX_NAME}"
echo "Drop column:     ${COLUMN_NAME}"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}Dry run only. SQL that would be executed:${NC}"
    echo ""
    printf '%s\n' "$APPLY_SQL"
    exit 0
fi

if [ "$AUTO_APPROVE" != true ]; then
    read -r -p "Apply this rollback now? [y/N] " REPLY
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
echo "Applying rollback..."
cockroach sql --url "$CLI_URL" --execute "$APPLY_SQL"

echo ""
echo "Verifying results..."
cockroach sql --url "$CLI_URL" --execute "$VERIFY_SQL"

echo ""
echo -e "${GREEN}Rollback completed successfully.${NC}"
echo "You can now re-run the forward schema change script without rebuilding iam_demo."
