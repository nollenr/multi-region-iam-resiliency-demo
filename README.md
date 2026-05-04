# CockroachDB Multi-Region IAM Demo

This demo demonstrates CockroachDB's multi-region capabilities and resiliency using an Identity and Access Management (IAM) use case. It showcases how authentication and authorization systems can continue to function even when an entire region fails.

## What This Demo Shows

The demo illustrates three types of multi-region tables with different latency characteristics:

1. **Global Tables** (users, roles) - Fast reads from any region, slower writes
2. **Regional Tables** (sessions) - Fast reads/writes in the primary region
3. **Regional-by-Row Tables** (audit_logs) - Each row stored in its designated region

**Focus**: This demo emphasizes **resiliency** - showing how IAM operations continue functioning when a region fails, not the complexity of IAM systems themselves.

## Architecture

- **CockroachDB Cloud Advanced** multi-region cluster (3 regions)
- **One application instance per region** (deployed on EC2)
- Each app connects only to the cluster (CockroachDB manages routing)
- When a region fails, that app enters a retry loop (does NOT failover)
- When the region recovers, the app automatically reconnects
- **Prometheus + Grafana** for real-time metrics visualization (on primary region)

## Prerequisites

### CockroachDB Cloud Cluster

**Required:** A CockroachDB Cloud Advanced cluster across 3 regions must be created before running Terraform.

### Infrastructure (Deployed by Terraform)

This demo is designed to be deployed via Terraform, which automatically:

- Deploys EC2 app servers in each region
- Sets required environment variables in `.bashrc`

**Required environment variables** (set by Terraform in `.bashrc`):

```bash
export CRDB_CERT_URL="postgresql://user@cluster-id.region.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full&sslrootcert=..."
export DATABASE_REGIONS="region1,region2,region3"  # Comma-separated
export APP_PRIVATE_IP_LIST="ip1,ip2,ip3"          # Comma-separated (primary region only)
```

### Software Requirements (all installed by Terraform)

- **Python 3.11** 
- **Docker + Docker Compose** (for Prometheus/Grafana on primary region)
- **cockroach CLI** (for database setup)

## Required Values for Setup

Before running `setup-demo.sh`, you'll need three values from CockroachDB Cloud:

### 1. Database User Password

