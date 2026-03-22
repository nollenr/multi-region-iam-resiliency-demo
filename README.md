# CockroachDB Multi-Region IAM Demo
# CockroachDB Multi-Region IAM Demo

This demo demonstrates CockroachDB's multi-region capabilities and resiliency using an Identity and Access Management (IAM) use case. It showcases how authentication and authorization systems can continue to function even when an entire region fails.

## What This Demo Shows

The demo illustrates three types of multi-region tables with different latency characteristics:

1. **Global Tables** (users, roles) - Fast reads from any region, slower writes
2. **Regional Tables** (sessions) - Fast reads/writes in the primary region
3. **Regional-by-Row Tables** (audit_logs) - Each row stored in its designated region

**Focus**: This demo emphasizes **resiliency** - showing how IAM operations continue functioning when a region fails, not the complexity of IAM systems themselves.

## Architecture

- Multi-region CockroachDB cluster (3 regions by default)
- One application instance per region
- Each app connects only to local CockroachDB nodes via HAProxy
- When a region fails, that app enters a retry loop (does NOT failover)
- When the region recovers, the app automatically reconnects

## Prerequisites

- Multi-region CockroachDB cluster with regions configured (default: `aws-us-east-1`, `aws-us-east-2`, `aws-us-west-2`)
  - **Note**: Update `sql/schema.sql` to match your actual cluster regions
- Python 3.8 or higher
- Cluster configured to survive region failure

## Setup Instructions

### 1. Generate Demo Data

Generate the SQL data file (creates 50k+ rows):

```bash
# With default regions (aws-us-east-1, aws-us-east-2, aws-us-west-2)
python3 sql/generate_data.py

# With custom regions (specify your actual cluster regions)
python3 sql/generate_data.py --regions us-east-1 us-west-2 eu-central-1

# Get help
python3 sql/generate_data.py --help
```

**Options:**
- `--regions` or `-r`: Space-separated list of regions (must match your cluster regions)
- `--output` or `-o`: Output file path (default: `sql/data.sql`)

This creates `sql/data.sql` with demo data for:
- 1,000 users
- 15 roles
- 5,000 historical sessions (distributed randomly across regions)
- 50,000 audit log entries (distributed evenly across regions)

### 2. Initialize Database

Connect to your CockroachDB cluster and run:

```bash
# Create schema and configure multi-region
cockroach sql --url "postgresql://root@<your-cluster>:26257/defaultdb?sslmode=require" < sql/schema.sql

# Load demo data
cockroach sql --url "postgresql://root@<your-cluster>:26257/iam_demo?sslmode=require" < sql/data.sql
```

### 3. Install Python Dependencies

On each app server (one per region):

```bash
pip3 install -r requirements.txt
```

### 4. Configure Application

Edit `demo.env` or set environment variables:

```bash
# Database connection - point to your regional HAProxy/load balancer
# Use CRDB_URL (preferred) or DB_URI
export CRDB_URL="cockroachdb://root@<haproxy-host>:26257/iam_demo?application_name=iam_demo&sslmode=require"
```

**Note**: The application checks for `CRDB_URL` first, then `DB_URI`, then uses a default. The region is automatically detected via `gateway_region()` - no manual configuration needed!

### 5. Start Demo Applications

