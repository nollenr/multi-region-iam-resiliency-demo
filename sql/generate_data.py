#!/usr/bin/env python3.11
"""
Generate demo data for IAM multi-region demo
Creates SQL INSERT statements with 50k+ rows total
"""

import argparse
import random
from datetime import datetime, timedelta
from uuid import uuid4

# Configuration
NUM_USERS = 1000
NUM_ROLES = 15
NUM_SESSIONS = 5000
NUM_AUDIT_LOGS = 50000

# Default regions - can be overridden via command line
DEFAULT_REGIONS = ['aws-us-east-1', 'aws-us-east-2', 'aws-us-west-2']

ACTIONS = [
    'login', 'logout', 'view_dashboard', 'update_profile', 'change_password',
    'view_report', 'create_resource', 'delete_resource', 'modify_resource',
    'grant_permission', 'revoke_permission', 'view_audit_log', 'export_data',
    'configure_settings', 'run_query', 'upload_file', 'download_file'
]

RESOURCES = [
    'user_profile', 'dashboard', 'reports', 'settings', 'audit_logs',
    'users', 'roles', 'permissions', 'sessions', 'resources', 'data_export',
    'analytics', 'monitoring', 'alerts', 'integrations'
]

ROLE_TEMPLATES = [
    ('admin', 'System Administrator', ['*']),
    ('security_admin', 'Security Administrator', ['user_management', 'audit_logs', 'security_settings']),
    ('user_manager', 'User Manager', ['user_read', 'user_write', 'role_assignment']),
    ('auditor', 'Auditor', ['audit_read', 'report_read']),
    ('developer', 'Developer', ['resource_read', 'resource_write', 'api_access']),
    ('analyst', 'Data Analyst', ['report_read', 'data_export', 'analytics']),
    ('operator', 'System Operator', ['resource_read', 'monitoring', 'alerts']),
    ('support', 'Support Staff', ['user_read', 'ticket_management']),
    ('viewer', 'Read-only Viewer', ['dashboard_read', 'report_read']),
    ('manager', 'Manager', ['user_read', 'report_read', 'approve_requests']),
    ('finance', 'Finance', ['financial_read', 'financial_write', 'export_data']),
    ('hr', 'Human Resources', ['user_read', 'user_write', 'hr_data']),
    ('compliance', 'Compliance Officer', ['audit_read', 'compliance_reports', 'policy_management']),
    ('guest', 'Guest User', ['dashboard_read']),
    ('api_user', 'API User', ['api_access', 'resource_read'])
]

def generate_timestamp(days_ago_max=365):
    """Generate a random timestamp within the last N days"""
    days_ago = random.randint(0, days_ago_max)
    hours_ago = random.randint(0, 23)
    minutes_ago = random.randint(0, 59)
    return datetime.now() - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)

def sql_escape(s):
    """Escape single quotes for SQL"""
    return s.replace("'", "''")

