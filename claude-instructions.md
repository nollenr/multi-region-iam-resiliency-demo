To start with, if you are unable to read any of the folders or github repos mentioned below, we need to fix that first.   

I want to create a new MR demo similiar to this one:
C:\Users\RonNollen\Documents\Ron's Stuff\multi-region-demo-j4-adapted

tools:
CockroachDB 
latest version of python
psycopg (psycopg3)
sqlalchemy

Demo:
Instead of the movr demo, I need an IAM demo that gives a nod to Ory and Teleport.   User authentication and logging is one of the verticals that runs really well.

Unless you can think of something better, I would like the demo to run the same way as the previous one.   I'll run a multi-region CRDB cluster and one copy of the code in each region (each region has an app server).  When one of the regions is taken down, the app code in that region should not connect to a surviving region, instead it should display a message every few seconds that it is trying to connect.  When the region is brought back to life, the app in that region should reconnect and start processing again.   As in the previous demo, we should use global tables, regional tables and regional-by-row tables.   We should also use follower reads.    Displaying the latencies in each region, as we did in the previous demo is a must, but you can use whatever mechanism is best to do that -- previously we used demostats and timers -- use whatever makes sense especially if there are tools that make sense.


I'll be creating the CRDB Cluster with my own terraform scripts availble here -- you don't have to worry about that.   
https://github.com/nollenr/AWS-Terraform-CRDB-Multi-Region which in turn, pulls from here:
https://github.com/nollenr/AWS-Terraform-CRDB-Module

Later, we'll figure out what needs to be changed in the rollout of the app node in each region to install this demo as part of the TF and any dependancies so that anyone can roll it out easily.


Structure:
You can use whatever folder structure makes sense, there is no need to follow what was done in the previous demo.

Demo data:
Create data as a bunch of multi-value insert statements.  I don't want to create dependancies on anything here. A script that creates the database, creates the schema and the data is very important.   There should be plenty of demo data (50k rows).    Allow the database to generate the UUIDs (using gen_random_uuid()) whenever possible instead of supplying UUIDs as part of the insert statement.  

Other Thoughts:
One of the things that was great about the previous demo, was the simplicity in rolling it out and making it run.   The number of hoops that needed to be jumped through was minimal to make it run -- the TF did a lot of the heavy lifting and provided env variables that allowed the demo to "just run".

This demo needs to be absolutely bullet proof -- it will be run in front of a very large audience and the veeps of both Ory and Teleport will be in attendance.  So keeping it relatively simple is key so that there is less that can go wrong.   That being said, if there are test scripts that need to be created, please do.    

Remember that this is all being generated to run on CockroachDB, not standard Postgres.  Please keep that in mind when generating code.   

Demo Flow:
For sure users, maybe roles, authentication session, audit logs?  Given a user and a role, log the user in, have them do some stuff and log out?   Don't take that as gospel.  Let's do what makes sense, but keep it simple, so that it is easy to explain and easy to see what's going on.  The focus of the demo is resiliency, not how IAM works -- but I want to demonstrate how authentication can continue to function even when a region is taken out of commission.  

Regions:
The regions should be passed in as a parameter wherever they're needed.   The defaults should be 3 regions: us-east-1, us-east-2, us-west-2.  


--------------------------------
Complete Demo Recreation Instructions
Core Requirements
Create a multi-region IAM demo for CockroachDB to demonstrate resiliency during region failures. Target audience: Ory and Teleport executives (high-stakes).

Architecture:

CockroachDB Advanced cluster across 3 AWS regions: aws-us-east-1, aws-us-east-2, aws-us-west-2
One Python 3.11 application instance per region
Each app connects ONLY to local CockroachDB nodes via HAProxy
When region fails: app enters retry loop (does NOT failover)
When region recovers: app automatically reconnects
Optional: Grafana + Prometheus on one EC2 instance for visualization
Technology Stack:

Python 3.11
SQLAlchemy 2.0+
psycopg3 (psycopg[binary]>=3.1) - NOT psycopg2
sqlalchemy-cockroachdb dialect
prometheus-client>=0.19.0
Docker + Docker Compose for Grafana/Prometheus
Database Schema - Three Table Types
1. Global Tables (users, roles):

Fast reads from any region (local replica)
Slower writes (require consensus across regions)
Use for data that must be consistent everywhere
2. Regional Tables (sessions):

Fast reads/writes in primary region
Include AOST (follower reads) for even lower latency
Sessions table should have region column set to gateway_region()::STRING on INSERT
3. Regional-by-Row Tables (audit_logs):

