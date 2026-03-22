#!/bin/bash
#
# Initialize the IAM demo database
# Run this script to create the schema and load demo data
#

set -e

# Check for CRDB_URL first, then DB_URI
if [ -n "$CRDB_URL" ]; then
    DB_URI="$CRDB_URL"
elif [ -z "$DB_URI" ]; then
    echo "Error: Neither CRDB_URL nor DB_URI environment variable is set"
    echo "Example: export CRDB_URL='cockroachdb://root@localhost:26257/defaultdb?sslmode=require'"
    echo "     or: export DB_URI='cockroachdb://root@localhost:26257/defaultdb?sslmode=require'"
    exit 1
fi

# Extract host and port from DB_URI for cockroach sql command
# This is a simple extraction - adjust if your URI format differs
CLUSTER_URI=$(echo $DB_URI | sed 's/cockroachdb:/postgresql:/')

echo "=================================================="
echo "IAM Demo - Database Initialization"
echo "=================================================="
echo ""

# Step 1: Generate demo data
echo "Step 1: Generating demo data..."
python3 sql/generate_data.py
echo "✓ Demo data generated"
echo ""

# Step 2: Create schema
echo "Step 2: Creating schema and configuring multi-region..."
cockroach sql --url "$CLUSTER_URI" < sql/schema.sql
echo "✓ Schema created"
echo ""

# Step 3: Load data
echo "Step 3: Loading demo data..."
# Update URI to use iam_demo database
IAM_DB_URI=$(echo $CLUSTER_URI | sed 's/defaultdb/iam_demo/')
cockroach sql --url "$IAM_DB_URI" < sql/data.sql
echo "✓ Data loaded"
echo ""

echo "=================================================="
echo "Database initialization complete!"
echo "=================================================="
echo ""
echo "You can now start the demo application:"
echo "  export CRDB_URL='cockroachdb://root@<host>:26257/iam_demo?application_name=iam_demo'"
echo "  ./demo.py"
echo ""
echo "Note: Region is automatically detected from your database connection"
echo "      The demo checks for CRDB_URL, then DB_URI, then uses a default"
echo ""
