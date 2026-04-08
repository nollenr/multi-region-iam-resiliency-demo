#!/bin/bash

# CockroachDB Cloud IP Allowlist Cleanup Script
#
# Deletes all IP allowlist entries EXCEPT:
# - Desktop (netskope)
# - Desktop (no netskope)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for required environment variables
if [ -z "$COCKROACH_API_KEY" ]; then
    echo -e "${RED}Error: COCKROACH_API_KEY environment variable is not set${NC}"
    exit 1
fi

if [ -z "$CLUSTER_ID" ]; then
    echo -e "${RED}Error: CLUSTER_ID environment variable is not set${NC}"
    exit 1
fi

# Check if jq is available
if ! command -v jq &> /dev/null; then
    echo -e "${RED}Error: jq is not installed${NC}"
    echo "Install it with: sudo yum install -y jq"
    exit 1
fi

echo -e "${YELLOW}Fetching current allowlist entries...${NC}"
echo ""

# Get current allowlist
RESPONSE=$(curl -s --request GET \
    --url "https://cockroachlabs.cloud/api/v1/clusters/${CLUSTER_ID}/networking/allowlist" \
    --header "Authorization: Bearer ${COCKROACH_API_KEY}")

# Check if response is valid
if ! echo "$RESPONSE" | jq -e '.allowlist' > /dev/null 2>&1; then
    echo -e "${RED}Error: Failed to retrieve allowlist${NC}"
    echo "Response: $RESPONSE"
    exit 1
fi

# Display current entries
echo -e "${GREEN}Current allowlist entries:${NC}"
echo "$RESPONSE" | jq -r '.allowlist[] | "  \(.name) - \(.cidr_ip)/\(.cidr_mask)"'
echo ""

# Entries to keep (case-sensitive)
KEEP_ENTRIES=("Desktop (netskope)" "Desktop (no netskope)")

# Count entries to delete
TO_DELETE=$(echo "$RESPONSE" | jq -r --argjson keep "$(printf '%s\n' "${KEEP_ENTRIES[@]}" | jq -R . | jq -s .)" \
    '.allowlist[] | select([.name] | inside($keep) | not) | .name' | wc -l)

if [ "$TO_DELETE" -eq 0 ]; then
    echo -e "${GREEN}No entries to delete. Only protected entries remain.${NC}"
    exit 0
fi

echo -e "${YELLOW}Entries to DELETE: $TO_DELETE${NC}"
echo "$RESPONSE" | jq -r --argjson keep "$(printf '%s\n' "${KEEP_ENTRIES[@]}" | jq -R . | jq -s .)" \
    '.allowlist[] | select([.name] | inside($keep) | not) | "  \(.name) - \(.cidr_ip)/\(.cidr_mask)"'
echo ""

echo -e "${GREEN}Entries to KEEP:${NC}"
for entry in "${KEEP_ENTRIES[@]}"; do
    echo "  $entry"
done
echo ""

# Confirm deletion
read -p "Delete $TO_DELETE entries? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo -e "${YELLOW}Deleting entries one by one...${NC}"

# Delete each entry (except the ones we want to keep)
DELETED=0
FAILED=0

echo "$RESPONSE" | jq -r --argjson keep "$(printf '%s\n' "${KEEP_ENTRIES[@]}" | jq -R . | jq -s .)" \
    '.allowlist[] | select([.name] | inside($keep) | not) | "\(.cidr_ip)|\(.cidr_mask)|\(.name)"' | \
while IFS='|' read -r cidr_ip cidr_mask name; do
    echo -n "  Deleting: $name ($cidr_ip/$cidr_mask)... "

    DELETE_RESPONSE=$(curl -s -w "\n%{http_code}" --request DELETE \
        --url "https://cockroachlabs.cloud/api/v1/clusters/${CLUSTER_ID}/networking/allowlist/${cidr_ip}/${cidr_mask}" \
        --header "Authorization: Bearer ${COCKROACH_API_KEY}")

    HTTP_CODE=$(echo "$DELETE_RESPONSE" | tail -n1)

    if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 204 ]; then
        echo -e "${GREEN}✓${NC}"
        ((DELETED++))
    else
        echo -e "${RED}✗ (HTTP $HTTP_CODE)${NC}"
        ((FAILED++))
    fi
done

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Cleanup complete${NC}"
echo -e "${GREEN}========================================${NC}"
echo "Deleted: $DELETED entries"
if [ "$FAILED" -gt 0 ]; then
    echo -e "${RED}Failed: $FAILED entries${NC}"
fi
