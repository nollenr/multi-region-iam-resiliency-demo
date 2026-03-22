#!/usr/bin/env python3.11
"""
Generate demo data for IAM multi-region demo
Creates SQL INSERT statements with 50k+ rows total
"""

import argparse
import math
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

def create_behavior_vector(hour_of_day, day_of_week, primary_region_idx,
                          time_since_last_login_hours, avg_session_duration_hours,
                          logins_per_day, failure_rate, avg_actions_per_session):
    """
    Create an 8-dimensional behavior vector for a user profile.

    Vector dimensions:
    1. Hour of day (normalized 0-1)
    2. Day of week (normalized 0-1)
    3. Region consistency (0-1, based on primary region index)
    4. Time since last login (log-scaled, normalized)
    5. Session duration pattern (normalized)
    6. Login frequency (normalized)
    7. Recent failure rate (0-1)
    8. Activity level (normalized)
    """
    # Normalize hour of day (0-23 -> 0-1)
    v1 = hour_of_day / 23.0

    # Normalize day of week (0-6 -> 0-1)
    v2 = day_of_week / 6.0

    # Region consistency - encode primary region (0, 1, or 2 -> normalized)
    v3 = primary_region_idx / 2.0

    # Time since last login (log scale to handle wide range)
    # Typical range: 1 hour to 168 hours (1 week)
    # log(1) = 0, log(168) ~= 5.12
    v4 = min(1.0, math.log(max(1, time_since_last_login_hours)) / 5.12)

    # Session duration (normalize to 0-1, typical range 0.1 to 4 hours)
    v5 = min(1.0, avg_session_duration_hours / 4.0)

    # Login frequency (normalize to 0-1, typical range 0.1 to 10 logins/day)
    v6 = min(1.0, logins_per_day / 10.0)

    # Failure rate (already 0-1)
    v7 = min(1.0, max(0.0, failure_rate))

    # Activity level (normalize to 0-1, typical range 1 to 50 actions/session)
    v8 = min(1.0, avg_actions_per_session / 50.0)

    return [v1, v2, v3, v4, v5, v6, v7, v8]

def format_vector(vector):
    """Format a vector as a SQL array literal"""
    return '[' + ','.join(str(v) for v in vector) + ']'

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
                    # Special handling for vector columns - format as array literal
                    elif col_name and 'vector' in col_name.lower():
                        values.append(f"'{val}'")
                    else:
                        values.append(f"'{sql_escape(val)}'")
                elif isinstance(val, dict):
                    import json
                    values.append(f"'{json.dumps(val)}'::JSONB")
                elif isinstance(val, list) and col_name and 'vector' in col_name.lower():
                    # Vector column - format as array literal
                    vector_str = '[' + ','.join(str(v) for v in val) + ']'
                    values.append(f"'{vector_str}'")
                elif isinstance(val, list):
                    # Regular list -> JSONB
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

        # Generate user behavior profiles (8D vectors)
        # Create different user categories with distinct patterns
        print("Generating user behavior profiles...")
        profile_data = []

        for i, user_id in enumerate(user_ids):
            # Categorize users into different behavior patterns
            category = i % 5

            if category == 0:
                # Category 0: Business hours users (9-5, weekdays, Region 1)
                profile_type = '9-5 workers (Region 1)'
                hour = random.gauss(13, 3)  # Center around 1 PM
                day = random.randint(0, 4)  # Weekdays only
                region_idx = 0  # Primary region 1
                time_since_last = random.gauss(24, 8)  # Daily login
                session_duration = random.gauss(2, 0.5)  # ~2 hour sessions
                login_freq = random.gauss(1, 0.2)  # ~1 login/day
                failure_rate = 0.02  # Low failure rate
                activity = random.gauss(15, 5)  # Moderate activity

            elif category == 1:
                # Category 1: Business hours users (9-5, weekdays, Region 2)
                profile_type = '9-5 workers (Region 2)'
                hour = random.gauss(13, 3)
                day = random.randint(0, 4)
                region_idx = 1  # Primary region 2
                time_since_last = random.gauss(24, 8)
                session_duration = random.gauss(2, 0.5)
                login_freq = random.gauss(1, 0.2)
                failure_rate = 0.02
                activity = random.gauss(15, 5)

            elif category == 2:
                # Category 2: Night shift users (Region 3)
                profile_type = 'Night shift (Region 3)'
                hour = random.gauss(2, 2)  # Center around 2 AM
                day = random.randint(0, 6)  # Any day
                region_idx = 2  # Primary region 3
                time_since_last = random.gauss(24, 8)
                session_duration = random.gauss(3, 0.5)  # Longer sessions
                login_freq = random.gauss(1, 0.2)
                failure_rate = 0.03
                activity = random.gauss(20, 5)  # Higher activity

            elif category == 3:
                # Category 3: Global travelers (inconsistent patterns)
                profile_type = 'Global travelers'
                hour = random.uniform(0, 23)  # Any time
                day = random.randint(0, 6)  # Any day
                region_idx = random.randint(0, 2)  # Random region
                time_since_last = random.gauss(48, 24)  # Less frequent
                session_duration = random.gauss(1, 0.3)  # Shorter sessions
                login_freq = random.gauss(0.5, 0.2)  # ~2 days between logins
                failure_rate = 0.05  # Higher failure rate
                activity = random.gauss(10, 3)  # Lower activity

            else:  # category == 4
                # Category 4: Irregular users (weekends, odd hours)
                profile_type = 'Irregular users'
                hour = random.choice([random.gauss(9, 2), random.gauss(21, 2)])  # Morning or evening
                day = random.randint(5, 6)  # Weekends
                region_idx = random.randint(0, 2)
                time_since_last = random.gauss(72, 48)  # Weekly-ish
                session_duration = random.gauss(1.5, 0.5)
                login_freq = random.gauss(0.3, 0.1)
                failure_rate = 0.04
                activity = random.gauss(12, 4)

            # Clamp values to valid ranges
            hour = max(0, min(23, hour))
            day = max(0, min(6, int(day)))
            time_since_last = max(1, time_since_last)
            session_duration = max(0.1, session_duration)
            login_freq = max(0.1, login_freq)
            failure_rate = max(0, min(1, failure_rate))
            activity = max(1, activity)

            # Create the behavior vector
            vector = create_behavior_vector(
                hour_of_day=hour,
                day_of_week=day,
                primary_region_idx=region_idx,
                time_since_last_login_hours=time_since_last,
                avg_session_duration_hours=session_duration,
                logins_per_day=login_freq,
                failure_rate=failure_rate,
                avg_actions_per_session=activity
            )

            profile_data.append([
                user_id,
                vector,  # behavior_vector
                'static',  # profile_type
                100,  # sample_count (synthetic baseline)
                generate_timestamp(30)  # last_updated
            ])

        write_inserts(f, 'user_behavior_profiles',
                     ['user_id', 'behavior_vector', 'profile_type', 'sample_count', 'last_updated'],
                     profile_data)

    print(f"\nData generation complete!")
    print(f"Output written to: {output_file}")
    total_rows = NUM_USERS + NUM_ROLES + len(user_role_data) + NUM_SESSIONS + NUM_AUDIT_LOGS + NUM_USERS
    print(f"Total rows: {total_rows:,}")
    print(f"  Behavior profiles: {NUM_USERS}")

if __name__ == '__main__':
    main()