In separate terminals for each region (connect to each region's local HAProxy):

**Region 1 (aws-us-east-1):**
```bash
export CRDB_URL="cockroachdb://root@<region1-haproxy>:26257/iam_demo?application_name=iam_demo_east1"
./demo.py
```

**Region 2 (aws-us-east-2):**
```bash
export CRDB_URL="cockroachdb://root@<region2-haproxy>:26257/iam_demo?application_name=iam_demo_east2"
./demo.py
```

**Region 3 (aws-us-west-2):**
```bash
export CRDB_URL="cockroachdb://root@<region3-haproxy>:26257/iam_demo?application_name=iam_demo_west2"
./demo.py
```

## Demo Walkthrough

### Normal Operation

When all regions are healthy, you'll see latency stats every 5 seconds:

```
2026-03-19 10:23:45.123456
---------------------------------------
Global tables (users, roles)
  reads:     2.34 ms avg

Regional tables (sessions)
  writes:    3.45 ms avg

RBR tables (audit_logs)
  reads:     1.23 ms avg
  writes:    2.56 ms avg
  AOST:      0.89 ms avg
```

### Understanding the Latencies

**Global Tables (users, roles)**
- **Reads**: Fast from any region (local replica)
- **Writes**: Slower (requires consensus across regions)
- Use case: Data that must be consistent everywhere (user accounts, permissions)

**Regional Tables (sessions)**
- **Writes**: Fast in primary region (where leaseholder lives)
- Use case: Data primarily accessed from one region

**Regional-by-Row Tables (audit_logs)**
- **Reads**: Fast when reading from local region
- **Writes**: Fast (writes to local region)
- **AOST** (Follower reads): Fastest - reads from local follower without contacting leaseholder
- Use case: Data that's naturally partitioned by region

### Simulating Region Failure

1. **Prepare to fail a region** (e.g., aws-us-east-1)

   Before failing, explain what will happen:
   - aws-us-east-1 app will enter retry loop, displaying "Connection lost, attempting to reconnect..."
   - aws-us-east-2 and aws-us-west-2 (surviving regions) will continue operating normally
   - You may see 1-2 cycles of higher latency as leaseholders are re-elected
   - Regional table latencies may change as leaseholders move to surviving regions

2. **Open DB Console**

   Show the Cluster Overview page:
   - Note the number of nodes live, 0 suspect, 0 dead
   - Note: 0 under-replicated ranges, 0 unavailable ranges

3. **Fail the region**

   Stop all CockroachDB nodes in the target region (method depends on your deployment).

4. **Observe the behavior**

   - Failed region's app displays: "Connection lost, attempting to reconnect..."
   - Surviving regions' apps continue showing latency stats (may see brief spike during leaseholder re-election)
   - In DB Console: Nodes show as "Suspect" then "Dead" (after ~1m15s with default settings)
   - During suspect period: Some ranges show as under-replicated
   - After nodes declared dead: Under-replicated ranges return to 0

5. **Discuss the latencies**

   - Global tables: Same latencies as before (data still available)
   - Regional table writes: May have different latencies (leaseholders moved)
   - RBR table operations: Unchanged for surviving regions

### Restoring the Failed Region

1. **Restart the failed region's nodes**

2. **Observe recovery**

   - Failed region's app automatically reconnects and resumes showing stats
   - Regional table latencies may be higher in the recovered region initially
   - Within ~30 seconds, leaseholders rebalance back
   - All latencies return to normal

## Demo Flow (Per Iteration)

Each iteration of the demo simulates a user session:

1. **Login** - Create session (regional write to sessions table)
2. **Check User** - Read user info (global read from users table)
3. **Check Role** - Read role/permissions (global read from roles table)
4. **Perform Actions** - Create 5 audit log entries (RBR writes to audit_logs table)
5. **Logout** - End session (regional write to sessions table)
6. **Read Audit** - Read recent audit entry (RBR read from audit_logs table)
7. **Read Audit (AOST)** - Follower read of audit entry (RBR AOST read from audit_logs table)

## Project Structure

```
.
├── demo.py                  # Main application
├── demo.env                 # Environment variable template
├── requirements.txt         # Python dependencies
├── README.md               # This file
├── iam/                    # IAM module
│   ├── __init__.py
│   ├── transactions.py     # Database transaction functions
│   └── helpers.py          # Stats tracking, timing, retry logic
└── sql/                    # SQL scripts
    ├── schema.sql          # Database schema and multi-region config
    ├── generate_data.py    # Data generation script
    └── data.sql            # Generated demo data (created by generate_data.py)
```

## Key Features

- **Bulletproof Connection Handling**: Apps retry indefinitely on connection loss
- **Transaction Retry Logic**: Handles serialization failures and transient errors
- **Clean Statistics**: Shows latencies grouped by table type
- **Simple Setup**: Minimal configuration required
- **Real-time Metrics**: 5-second refresh interval shows operation latencies

## Prometheus and Grafana Setup (Optional)

For professional visualization of metrics, you can deploy Prometheus and Grafana alongside the demo applications.

### Monitoring Architecture

- Prometheus scrapes metrics from all 3 regional IAM demo apps (port 8000)
- Grafana connects to Prometheus and displays dashboards
- Both run as Docker containers on one of the regional EC2 instances (typically Region 1)

### Monitoring Prerequisites

- Docker and Docker Compose installed on the monitoring host
- Network access from Prometheus to all 3 app hosts on port 8000
- Ports 3000 (Grafana) and 9090 (Prometheus) accessible

### Monitoring Setup Instructions

#### 1. Install Docker on Amazon Linux

**For Amazon Linux 2:**

```bash
sudo yum update -y
sudo yum install -y docker
sudo service docker start
sudo usermod -a -G docker ec2-user

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

**For Amazon Linux 2023:**

```bash
sudo yum update -y
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -a -G docker ec2-user

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

Log out and back in for group membership to take effect.

#### 2. Configure Prometheus

Edit `prometheus.yml` and replace the placeholder hosts with your actual app server IPs/hostnames:

```yaml
scrape_configs:
  - job_name: 'iam-demo'
    scrape_interval: 5s
    static_configs:
      - targets: ['10.0.1.10:8000']  # Replace with Region 1 app host
        labels:
          region: 'aws-us-east-1'

      - targets: ['10.0.2.10:8000']  # Replace with Region 2 app host
        labels:
          region: 'aws-us-east-2'

      - targets: ['10.0.3.10:8000']  # Replace with Region 3 app host
        labels:
          region: 'aws-us-west-2'
```

#### 3. Configure Security Groups

Allow Prometheus to scrape metrics from all app servers on port 8000:

**For each app server's security group:**
1. Go to EC2 Console → Security Groups
2. Select the security group for the app server
3. Add inbound rule:
   - **Type:** Custom TCP
   - **Port:** 8000
   - **Source:** IP address of Prometheus/Grafana host (or its security group ID)
   - **Description:** Prometheus metrics scraping

**Note:** If Prometheus is running on the same host as one of the apps, use `localhost:8000` for that target in `prometheus.yml` instead of the public IP.

#### 4. Set File Permissions

Ensure the dashboard file is readable by Grafana:

```bash
chmod 644 grafana/dashboards/iam-demo.json
```

#### 5. Start Grafana and Prometheus

```bash
# From the demo directory
docker-compose up -d

# Check that containers are running
docker-compose ps

# View logs if needed
docker-compose logs -f
```

#### 6. Access Grafana

1. Open browser to `http://<monitoring-host>:3000`
2. Login with default credentials:
   - Username: `admin`
   - Password: `admin`
3. Change password when prompted (or skip)
4. The dashboard "CockroachDB IAM Multi-Region Demo" should be automatically loaded

#### 7. Verify Metrics Collection

1. Navigate to Prometheus: `http://<monitoring-host>:9090`
2. Go to Status → Targets
3. Verify all 3 IAM demo apps show as "UP"
4. If any show as "DOWN", check:
   - App is running and exposing metrics on port 8000
   - Network connectivity between Prometheus and app hosts
   - Firewall/security group rules allow port 8000

### Dashboard Features

The Grafana dashboard includes:

- **Global Tables Latency**: Read and write latencies for users/roles tables
- **Regional Tables Latency**: Read, write, and AOST latencies for sessions table
- **Regional-by-Row Tables Latency**: Read and write latencies for audit_logs table
- **Operations per Second by Region**: Total throughput per region
- **Region Status Gauges**: Visual indicators showing which regions are up/down
- **Operations by Table Type**: Stacked view of operations across table types
- **Average Latency by Operation**: Bar chart of all operation latencies

### Observing Region Failures

When you fail a region during the demo:

1. The region status gauge will change from green "UP" to red "DOWN"
2. Operations per second will drop to zero for that region
3. The other regions continue showing normal metrics
4. Latency graphs show how surviving regions are affected

When the region recovers:

1. The status gauge returns to green "UP"
2. Operations resume for that region
3. Latency may be temporarily elevated as leaseholders rebalance

### Stopping Grafana and Prometheus

```bash
# Stop containers but keep data
docker-compose stop

# Stop and remove containers (keeps volumes/data)
docker-compose down

# Stop and remove everything including data
docker-compose down -v
```

### Monitoring Troubleshooting

**Grafana shows "No data":**

- Verify Prometheus is running: `docker-compose ps`
- Check Prometheus targets: `http://<host>:9090/targets`
- Ensure IAM demo apps are running and exposing metrics

**Can't access Grafana/Prometheus:**

- Check security group rules allow inbound on ports 3000 and 9090
- Verify containers are running: `docker-compose ps`
- Check logs: `docker-compose logs grafana` or `docker-compose logs prometheus`

**Metrics not updating:**

- Verify scrape interval in prometheus.yml (default: 5s)
- Check Prometheus logs: `docker-compose logs prometheus`
- Ensure app hosts are reachable from Prometheus container

## Technologies Used

- **CockroachDB**: Multi-region distributed SQL database
- **Python 3**: Application runtime
- **SQLAlchemy**: SQL toolkit and ORM
- **psycopg3**: PostgreSQL adapter for Python
- **sqlalchemy-cockroachdb**: CockroachDB dialect for SQLAlchemy
- **Prometheus**: Metrics collection and monitoring
- **Grafana**: Metrics visualization and dashboards
- **Docker**: Container runtime for Prometheus and Grafana

## Notes for Presenters

- This demo runs in front of Ory and Teleport executives - keep it simple!
- Focus on **resiliency** story, not IAM complexity
- Key message: "IAM systems need to be always available - CRDB makes that possible"
- The retry loop behavior (vs failover) clearly demonstrates regional isolation
- Follower reads (AOST) show how to get even lower latency for slightly stale data

## Troubleshooting

**App shows connection errors immediately:**
- Check DB_URI is correct and accessible
- Verify CockroachDB cluster is running
- Check network connectivity to HAProxy/load balancer

**No latency stats displayed:**
- Ensure database has data (run data generation and import)
- Verify there are active users and roles in the database
- Check that your connection reaches the database (gateway_region() should return a valid region)

**High latencies:**
- Check network latency between regions
- Verify cluster is properly distributed across regions
- Review DB Console for hot spots or rebalancing activity

## License

This demo is provided as-is for demonstration purposes.
