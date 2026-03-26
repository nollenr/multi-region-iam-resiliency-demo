#!/bin/bash

# CockroachDB Cloud Cluster Disruption Tool
#
# IMPORTANT - API Key Permissions:
#   The API Key needs to be attached to a Service Account that includes "Cluster Administrator"
#   with a scope of the cluster being disrupted.
#
# IMPORTANT - Finding the correct Cluster ID:
#   Cluster ID (From SuperUser): 6ea7a3a8-1ad6-4f19-a5bd-65213d03eef8            <-- USE THIS ONE!
#   URL (from cluster-create screen link): 6ea7a3a8-1ad6-4f19-a5bd-65213d03eef8  <-- OR THIS ONE!
#   CRDB Cluster ID (From SuperUser): 19bc23fe-761d-4540-99b5-259b0936c64b (NOT this one!)
#   Cluster Id (From Database UI): 19bc23fe-761d-4540-99b5-259b0936c64b    (NOT this one!)
#
# The Cluster ID for the Cloud API is different from the internal CRDB cluster ID.
# Use the ID from SuperUser or the cluster creation screen URL.
#
# API Documentation:
#   https://www.cockroachlabs.com/docs/cockroachcloud/cloud-api
#   https://www.cockroachlabs.com/docs/api/cloud/v1#get-/api/scim/v2/Groups
#   https://www.cockroachlabs.com/docs/api/cluster/v2 (databases, users, ranges, etc)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Usage function
usage() {
    echo "Usage: $0 <command> [arguments]"
    echo ""
    echo "Commands:"
    echo "  list                              List all regions and nodes in the cluster"
    echo "  region <region-name>              Disrupt entire region"
    echo "  az <region> <az1> [az2] [az3]     Disrupt specific availability zones"
    echo "  node <node-name>                  Disrupt specific node/pod"
    echo "  clear                             Clear all active disruptions"
    echo ""
    echo "Environment variables required:"
    echo "  COCKROACH_API_KEY  - CockroachDB Cloud API key"
    echo "  CLUSTER_ID         - CockroachDB Cloud cluster ID"
    echo ""
    echo "Examples:"
    echo "  $0 list"
    echo "  $0 region aws-us-east-2"
    echo "  $0 az aws-us-west-2 a b"
    echo "  $0 node cockroachdb-abc123"
    echo "  $0 clear"
    exit 1
}

# Check for required environment variables
check_env() {
    if [ -z "$COCKROACH_API_KEY" ]; then
        echo -e "${RED}Error: COCKROACH_API_KEY environment variable is not set${NC}"
        exit 1
    fi

    if [ -z "$CLUSTER_ID" ]; then
        echo -e "${RED}Error: CLUSTER_ID environment variable is not set${NC}"
        exit 1
    fi

    # Check if jq is available (needed for JSON parsing)
    if ! command -v jq &> /dev/null; then
        echo -e "${RED}Error: jq is not installed${NC}"
        echo "Install it with: sudo yum install -y jq"
        exit 1
    fi
}

# List all nodes in the cluster
list_nodes() {
    echo -e "${BLUE}Fetching cluster information...${NC}"
    echo ""

    RESPONSE=$(curl -s --request GET \
        --url "https://cockroachlabs.cloud/api/v1/clusters/${CLUSTER_ID}/nodes" \
        --header "Authorization: Bearer ${COCKROACH_API_KEY}")

    # Check if response contains nodes
    if ! echo "$RESPONSE" | jq -e '.nodes' > /dev/null 2>&1; then
        echo -e "${RED}Error: Failed to retrieve node information${NC}"
        echo "Response: $RESPONSE"
        exit 1
    fi

    # Parse and display regions using jq
    echo -e "${GREEN}Regions in cluster:${NC}"
    echo "$RESPONSE" | jq -r '.nodes[].region_name' | sort -u | while read region; do
        echo -e "  ${YELLOW}●${NC} $region"
    done
    echo ""

    # Parse and display nodes by region using jq
    echo -e "${GREEN}Nodes in cluster:${NC}"

    # Get unique regions
    REGIONS=$(echo "$RESPONSE" | jq -r '.nodes[].region_name' | sort -u)

    for region in $REGIONS; do
        echo -e "${YELLOW}Region: $region${NC}"

        # Extract nodes for this region using jq
        echo "$RESPONSE" | jq -r ".nodes[] | select(.region_name == \"$region\") | \"\(.name)|\(.status)\"" | while IFS='|' read node status; do
            if [ "$status" = "LIVE" ]; then
                echo -e "  ${GREEN}✓${NC} $node (${status})"
            else
                echo -e "  ${RED}✗${NC} $node (${status})"
            fi
        done
        echo ""
    done
}

# Disrupt entire region
disrupt_region() {
    local region=$1

    if [ -z "$region" ]; then
        echo -e "${RED}Error: Region name required${NC}"
        usage
    fi

    echo -e "${YELLOW}Disrupting entire region: $region${NC}"

    JSON_PAYLOAD=$(cat <<EOF
{
    "regional_disruptor_specifications": [
        {
            "region_code": "$region",
            "is_whole_region": true
        }
    ]
}
EOF
)

    RESPONSE=$(curl -s -w "\n%{http_code}" --request PUT \
        --url "https://cockroachlabs.cloud/api/v1/clusters/${CLUSTER_ID}/disrupt" \
        --header "Authorization: Bearer ${COCKROACH_API_KEY}" \
        --header "Content-Type: application/json" \
        --data "$JSON_PAYLOAD")

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    RESPONSE_BODY=$(echo "$RESPONSE" | head -n-1)

    if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 204 ]; then
        echo -e "${GREEN}✓ Region disruption activated${NC}"
        echo "  Region: $region"
    else
        echo -e "${RED}Error: Failed to disrupt region (HTTP $HTTP_CODE)${NC}"
        echo "Response: $RESPONSE_BODY"
        exit 1
    fi
}

