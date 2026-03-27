#!/bin/bash
set -e

# Make sure env vars are set first
# source demo-env.sh

# Run in background
# nohup ./demo.py > /dev/null 2>demo.err &

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Usage function
usage() {
    echo "Usage: $0 <password> <api-key> <cluster-id>"
    echo ""
    echo "Arguments:"
    echo "  password   - CockroachDB user password"
    echo "  api-key    - CockroachDB Cloud API key for allowlist management"
    echo "  cluster-id - CockroachDB Cloud cluster ID"
    echo ""
    echo "Required environment variables:"
    echo "  CRDB_CERT_URL       - Database connection string"
    echo "  DATABASE_REGIONS    - Comma-separated list of regions (e.g., \"aws-us-east-2,aws-ca-central-1,aws-us-west-2\")"
    echo ""
    echo "Optional environment variables:"
    echo "  APP_PRIVATE_IP_LIST - Comma-separated list of app server private IPs (e.g., \"10.0.1.5,10.0.2.5,10.0.3.5\")"
    echo "                        If not set, this server is treated as a non-primary region (skips Prometheus/Grafana setup)"
    echo ""
    echo "Example:"
    echo "  export CRDB_CERT_URL=\"postgresql://ron@nollen-iam-demo.cloud:26257/iam_demo?sslmode=verify-full&sslrootcert=\$HOME/Library/CockroachCloud/certs/cert.crt\""
    echo "  export DATABASE_REGIONS=\"aws-us-east-2,aws-ca-central-1,aws-us-west-2\""
    echo "  export APP_PRIVATE_IP_LIST=\"10.0.1.5,10.0.2.5,10.0.3.5\""
    echo "  $0 \"mypassword\" \"your-api-key-here\" \"nollen-iam-demo-w7v\""
    exit 1
}

# Check argument count
if [ "$#" -ne 3 ]; then
    echo -e "${RED}Error: Expected 3 arguments (password, api-key, and cluster-id), got $#${NC}"
    echo ""
    usage
fi

PASSWORD="$1"
COCKROACH_API_KEY="$2"
CLUSTER_ID="$3"

# Validate arguments
if [ -z "$PASSWORD" ]; then
    echo -e "${RED}Error: Password cannot be empty${NC}"
    exit 1
fi

if [ -z "$COCKROACH_API_KEY" ]; then
    echo -e "${RED}Error: API key cannot be empty${NC}"
    exit 1
fi

if [ -z "$CLUSTER_ID" ]; then
    echo -e "${RED}Error: Cluster ID cannot be empty${NC}"
    exit 1
fi

# Check for required environment variables
if [ -z "$CRDB_CERT_URL" ]; then
    echo -e "${RED}Error: CRDB_CERT_URL environment variable is not set${NC}"
    echo ""
    usage
fi

if [ -z "$DATABASE_REGIONS" ]; then
    echo -e "${RED}Error: DATABASE_REGIONS environment variable is not set${NC}"
    echo ""
    usage
fi

# Assign to local variables for compatibility with rest of script
CONNECTION_STRING="$CRDB_CERT_URL"
REGIONS="$DATABASE_REGIONS"
IPS="${APP_PRIVATE_IP_LIST:-}"  # Optional - empty if not set

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}IAM Demo Setup Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Pre-flight checks
echo -e "${YELLOW}Pre-flight Checks:${NC}"
echo ""
echo "IMPORTANT: The API Key must be attached to a Service Account that includes"
echo "\"Cluster Administrator\" with a scope of the cluster being configured."
echo ""
echo "This script will automatically:"
echo "  ✓ Add this server's public IP to the CockroachDB Cloud IP allowlist"
echo "  ✓ Configure Prometheus and Grafana (on first server only)"
echo "  ✓ Start the IAM demo application"
echo ""