**Where to find:**
1. Go to [CockroachDB Cloud Console](https://cockroachlabs.cloud)
2. Click **Clusters** in the top menu
3. Select your cluster
4. In the left menu, go to **Security → SQL Users**
5. Create a new SQL user (or use existing)
6. **Copy the password** during creation (shown only once!)

### 2. API Key

**Where to create:**
1. In CockroachDB Cloud Console
2. Click **Organization** in the top menu
3. Go to **Access Management → Service Accounts**
4. Create a new service account
5. Assign role: **Cluster Administrator** (scope: your cluster)
6. Generate and **copy the API key** (shown only once!)

**Important:** The API key must have "Cluster Administrator" permissions scoped to your cluster for IP allowlist management and disruption testing.

### 3. Cluster ID

**Where to find:**
1. Go to your cluster page in CockroachDB Cloud Console
2. Look at the browser URL
3. The cluster ID is the UUID in the URL

**Example URL:**
```
https://cockroachlabs.cloud/cluster/2b50f1df-8a4d-401b-8d45-bfb0eb589a96/overview
                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                    This is your Cluster ID
```

**Note:** This is the Cloud cluster ID (UUID format), NOT the internal CRDB cluster ID shown in the database UI.

## Setup Instructions

### Quick Start (Primary Region Only)

SSH into the **primary region** app server (Region 1) and run:

```bash
./setup-demo.sh "<password>" "<api-key>" "<cluster-id>"
```

**What it does:**
1. ✅ Detects server's public IP and adds to cluster IP allowlist
2. ✅ Creates connection strings for demo app and CLI
3. ❓ **Asks if you want to setup the database** (yes/no)
   - Generates demo data (1000 users, 15 roles, 50k+ rows)
   - Updates schema with your regions
   - Drops and recreates `iam_demo` database
   - Loads all demo data
4. ✅ Updates Prometheus and Grafana dashboards with your regions
5. ✅ Starts Prometheus + Grafana (primary region only)
6. ✅ Creates `demo-env.sh` for easy variable reuse
7. ✅ Starts the IAM demo application

### Secondary Regions

SSH into **each secondary region** app server and run the same command:

```bash
./setup-demo.sh "<password>" "<api-key>" "<cluster-id>"
```

**What it does on secondary regions:**
1. ✅ Detects server's public IP and adds to cluster IP allowlist
2. ✅ Creates connection strings
3. ⏭️ Skips database setup (only primary does this)
4. ⏭️ Skips Prometheus/Grafana (only primary has monitoring)
5. ✅ Creates `demo-env.sh`
6. ✅ Starts the IAM demo application

### After Setup

The script creates `demo-env.sh` with all necessary environment variables:

```bash
# On subsequent logins, just source this file:
source demo-env.sh
```

## Running the Demo

### Viewing Metrics

**Grafana Dashboards** (Primary region only):
- URL: `http://<primary-region-ip>:3000`
- Login: `admin` / `admin`
- Five pre-configured dashboards showing latencies by region

**Prometheus** (for troubleshooting):
- URL: `http://<primary-region-ip>:9090`

### Demo Flow: Simulating Region Failure

The demo uses `disrupt.sh` to simulate region failures via the CockroachDB Cloud API.

**1. List available regions and nodes:**
```bash
source demo-env.sh  # Load credentials
./disrupt.sh list
```

**2. Observe normal operation:**
- Check Grafana dashboards - all regions showing healthy metrics
- All demo apps showing latency stats every 5 seconds

**3. Disrupt a region:**
```bash
# Disrupt entire region
./disrupt.sh region aws-us-east-2

# Or disrupt specific availability zones
./disrupt.sh az aws-us-west-2 a b

# Or disrupt a single node
./disrupt.sh node cockroachdb-abc123
```

**4. Watch the behavior:**
- **Failed region's app:** Shows "Connection lost, attempting to reconnect..."
- **Surviving regions:** Continue operating normally
- **Grafana:** Failed region's metrics drop to zero, status gauge turns red
- **DB Console:** Nodes show as "Suspect" then "Dead" after ~1m15s

**5. Clear the disruption:**
```bash
./disrupt.sh clear
```

**6. Observe recovery:**
- Failed region's app automatically reconnects
- Metrics resume in Grafana
- Latencies may be briefly elevated during leaseholder rebalancing

### Understanding the Latencies

**Global Tables (users, roles)**
- **Reads:** Fast from any region (local replica)
- **Writes:** Slower (requires consensus across regions)
- **Use case:** Data that must be consistent everywhere

**Regional Tables (sessions)**
- **Reads/Writes:** Fast in primary region
- **AOST Reads:** Fastest (follower reads from local replica)
- **Use case:** Data primarily accessed from one region

**Regional-by-Row Tables (audit_logs)**
- **Reads:** Fast when reading local region's data
- **Writes:** Fast (written to local region)
- **AOST Reads:** Fastest (local follower reads)
- **Use case:** Data naturally partitioned by region

## Demo Flow (Per Iteration)

Each iteration simulates a complete user session:

1. **Login** - Create session (regional write)
2. **Anomaly Detection** - Check if login is unusual (vector search)
3. **Read User** - Fetch user info (global read)
4. **Update Last Login** - Update user record (global write)
5. **Read Role** - Check permissions (global read)
6. **Perform Actions** - Create 5 audit logs (RBR writes)
7. **Logout** - End session (regional write)
8. **Read Audit** - Fetch recent audit entry (RBR read)
9. **Read Session** - Current data (regional read)
10. **Read Session (AOST)** - Follower read (regional AOST)

Stats displayed every 5 seconds showing average latencies by operation type.

## Project Structure

```
.
├── setup-demo.sh           # Automated setup script
├── disrupt.sh              # Cluster disruption tool
├── demo.py                 # Main IAM demo application
├── demo-env.sh             # Generated environment variables (source this)
├── requirements.txt        # Python dependencies
├── docker-compose.yml      # Prometheus + Grafana
├── prometheus.yml          # Prometheus configuration
├── iam/                    # IAM application code
│   ├── __init__.py
│   ├── transactions.py     # Database operations
│   └── helpers.py          # Stats tracking, metrics, retry logic
├── sql/                    # Database schema and data
│   ├── schema.sql          # Multi-region schema definition
│   ├── generate_data.py    # Demo data generator
│   └── data.sql            # Generated data (created by setup)
└── grafana/                # Grafana configuration
    ├── provisioning/
    │   ├── datasources/
    │   │   └── prometheus.yml
    │   └── dashboards/
    │       └── dashboards.yml
    └── dashboards/         # Five pre-configured dashboards
        ├── iam-demo.json
        ├── iam-demo-by-region.json
        ├── iam-demo-comparison.json
        ├── iam-demo-regional-overview.json
        └── iam-demo-regional-split.json
```

## Anomaly Detection Feature

The demo includes ML-based anomaly detection for login patterns:

- **Vector embeddings** representing user login behavior (time of day, day of week, region)
- **Cosine similarity search** using PostgreSQL vector extensions
- **Severity levels:** Low (0.3-0.5), Medium (0.5-0.7), High (>0.7)
- **Optional learning mode:** Updates user profiles from normal logins

**Configuration** (environment variables):
```bash
ENABLE_ANOMALY_DETECTION=true    # Enable/disable feature
ANOMALY_THRESHOLD=0.3            # Minimum score to flag
ANOMALY_INJECTION_RATE=0.10      # Percentage of anomalous logins (for demo)
ENABLE_PROFILE_LEARNING=false    # Learn from normal logins
LEARNING_RATE=0.1                # Weight for new observations
```

## Grafana Dashboards

Five dashboards are included, each with a different visualization style:

1. **iam-demo.json** - Comprehensive overview with multiple panel types
2. **iam-demo-by-region.json** - Big stat panels mimicking console output
3. **iam-demo-comparison.json** - All regions overlaid on same graphs
4. **iam-demo-regional-overview.json** - All metrics per region in one view
5. **iam-demo-regional-split.json** - Separate Y-axes for fast/slow operations

All dashboards auto-update with your actual region names during setup.

## Troubleshooting

### Setup Script Issues

**"Error: CRDB_CERT_URL environment variable is not set"**
- Environment variables should be in `.bashrc` (set by Terraform)
- Run: `source ~/.bashrc`

**"Error: Failed to add IP to allowlist"**
- Check API key has "Cluster Administrator" role
- Verify cluster ID is correct (UUID from cluster URL)
- Check API key hasn't expired

**"Error: Failed to install schema"**
- Verify cluster is accessible from this server
- Check SQL user credentials are correct
- Ensure cluster regions match `DATABASE_REGIONS`

### Demo App Issues

**"Connection lost, attempting to reconnect..."**
- Expected during region disruptions
- If persistent, check cluster status in Cloud Console
- Verify IP allowlist includes this server's public IP

**Fast single-node failure detection**
- The app uses aggressive client-side connection settings to notice dead node connections sooner during the demo.
- Current settings in `demo.py` include `connect_timeout=2`, `statement_timeout=2500`, and `tcp_user_timeout=2500`.
- This improves how quickly the app realizes it needs to reconnect after a node disappears, while keeping the existing retry loop behavior.

**No metrics in Grafana**
- Check demo app is running: `ps aux | grep demo.py`
- Verify Prometheus can scrape: `http://<ip>:9090/targets`
- Check demo app metrics endpoint: `curl http://localhost:8000/metrics`

### Disruption Issues

**"Error: Node not found in cluster"**
- Run `./disrupt.sh list` to see available nodes
- Node names change when pods restart

**Disruption doesn't clear**
- Try: `./disrupt.sh clear` again
- Check Cloud Console for active disruptions
- Verify API key has proper permissions

## Advanced Usage

### Running Demo App in Background

After setup, you can manage the demo app manually:

```bash
# Stop current demo
pkill -f demo.py

# Run in background
source demo-env.sh
nohup ./demo.py > /dev/null 2>demo.err &

# Check errors
tail -f demo.err

# Stop
pkill -f demo.py
```

### Re-running Setup with Different Regions

The setup script is idempotent and can be run multiple times:

```bash
# Update DATABASE_REGIONS in .bashrc
export DATABASE_REGIONS="new-region1,new-region2,new-region3"

# Re-run setup
./setup-demo.sh "<password>" "<api-key>" "<cluster-id>"
```

Original backup files (`.bak.original`) ensure safe re-runs.

## Technologies Used

- **CockroachDB Cloud Advanced** - Multi-region distributed SQL database
- **Python 3.11** - Application runtime
- **SQLAlchemy 2.0** - SQL toolkit and ORM
- **psycopg3** - PostgreSQL adapter (not psycopg2)
- **sqlalchemy-cockroachdb** - CockroachDB dialect for SQLAlchemy
- **prometheus-client** - Metrics export
- **Prometheus** - Metrics collection and monitoring
- **Grafana** - Metrics visualization
- **Docker + Docker Compose** - Container runtime

## Key Features

- ✅ **Fully automated setup** - One script configures everything
- ✅ **Idempotent** - Safe to re-run with different regions
- ✅ **IP allowlist automation** - Automatic via Cloud API
- ✅ **Region discovery** - Auto-detects cluster topology
- ✅ **Real-time metrics** - Prometheus + Grafana integration
- ✅ **Anomaly detection** - ML-based login pattern analysis
- ✅ **Simple disruption testing** - Easy region failure simulation
- ✅ **Professional dashboards** - Five visualization options

## Notes for Presenters

- This demo is designed for high-stakes presentations (Ory, Teleport executives)
- **Focus on resiliency**, not IAM complexity
- **Key message:** "IAM systems need to be always available - CockroachDB makes that possible"
- The retry loop (vs failover) clearly demonstrates regional isolation
- Follower reads (AOST) show even lower latency for slightly stale data
- Use `disrupt.sh` during presentation for dramatic effect

## License

This demo is provided for demonstration purposes.

# Reader's Digest Condensed Version

- [x] Create the cluster -- wait for the cluster creation to complete.
- [x] turn off backups
- [x] set the maintenance window (Monday at 4am UTC / Sunday 9pm PT) and delay upgrades for 90 days.  
- [x] Set delete protection on.  
- [x] Find your API key and choose "Edit Roles" from the Action List.  Add a new role with scope of the cluster (nollen-iam-demo for example) and role of "Cluster Admin".
- [x] Create a user / copy password to sql_notes.txt
- [x] Copy the cluster id (top of cluster UI) and paste into sql_notes.txt.  Both in the export - variable and in the setup-demo command!   
- [x] Using notskope.com, get both IPs and add them to the IP Allow List in the Cluster UI
- [x] Check terraform.tfvars to be sure the regions match your cluster regions
- [x] Using the connect string for linux, update terraform.tvfars with the connection string for - each region.  Be sure to match the region with the correct string in terraform.tfvars.
- [x] You may want to be sure the CRDB version in terraform.tfvars matches the version of your - cluster.
- [x] Roll out the terraform
- [x] Connect to the primary region app node
- [x] `tail -f /var/log/cloud-init-output.log` until "complete" message with "Up ... seconds"
- [x] Reconnect or source the .bashrc
- [x] `cd` to `crdb-multi-region-iam-demo`
- [x] paste in the  top line from sql_notes.txt (setup-demo.sh).  This will kick off the setup, including the database schema.
- [x] ssh to each of the other nodes and paste the setup-demo same line.
- Open 5 Firefox http tabs:
  - [ ] Slides
  - [ ] Database UI
  - [ ] cloudping.co
  - [x] Primary Cluster IP  + 9090 navigate to status/target health
  - [x] Primary Cluster IP + 3000 (admin/admin) / Change the Time Range to now -2m
- [x] Run Queries in sql_notes to have the information handy, including system.locations inserts!  
  - [x] source demo-env.sh
  - [x] CRDB
  - [x] Install system.locations!
- Open cloudping and Database UI
- chmod +x
  - [ ] rollback-online-schema-change.sh
  - [ ] run-online-schema-change.sh
- Open https://docs.google.com/presentation/d/1JCN_tjBfSOfS37ht0zshIOGdsOfJZRPHdlk_ybJM8yo/edit?slide=id.g2b6c6946b7e_0_2297#slide=id.g2b6c6946b7e_0_2297




Close all non-essential tabs
1. The "Native Shortcut" (Fastest)
- This is the "old school" way, but it's still the most reliable and doesn't require any setup.
- To Save: Press Ctrl + Shift + D (Windows) or Cmd + Shift + D (Mac).
- Action: Chrome will ask you to name a folder. Call it "Pre-Demo Tabs" and save it to your Bookmarks Bar.
- To Reopen: When your demo is over, just right-click that folder in your Bookmarks Bar and select "Open All in New Window."

Turn on Do Not Disturb and Close Slack