# Disrupt specific availability zones
disrupt_az() {
    local region=$1
    shift
    local azs=("$@")

    if [ -z "$region" ] || [ ${#azs[@]} -eq 0 ]; then
        echo -e "${RED}Error: Region and at least one AZ required${NC}"
        usage
    fi

    # Build AZ array with proper prefixes
    AZ_LIST=""
    for az in "${azs[@]}"; do
        # If AZ is just a letter, prepend region
        if [[ "$az" =~ ^[a-z]$ ]]; then
            AZ_LIST="$AZ_LIST\"${region}${az}\","
        else
            AZ_LIST="$AZ_LIST\"$az\","
        fi
    done
    # Remove trailing comma
    AZ_LIST=${AZ_LIST%,}

    echo -e "${YELLOW}Disrupting AZs in region: $region${NC}"
    echo "  AZs: ${azs[*]}"

    JSON_PAYLOAD=$(cat <<EOF
{
    "regional_disruptor_specifications": [
        {
            "region_code": "$region",
            "azs": [$AZ_LIST]
        }
    ]
}
EOF
)

    RESPONSE=$(curl -s -w "\n%{http_code}" --request PUT \
        --url "https://cockroachlabs.cloud/api/v1/clusters/${CLUSTER_ID}/disrupt" \
        --header "Authorization: Bearer ${COCKROACH_API_KEY}" \
        --header "Content-Type: application/json" \
        --data "$JSON_PAYLOAD")

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    RESPONSE_BODY=$(echo "$RESPONSE" | head -n-1)

    if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 204 ]; then
        echo -e "${GREEN}✓ AZ disruption activated${NC}"
    else
        echo -e "${RED}Error: Failed to disrupt AZs (HTTP $HTTP_CODE)${NC}"
        echo "Response: $RESPONSE_BODY"
        exit 1
    fi
}

# Disrupt specific node
disrupt_node() {
    local node=$1

    if [ -z "$node" ]; then
        echo -e "${RED}Error: Node name required${NC}"
        usage
    fi

    # Get node information to find its region
    echo -e "${BLUE}Looking up node information...${NC}"
    NODES_RESPONSE=$(curl -s --request GET \
        --url "https://cockroachlabs.cloud/api/v1/clusters/${CLUSTER_ID}/nodes" \
        --header "Authorization: Bearer ${COCKROACH_API_KEY}")

    # Find region for this node using jq
    REGION=$(echo "$NODES_RESPONSE" | jq -r ".nodes[] | select(.name == \"$node\") | .region_name")

    if [ -z "$REGION" ]; then
        echo -e "${RED}Error: Node '$node' not found in cluster${NC}"
        echo "Use '$0 list' to see available nodes"
        exit 1
    fi

    echo -e "${YELLOW}Disrupting node: $node${NC}"
    echo "  Region: $REGION"

    JSON_PAYLOAD=$(cat <<EOF
{
    "regional_disruptor_specifications": [
        {
            "region_code": "$REGION",
            "pods": ["$node"]
        }
    ]
}
EOF
)

    RESPONSE=$(curl -s -w "\n%{http_code}" --request PUT \
        --url "https://cockroachlabs.cloud/api/v1/clusters/${CLUSTER_ID}/disrupt" \
        --header "Authorization: Bearer ${COCKROACH_API_KEY}" \
        --header "Content-Type: application/json" \
        --data "$JSON_PAYLOAD")

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    RESPONSE_BODY=$(echo "$RESPONSE" | head -n-1)

    if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 204 ]; then
        echo -e "${GREEN}✓ Node disruption activated${NC}"
    else
        echo -e "${RED}Error: Failed to disrupt node (HTTP $HTTP_CODE)${NC}"
        echo "Response: $RESPONSE_BODY"
        exit 1
    fi
}

# Clear all disruptions
clear_disruptions() {
    echo -e "${YELLOW}Clearing all active disruptions...${NC}"

    RESPONSE=$(curl -s -w "\n%{http_code}" --request PUT \
        --url "https://cockroachlabs.cloud/api/v1/clusters/${CLUSTER_ID}/disrupt" \
        --header "Authorization: Bearer ${COCKROACH_API_KEY}")

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    RESPONSE_BODY=$(echo "$RESPONSE" | head -n-1)

    if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 204 ]; then
        echo -e "${GREEN}✓ All disruptions cleared${NC}"
    else
        echo -e "${RED}Error: Failed to clear disruptions (HTTP $HTTP_CODE)${NC}"
        echo "Response: $RESPONSE_BODY"
        exit 1
    fi
}

# Main script logic
if [ "$#" -lt 1 ]; then
    echo -e "${RED}Error: No command specified${NC}"
    echo ""
    usage
fi

COMMAND=$1
shift

# Check environment variables
check_env

# Execute command
case "$COMMAND" in
    list)
        list_nodes
        ;;
    region)
        disrupt_region "$@"
        ;;
    az)
        disrupt_az "$@"
        ;;
    node)
        disrupt_node "$@"
        ;;
    clear)
        clear_disruptions
        ;;
    *)
        echo -e "${RED}Error: Unknown command '$COMMAND'${NC}"
        echo ""
        usage
        ;;
esac