# Validate regions (comma-separated)
IFS=',' read -ra REGION_ARRAY <<< "$REGIONS"
REGION_COUNT=${#REGION_ARRAY[@]}
if [ "$REGION_COUNT" -ne 3 ]; then
    echo -e "${RED}Error: Expected exactly 3 regions, got $REGION_COUNT${NC}"
    echo "Regions provided: $REGIONS"
    exit 1
fi

# Validate IPs (comma-separated) - only if provided
if [ -n "$IPS" ]; then
    IFS=',' read -ra IP_ARRAY <<< "$IPS"
    IP_COUNT=${#IP_ARRAY[@]}
    if [ "$IP_COUNT" -ne 3 ]; then
        echo -e "${RED}Error: Expected exactly 3 IP addresses, got $IP_COUNT${NC}"
        echo "IPs provided: $IPS"
        exit 1
    fi
    echo -e "${GREEN}✓ Validation passed:${NC} 3 regions, 3 IPs"
else
    echo -e "${GREEN}✓ Validation passed:${NC} 3 regions (no IP list - running as non-primary)"
fi
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

# Get public IP from AWS metadata service
PUBLIC_IP=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null)
if [ -z "$PUBLIC_IP" ]; then
    echo -e "${RED}Error: Failed to get public IP from AWS metadata service${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Detected public IP:${NC} $PUBLIC_IP"
echo -e "${GREEN}✓ Using cluster ID:${NC} $CLUSTER_ID"
echo ""

# Add public IP to CockroachDB Cloud allowlist
echo "Adding public IP to CockroachDB Cloud allowlist..."
API_RESPONSE=$(curl -s -w "\n%{http_code}" --request POST \
    --url "https://cockroachlabs.cloud/api/v1/clusters/${CLUSTER_ID}/networking/allowlist" \
    --header "Authorization: Bearer ${COCKROACH_API_KEY}" \
    --header "Content-Type: application/json" \
    --data "{\"cidr_ip\":\"${PUBLIC_IP}\",\"cidr_mask\":32,\"name\":\"IAM Demo - ${PRIVATE_IP}\",\"sql\":true,\"ui\":false}")

HTTP_CODE=$(echo "$API_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$API_RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 201 ]; then
    echo -e "${GREEN}✓ Public IP added to allowlist${NC}"
elif [ "$HTTP_CODE" -eq 409 ]; then
    echo -e "${YELLOW}⚠ Public IP already in allowlist${NC}"
else
    echo -e "${RED}Error: Failed to add IP to allowlist (HTTP $HTTP_CODE)${NC}"
    echo "Response: $RESPONSE_BODY"
    exit 1
fi
echo ""

# Transform connection string: postgresql -> cockroachdb+psycopg and add password
# Extract username from connection string
if [[ $CONNECTION_STRING =~ postgresql://([^@]+)@ ]]; then
    USERNAME="${BASH_REMATCH[1]}"
else
    echo -e "${RED}Error: Could not extract username from connection string${NC}"
    exit 1
fi

# Transform the connection string:
# 1. postgresql:// -> cockroachdb+psycopg://
# 2. Add password
# 3. Change database from defaultdb -> iam_demo
# 4. Change sslmode=verify-full -> sslmode=require
# 5. Remove sslrootcert parameter
CRDB_URL=$(echo "$CONNECTION_STRING" | \
    sed "s|postgresql://|cockroachdb+psycopg://|" | \
    sed "s|://${USERNAME}@|://${USERNAME}:${PASSWORD}@|" | \
    sed "s|/defaultdb|/iam_demo|" | \
    sed "s|sslmode=verify-full|sslmode=require|" | \
    sed "s|&sslrootcert=[^&]*||")

echo -e "${GREEN}✓ Connection string transformed${NC}"
echo "CRDB_URL: $CRDB_URL"
echo ""

# Export CRDB_URL
export CRDB_URL="$CRDB_URL"
echo -e "${GREEN}✓ CRDB_URL exported${NC}"
echo ""

# Create CRDB_URI for cockroach CLI (stays as postgresql, connects to defaultdb)
CRDB_URI=$(echo "$CONNECTION_STRING" | \
    sed "s|://${USERNAME}@|://${USERNAME}:${PASSWORD}@|" | \
    sed "s|sslmode=verify-full|sslmode=require|" | \
    sed "s|&sslrootcert=[^&]*||")

echo -e "${GREEN}✓ Connection string for CLI created${NC}"
echo "CRDB_URI: $CRDB_URI"
echo ""

# Export CRDB_URI
export CRDB_URI="$CRDB_URI"
echo -e "${GREEN}✓ CRDB_URI exported${NC}"
echo ""

# Check if this is the first server (only if IP list was provided)
if [ -n "$IPS" ]; then
    FIRST_IP="${IP_ARRAY[0]}"
else
    FIRST_IP=""
fi

if [ -n "$FIRST_IP" ] && [ "$PRIVATE_IP" == "$FIRST_IP" ]; then
    echo -e "${YELLOW}This is the FIRST server in the list${NC}"
    echo ""

    # Ask about database setup
    read -p "Generate data and install schema? This will DROP and recreate the iam_demo database. (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Setting up database..."
        echo ""

        # Convert comma-separated regions to space-separated for python script
        REGIONS_SPACE_SEP=$(echo "$DATABASE_REGIONS" | tr ',' ' ')

        # Generate data
        echo "Generating demo data..."
        python3.11 sql/generate_data.py --regions $REGIONS_SPACE_SEP
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to generate data${NC}"
            exit 1
        fi
        echo -e "${GREEN}✓ Demo data generated${NC}"
        echo ""

        # Update schema.sql with regions (two-pass to avoid collisions)
        echo "Updating schema.sql with regions..."

        # Restore from original backup if it exists, otherwise create it
        if [ -f "sql/schema.sql.bak.original" ]; then
            echo "Restoring schema.sql from original backup..."
            cp sql/schema.sql.bak.original sql/schema.sql
        else
            echo "Creating original backup of schema.sql..."
            cp sql/schema.sql sql/schema.sql.bak.original
        fi

        # First pass: Replace with temporary placeholders
        sed -i 's/SET PRIMARY REGION = "aws-us-east-1"/SET PRIMARY REGION = "__TEMP_REGION_1__"/' sql/schema.sql
        sed -i 's/ADD REGION "aws-us-east-2"/ADD REGION "__TEMP_REGION_2__"/' sql/schema.sql
        sed -i 's/ADD REGION "aws-us-west-2"/ADD REGION "__TEMP_REGION_3__"/' sql/schema.sql

        # Second pass: Replace placeholders with actual region names (no quotes - they're already in the template)
        sed -i 's/__TEMP_REGION_1__/'${REGION_ARRAY[0]}'/' sql/schema.sql
        sed -i 's/__TEMP_REGION_2__/'${REGION_ARRAY[1]}'/' sql/schema.sql
        sed -i 's/__TEMP_REGION_3__/'${REGION_ARRAY[2]}'/' sql/schema.sql
        echo -e "${GREEN}✓ Schema updated with regions:${NC} ${REGION_ARRAY[0]}, ${REGION_ARRAY[1]}, ${REGION_ARRAY[2]}"
        echo ""

        # Install schema
        echo "Installing schema (this will drop existing iam_demo database)..."
        cockroach sql --url "$CRDB_URI" < sql/schema.sql
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to install schema${NC}"
            exit 1
        fi
        echo -e "${GREEN}✓ Schema installed${NC}"
        echo ""

        # Load data
        echo "Loading data..."
        cockroach sql --url "$CRDB_URI" < sql/data.sql
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to load data${NC}"
            exit 1
        fi
        echo -e "${GREEN}✓ Data loaded${NC}"
        echo ""

        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}✓ Database setup complete${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
    else
        echo "Skipping database setup"
        echo ""
    fi

    echo "Updating prometheus.yml and Grafana dashboards..."
    echo ""

    # Update prometheus.yml
    if [ ! -f "prometheus.yml" ]; then
        echo -e "${RED}Error: prometheus.yml not found in current directory${NC}"
        exit 1
    fi

    # Restore from original backup if it exists, otherwise create it
    if [ -f "prometheus.yml.bak.original" ]; then
        echo "Restoring prometheus.yml from original backup..."
        cp prometheus.yml.bak.original prometheus.yml
    else
        echo "Creating original backup of prometheus.yml..."
        cp prometheus.yml prometheus.yml.bak.original
    fi

    # Update prometheus.yml with IPs and regions
    sed -i "s|<REGION1_APP_HOST>|${IP_ARRAY[0]}|g" prometheus.yml
    sed -i "s|<REGION2_APP_HOST>|${IP_ARRAY[1]}|g" prometheus.yml
    sed -i "s|<REGION3_APP_HOST>|${IP_ARRAY[2]}|g" prometheus.yml

    # Use two-pass replacement to avoid collision when new region names match old ones
    # First pass: Replace with temporary placeholders
    sed -i "s|region: 'aws-us-east-1'|region: '__TEMP_REGION_1__'|g" prometheus.yml
    sed -i "s|region: 'aws-us-east-2'|region: '__TEMP_REGION_2__'|g" prometheus.yml
    sed -i "s|region: 'aws-us-west-2'|region: '__TEMP_REGION_3__'|g" prometheus.yml

    # Second pass: Replace placeholders with actual region names
    sed -i "s|region: '__TEMP_REGION_1__'|region: '${REGION_ARRAY[0]}'|g" prometheus.yml
    sed -i "s|region: '__TEMP_REGION_2__'|region: '${REGION_ARRAY[1]}'|g" prometheus.yml
    sed -i "s|region: '__TEMP_REGION_3__'|region: '${REGION_ARRAY[2]}'|g" prometheus.yml

    echo -e "${GREEN}✓ prometheus.yml updated${NC}"
    echo "  Region 1: ${REGION_ARRAY[0]} @ ${IP_ARRAY[0]}"
    echo "  Region 2: ${REGION_ARRAY[1]} @ ${IP_ARRAY[1]}"
    echo "  Region 3: ${REGION_ARRAY[2]} @ ${IP_ARRAY[2]}"
    echo ""

    # Update Grafana dashboards
    echo "Updating Grafana dashboards with new regions..."
    if [ ! -d "grafana/dashboards" ]; then
        echo -e "${RED}Error: grafana/dashboards directory not found${NC}"
        exit 1
    fi

    # Restore from original backups or create them
    for dashboard in grafana/dashboards/*.json; do
        if [ -f "$dashboard" ]; then
            if [ -f "${dashboard}.bak.original" ]; then
                # Restore from original backup
                cp "${dashboard}.bak.original" "$dashboard"
            else
                # Create original backup
                cp "$dashboard" "${dashboard}.bak.original"
            fi
        fi
    done

    # Update region names in all dashboard JSON files
    # Use two-pass replacement to avoid collision when new region names match old ones
    # First pass: Replace with temporary placeholders
    sed -i "s|aws-us-east-1|__TEMP_REGION_1__|g" grafana/dashboards/*.json
    sed -i "s|aws-us-east-2|__TEMP_REGION_2__|g" grafana/dashboards/*.json
    sed -i "s|aws-us-west-2|__TEMP_REGION_3__|g" grafana/dashboards/*.json

    # Second pass: Replace placeholders with actual region names
    sed -i "s|__TEMP_REGION_1__|${REGION_ARRAY[0]}|g" grafana/dashboards/*.json
    sed -i "s|__TEMP_REGION_2__|${REGION_ARRAY[1]}|g" grafana/dashboards/*.json
    sed -i "s|__TEMP_REGION_3__|${REGION_ARRAY[2]}|g" grafana/dashboards/*.json

    echo -e "${GREEN}✓ Grafana dashboards updated${NC}"
    echo "  All dashboards updated with new region names"
    echo ""

    # Start docker-compose (stop first to ensure fresh config is loaded)
    echo "Starting Prometheus and Grafana..."
    docker-compose down 2>/dev/null || true  # Stop if running, ignore errors if not
    if ! docker-compose up -d; then
        echo -e "${RED}Error: docker-compose failed${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ docker-compose started${NC}"
    echo ""
else
    if [ -z "$IPS" ]; then
        echo -e "${YELLOW}No APP_PRIVATE_IP_LIST provided - running as non-primary region${NC}"
    else
        echo -e "${YELLOW}This is NOT the first server${NC}"
    fi
    echo "Skipping prometheus.yml update and docker-compose startup"
    echo ""
fi

# Create demo-env.sh for easy sourcing of environment variables
echo "Creating demo-env.sh for environment variables..."
cat > demo-env.sh << EOF
# Demo environment variables
# Source this file to set up your environment: source demo-env.sh

export COCKROACH_API_KEY="$COCKROACH_API_KEY"
export CLUSTER_ID="$CLUSTER_ID"
export CRDB_URL="$CRDB_URL"
export CRDB_URI="$CRDB_URI"
EOF

chmod 644 demo-env.sh
echo -e "${GREEN}✓ demo-env.sh created${NC}"
echo "  To reuse these variables: source demo-env.sh"
echo ""

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