def write_inserts(file, table, columns, rows, batch_size=1000):
    """Write INSERT statements in batches"""
    file.write(f"\n-- Inserting {len(rows)} rows into {table}\n")

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        file.write(f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n")

        for j, row in enumerate(batch):
            values = []
            for col_idx, val in enumerate(row):
                col_name = columns[col_idx] if col_idx < len(columns) else None

                if val is None:
                    values.append('NULL')
                elif isinstance(val, str):
                    # Special handling for crdb_region column - cast to crdb_internal_region
                    if col_name == 'crdb_region':
                        values.append(f"CAST('{sql_escape(val)}' AS crdb_internal_region)")
                    else:
                        values.append(f"'{sql_escape(val)}'")
                elif isinstance(val, (dict, list)):
                    import json
                    values.append(f"'{json.dumps(val)}'::JSONB")
                elif hasattr(val, 'hex'):  # UUID object
                    values.append(f"'{str(val)}'")
                elif isinstance(val, datetime):  # datetime object
                    values.append(f"'{str(val)}'")
                else:
                    values.append(str(val))

            suffix = ',' if j < len(batch) - 1 else ';'
            file.write(f"  ({', '.join(values)}){suffix}\n")

        file.write("\n")

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Generate demo data for IAM multi-region demo')
    parser.add_argument('--regions', '-r', nargs='+',
                        default=DEFAULT_REGIONS,
                        help=f'Space-separated list of regions (default: {" ".join(DEFAULT_REGIONS)})')
    parser.add_argument('--output', '-o',
                        default='sql/data.sql',
                        help='Output file path (default: sql/data.sql)')
    args = parser.parse_args()

    REGIONS = args.regions
    output_file = args.output

    print(f"Generating demo data...")
    print(f"  Regions: {', '.join(REGIONS)}")
    print(f"  Users: {NUM_USERS}")
    print(f"  Roles: {NUM_ROLES}")
    print(f"  Sessions: {NUM_SESSIONS}")
    print(f"  Audit Logs: {NUM_AUDIT_LOGS}")
    print(f"  Total rows: {NUM_USERS + NUM_ROLES + NUM_SESSIONS + NUM_AUDIT_LOGS}")

    with open(output_file, 'w') as f:
        f.write("-- IAM Demo Data\n")
        f.write("-- Auto-generated data for multi-region IAM demo\n")
        f.write(f"-- Generated: {datetime.now().isoformat()}\n\n")
        f.write("USE iam_demo;\n\n")

        # Generate roles
        print("Generating roles...")
        role_data = []
        role_ids = []
        for role_name, description, permissions in ROLE_TEMPLATES:
            role_id = uuid4()
            role_ids.append(role_id)
            created_at = generate_timestamp(730)  # Within last 2 years
            role_data.append([
                role_id,
                role_name,
                description,
                {'permissions': permissions},
                created_at
            ])

        write_inserts(f, 'roles',
                     ['id', 'role_name', 'description', 'permissions', 'created_at'],
                     role_data)

        # Generate users
        print("Generating users...")
        user_data = []
        user_ids = []
        for i in range(NUM_USERS):
            user_id = uuid4()
            user_ids.append(user_id)
            username = f"user{i:04d}"
            email = f"{username}@example.com"
            password_hash = f"$2b$12${''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=50))}"
            created_at = generate_timestamp(730)
            last_login = generate_timestamp(30) if random.random() > 0.1 else None
            status = 'active' if random.random() > 0.05 else 'inactive'

            user_data.append([
                user_id,
                username,
                email,
                password_hash,
                created_at,
                last_login,
                status
            ])

        write_inserts(f, 'users',
                     ['id', 'username', 'email', 'password_hash', 'created_at', 'last_login', 'status'],
                     user_data)

        # Generate user_roles assignments
        print("Generating user-role assignments...")
        user_role_data = []
        for user_id in user_ids:
            # Each user gets 1-3 roles
            num_roles = random.randint(1, 3)
            assigned_roles = random.sample(role_ids, num_roles)
            for role_id in assigned_roles:
                assigned_at = generate_timestamp(365)
                user_role_data.append([user_id, role_id, assigned_at])

        write_inserts(f, 'user_roles',
                     ['user_id', 'role_id', 'assigned_at'],
                     user_role_data)

        # Generate sessions
        print("Generating sessions...")
        session_data = []
        session_ids = []
        for i in range(NUM_SESSIONS):
            session_id = uuid4()
            session_ids.append(session_id)
            user_id = random.choice(user_ids)
            region = random.choice(REGIONS)
            login_time = generate_timestamp(90)

            # 80% of sessions are completed (have logout time)
            if random.random() > 0.2:
                logout_time = login_time + timedelta(minutes=random.randint(5, 240))
                status = 'completed'
            else:
                logout_time = None
                status = 'active'

            ip_address = f"{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"
            user_agent = random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            ])

            session_data.append([
                session_id,
                user_id,
                region,
                login_time,
                logout_time,
                status,
                ip_address,
                user_agent
            ])

        write_inserts(f, 'sessions',
                     ['id', 'user_id', 'region', 'login_time', 'logout_time', 'status', 'ip_address', 'user_agent'],
                     session_data)

        # Generate audit logs (50k rows)
        # Note: ID is omitted - database generates it automatically
        # crdb_region is explicitly set to distribute data evenly across regions
        print("Generating audit logs...")
        audit_data = []
        for i in range(NUM_AUDIT_LOGS):
            user_id = random.choice(user_ids)
            session_id = random.choice(session_ids) if random.random() > 0.1 else None
            action = random.choice(ACTIONS)
            resource = random.choice(RESOURCES)
            result = 'success' if random.random() > 0.05 else 'failure'
            timestamp = generate_timestamp(90)
            # Distribute audit logs evenly across regions
            region = REGIONS[i % len(REGIONS)]
            metadata = {
                'user_agent': random.choice(['web', 'mobile', 'api']),
                'duration_ms': random.randint(10, 5000)
            }

            audit_data.append([
                user_id,
                session_id,
                action,
                resource,
                result,
                timestamp,
                region,
                metadata
            ])

        write_inserts(f, 'audit_logs',
                     ['user_id', 'session_id', 'action', 'resource', 'result', 'timestamp', 'crdb_region', 'metadata'],
                     audit_data, batch_size=1000)

    print(f"\nData generation complete!")
    print(f"Output written to: {output_file}")
    total_rows = NUM_USERS + NUM_ROLES + len(user_role_data) + NUM_SESSIONS + NUM_AUDIT_LOGS
    print(f"Total rows: {total_rows:,}")

if __name__ == '__main__':
    main()
