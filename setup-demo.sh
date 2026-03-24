#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Usage function
usage() {
    echo "Usage: $0 <connection-string> <password> \"<region1> <region2> <region3>\" \"<ip1> <ip2> <ip3>\""
    echo ""
    echo "Example:"
    echo "  $0 \\"
    echo "    \"postgresql://ron@nollen-iam-demo.cloud:26257/iam_demo?sslmode=verify-full&sslrootcert=\$HOME/Library/CockroachCloud/certs/cert.crt\" \\"
    echo "    \"mypassword\" \\"
    echo "    \"aws-us-east-1 aws-us-east-2 aws-us-west-2\" \\"
    echo "    \"10.0.1.5 10.0.2.5 10.0.3.5\""
    exit 1
}

# Check argument count
if [ "$#" -ne 4 ]; then
    echo -e "${RED}Error: Expected 4 arguments, got $#${NC}"
    echo ""
    usage
fi

CONNECTION_STRING="$1"
PASSWORD="$2"
REGIONS="$3"
IPS="$4"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}IAM Demo Setup Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Pre-flight checks
echo -e "${YELLOW}Pre-flight Checks:${NC}"
echo ""
echo "Before running this script, you must complete the following:"
echo "  1. Add the PUBLIC IP addresses of all 3 app servers to the CockroachDB Cloud IP allowlist"
echo "     (You can find these IPs in your Terraform output)"
echo "  2. Download the CockroachDB Cloud certificate to all app servers"
echo "     (Use the default location from the 'Connect' modal in CockroachDB Cloud)"
echo ""

read -p "Have you completed BOTH of these tasks? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${RED}Please complete the pre-flight tasks before running this script.${NC}"
    exit 1
fi
echo ""

# Validate regions
read -ra REGION_ARRAY <<< "$REGIONS"
REGION_COUNT=${#REGION_ARRAY[@]}
if [ "$REGION_COUNT" -ne 3 ]; then
    echo -e "${RED}Error: Expected exactly 3 regions, got $REGION_COUNT${NC}"
    echo "Regions provided: $REGIONS"
    exit 1
fi

# Validate IPs
read -ra IP_ARRAY <<< "$IPS"
IP_COUNT=${#IP_ARRAY[@]}
if [ "$IP_COUNT" -ne 3 ]; then
    echo -e "${RED}Error: Expected exactly 3 IP addresses, got $IP_COUNT${NC}"
    echo "IPs provided: $IPS"
    exit 1
fi

# Validate password
if [ -z "$PASSWORD" ]; then
    echo -e "${RED}Error: Password cannot be empty${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Validation passed:${NC} 3 regions, 3 IPs, password provided"
echo ""

# Check if docker-compose is available (only needed for first server, but good to check)
if ! command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}Warning: docker-compose not found. This is only required on the first server.${NC}"
fi

# Get private IP using AWS metadata service (IMDSv2)
echo "Detecting private IP address..."
TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>/dev/null)
if [ -z "$TOKEN" ]; then
    echo -e "${RED}Error: Failed to get AWS metadata token. Are you running on an EC2 instance?${NC}"
    exit 1
fi

PRIVATE_IP=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/local-ipv4 2>/dev/null)
if [ -z "$PRIVATE_IP" ]; then
    echo -e "${RED}Error: Failed to get private IP from AWS metadata service${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Detected private IP:${NC} $PRIVATE_IP"
echo ""

# Transform connection string: postgresql -> cockroachdb and add password
# Extract username from connection string
if [[ $CONNECTION_STRING =~ postgresql://([^@]+)@ ]]; then
    USERNAME="${BASH_REMATCH[1]}"
else
    echo -e "${RED}Error: Could not extract username from connection string${NC}"
    exit 1
fi

# Replace postgresql:// with cockroachdb:// and insert password
CRDB_URL=$(echo "$CONNECTION_STRING" | sed "s|postgresql://|cockroachdb://|" | sed "s|://${USERNAME}@|://${USERNAME}:${PASSWORD}@|")

echo -e "${GREEN}✓ Connection string transformed${NC}"
echo "CRDB_URL: $CRDB_URL"
echo ""

# Export CRDB_URL
export CRDB_URL="$CRDB_URL"
echo -e "${GREEN}✓ CRDB_URL exported${NC}"
echo ""

# Check if this is the first server
FIRST_IP="${IP_ARRAY[0]}"
if [ "$PRIVATE_IP" == "$FIRST_IP" ]; then
    echo -e "${YELLOW}This is the FIRST server in the list${NC}"
    echo "Updating prometheus.yml and starting docker-compose..."
    echo ""

    # Update prometheus.yml
    if [ ! -f "prometheus.yml" ]; then
        echo -e "${RED}Error: prometheus.yml not found in current directory${NC}"
        exit 1
    fi

    # Create backup
    cp prometheus.yml prometheus.yml.bak

    # Update prometheus.yml with IPs and regions
    sed -i "s|<REGION1_APP_HOST>|${IP_ARRAY[0]}|g" prometheus.yml
    sed -i "s|<REGION2_APP_HOST>|${IP_ARRAY[1]}|g" prometheus.yml
    sed -i "s|<REGION3_APP_HOST>|${IP_ARRAY[2]}|g" prometheus.yml

    sed -i "s|region: 'aws-us-east-1'|region: '${REGION_ARRAY[0]}'|g" prometheus.yml
    sed -i "s|region: 'aws-us-east-2'|region: '${REGION_ARRAY[1]}'|g" prometheus.yml
    sed -i "s|region: 'aws-us-west-2'|region: '${REGION_ARRAY[2]}'|g" prometheus.yml

    echo -e "${GREEN}✓ prometheus.yml updated${NC}"
    echo "  Region 1: ${REGION_ARRAY[0]} @ ${IP_ARRAY[0]}"
    echo "  Region 2: ${REGION_ARRAY[1]} @ ${IP_ARRAY[1]}"
    echo "  Region 3: ${REGION_ARRAY[2]} @ ${IP_ARRAY[2]}"
    echo ""

    # Start docker-compose
    echo "Starting Prometheus and Grafana..."
    if ! docker-compose up -d; then
        echo -e "${RED}Error: docker-compose failed${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ docker-compose started${NC}"
    echo ""
else
    echo -e "${YELLOW}This is NOT the first server${NC}"
    echo "Skipping prometheus.yml update and docker-compose startup"
    echo ""
fi

# Start demo.py
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Starting IAM Demo Application${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

if [ ! -f "./demo.py" ]; then
    echo -e "${RED}Error: demo.py not found in current directory${NC}"
    exit 1
fi

if [ ! -x "./demo.py" ]; then
    echo -e "${YELLOW}Warning: demo.py is not executable. Making it executable...${NC}"
    chmod +x ./demo.py
fi

# Start demo.py in foreground
./demo.py