Each row stored in its designated region
Fast local reads and writes
Use crdb_region column (auto-added by CRDB for REGIONAL BY ROW tables)
Do NOT manually add a region column - CRDB does this automatically
Demo Flow (Per Iteration)
Each iteration simulates a user session with these operations:

Login - Create session (regional write)
Read user info (global read)
Update last login (global write)
Read role/permissions (global read)
Perform 5 actions - Create audit logs (RBR writes)
Logout - End session (regional write)
Read recent audit entry (RBR read)
Read session (regional read - current)
Read session with AOST (regional follower read)
Stats displayed every 5 seconds showing avg latency for:

Global tables: reads/writes
Regional tables: reads/writes/AOST
RBR tables: reads/writes
Key Technical Details
Connection & Retry Logic:

Infinite retry on connection errors (sleep 1 second between attempts)
Retry up to 10 times on serialization failures (40001) and transient errors (40003)
Console output: "Connection lost, attempting to reconnect..."
Database Functions:

Auto-detect region via gateway_region() - NO manual region config in demo.env
Use CAST(gateway_region() AS crdb_internal_region) when comparing regions
Use CAST(:metadata AS JSONB) not ::JSONB for SQLAlchemy compatibility
Sessions region: gateway_region()::STRING (cast to STRING, not crdb_internal_region)
Schema Setup:

Use \set errexit=false/true around ADD REGION statements for Cloud compatibility
Audit_logs uses REGIONAL BY ROW WITHOUT explicit region column
Regions: aws-us-east-1, aws-us-east-2, aws-us-west-2
Data Generation:

Command-line arguments: --regions (list), --output (file path)
Generate 50k+ total rows: 1,000 users, 15 roles, 5,000 sessions, 50,000 audit logs
Multi-value INSERT statements (1000 rows per batch)
Distribute audit_logs evenly across regions using round-robin
Cast crdb_region: CAST('aws-us-east-1' AS crdb_internal_region)
Quote UUIDs: detect with hasattr(val, 'hex') and wrap in quotes
Quote timestamps: detect with isinstance(val, datetime) and wrap in quotes
Shebang: #!/usr/bin/env python3.11
Environment Variables:

Check for CRDB_URL first, then DB_URI, then use default
Connection string: cockroachdb://root@<haproxy>:26257/iam_demo?application_name=iam_demo
Region auto-detected, no manual configuration
METRICS_PORT for Prometheus (default: 8000)
Prometheus Integration
Metrics Exposed:

operation_latency - Histogram with labels: operation, table_type, region
operation_counter - Counter with labels: operation, table_type, region
region_status - Gauge with labels: region
HTTP server on port 8000 (configurable via METRICS_PORT env var)
Helpers.py Updates:


from prometheus_client import Histogram, Counter, Gauge

operation_latency = Histogram(...)
operation_counter = Counter(...)
region_status = Gauge(...)

# In add_to_stats():
operation_latency.labels(operation=op_name, table_type=table_type, region=region).observe(time_ms / 1000.0)
operation_counter.labels(operation=op_name, table_type=table_type, region=region).inc()

# In set_connection_info():
region_status.labels(region=region).set(1)
Demo.py Updates:


from prometheus_client import start_http_server
METRICS_PORT = int(os.getenv('METRICS_PORT', '8000'))
start_http_server(METRICS_PORT)
Low Cardinality Design:

Only use bounded labels: operation (9 types), table_type (3 types), region (3 regions)
NEVER use user_id, session_id, or other unbounded values as labels
Total time series: ~489 (completely safe)
Grafana + Prometheus Setup
Docker Compose Structure:

Prometheus scrapes all 3 regional apps on port 8000 every 5 seconds
Grafana connects to Prometheus and displays dashboards
Both run as Docker containers
Volumes for persistent data
Critical Configuration Files:

grafana/provisioning/datasources/prometheus.yml:

uid: prometheus  # CRITICAL - must match dashboard expectations
url: http://prometheus:9090  # Use service name, not localhost
prometheus.yml:
Replace <REGION1_APP_HOST>, <REGION2_APP_HOST>, <REGION3_APP_HOST> with actual IPs
Use localhost:8000 if Prometheus is on same host as one app
Label conflict: Prometheus renames region label to exported_region
All dashboard queries MUST use exported_region not region
File Permissions:


chmod 644 grafana/dashboards/*.json
Security Groups:

Allow port 8000 inbound from Prometheus host to all app servers
Allow ports 3000 (Grafana) and 9090 (Prometheus) as needed
Dashboard Loading:

Datasource UID mismatch causes "No data" - must be uid: prometheus
If dashboard doesn't load, delete Grafana volume and restart
Files must be readable (chmod 644) before starting Grafana
Five Grafana Dashboards
Create these 5 dashboards in grafana/dashboards/:

iam-demo.json - "CockroachDB IAM Multi-Region Demo"

Original detailed dashboard with multiple panel types
Graphs, gauges, bar charts showing all metrics
Good for comprehensive view
iam-demo-by-region.json - "IAM Demo - By Region"

Three sections (one per region)
Stat panels (big numbers) for each metric
Mirrors console output format
Easy to read, clear per-region view
iam-demo-comparison.json - "IAM Demo - Region Comparison"

7 graph panels + 3 status gauges
Each panel shows all 3 regions as different lines
Best for seeing region failures/recovery
Great for presentations
iam-demo-regional-overview.json - "IAM Demo - Regional Overview"

3 graph panels (one per region) + 3 status gauges
Each region panel shows all 7 metrics as different lines
Complete picture per region at a glance
iam-demo-regional-split.json - "IAM Demo - Regional Split View"

6 graph panels + 3 status gauges
Top row: Fast operations (Global reads, Regional, RBR) - one panel per region
Middle row: Global Writes only - one panel per region (separate Y-axis scale)
Bottom row: Region status gauges
Best for avoiding Y-axis scale issues (Global writes are 100x slower)
All graphs:

Use milliseconds (multiply by 1000)
Use exported_region not region in queries
Smooth line interpolation
Show mean and last values in legends
5 second refresh
Project Structure

.
├── demo.py                  # Main application (#!/usr/bin/env python3.11)
├── demo.env                 # Environment variable template
├── requirements.txt         # Python dependencies
├── docker-compose.yml       # Grafana + Prometheus containers
├── prometheus.yml           # Prometheus scrape config
├── README.md               
├── iam/
│   ├── __init__.py
│   ├── transactions.py     # All database operations
│   └── helpers.py          # Stats, timing, retry logic, Prometheus metrics
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── prometheus.yml  # uid: prometheus (CRITICAL)
│   │   └── dashboards/
│   │       └── dashboards.yml
│   └── dashboards/
│       ├── iam-demo.json
│       ├── iam-demo-by-region.json
│       ├── iam-demo-comparison.json
│       ├── iam-demo-regional-overview.json
│       └── iam-demo-regional-split.json
└── sql/
    ├── schema.sql          # Multi-region schema
    ├── generate_data.py    # Data generator (#!/usr/bin/env python3.11)
    └── data.sql            # Generated (not in git)
Installation & Setup Steps
Amazon Linux 2:


sudo yum install -y docker python3.11
sudo service docker start
sudo usermod -a -G docker ec2-user
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
Amazon Linux 2023:


sudo yum install -y docker python3.11
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -a -G docker ec2-user
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
Generate data:


python3 sql/generate_data.py --regions aws-us-east-1 aws-us-east-2 aws-us-west-2
Load schema and data:


cockroach sql --url "..." < sql/schema.sql
cockroach sql --url "..." < sql/data.sql
Configure Prometheus:

Edit prometheus.yml with actual app IPs
Use localhost:8000 if Prometheus on same host as app
Security groups:

Port 8000: From Prometheus to all app servers
Port 3000, 9090: For Grafana/Prometheus access
Set permissions and start:


chmod 644 grafana/dashboards/*.json
docker-compose up -d
Start apps:


export CRDB_URL="cockroachdb://root@<haproxy>:26257/iam_demo?application_name=iam_demo"
./demo.py
Key Fixes & Gotchas
Label conflict: Prometheus renames metric's region to exported_region when prometheus.yml also sets region label
Datasource UID: Must be uid: prometheus or dashboard shows "No data"
File permissions: Dashboard JSON files need chmod 644 or Grafana can't read them
Volume persistence: Delete iam_demo_v2_grafana-data volume to force fresh load
Region auto-detection: Use gateway_region(), don't require manual region config
Node display: Show "N/A (Serverless)" when node_id is None
Security groups: Port 8000 must be open from Prometheus to apps
Demo Message
Focus on resiliency not IAM complexity. Key message: "IAM systems need to be always available - CockroachDB makes that possible."

When a region fails:

That region's app shows "Connection lost, attempting to reconnect..."
Other regions continue operating normally
Dashboard shows that region's line drop to zero
Status gauge turns red
When region recovers:

App automatically reconnects
Metrics resume
May see brief latency spike during leaseholder rebalancing