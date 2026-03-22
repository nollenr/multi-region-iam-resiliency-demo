#!/usr/bin/env python3.11
"""
CockroachDB Multi-Region IAM Demo

Demonstrates multi-region table types and resiliency:
- Global tables (users, roles) - fast reads, slower writes
- Regional tables (sessions) - fast reads/writes in primary region
- Regional-by-row tables (audit_logs) - each row stored in its region

Focus: Showing how IAM systems can survive region failures with CockroachDB
"""

from datetime import datetime as dt
import os
from random import randint, choice
import signal
import sys
from uuid import uuid4

from prometheus_client import start_http_server
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine as SAEngine

from iam.transactions import (
    get_gateway_region, get_node_id,
    get_user, get_users, update_last_login,
    get_role, get_roles, get_user_roles,
    create_session, end_session, get_session, get_session_aost,
    create_audit_log, get_recent_audit_log
)
from iam.helpers import DemoStats, DemoTimer, run_transaction

# Configuration
STATS_INTERVAL_SECS = 5
NUM_AUDIT_ACTIONS = 5  # Number of audit log entries per session
METRICS_PORT = int(os.getenv('METRICS_PORT', '8000'))  # Port for Prometheus metrics endpoint

# Check for CRDB_URL first, then DB_URI, then use default
DB_URI = os.getenv('CRDB_URL') or os.getenv('DB_URI') or 'cockroachdb://root@127.0.0.1:26257/iam_demo?application_name=iam_demo'

# Common actions and resources for audit logs
ACTIONS = [
    'view_dashboard', 'update_profile', 'view_report', 'create_resource',
    'modify_resource', 'view_audit_log', 'run_query', 'export_data'
]

RESOURCES = [
    'user_profile', 'dashboard', 'reports', 'settings', 'audit_logs',
    'users', 'roles', 'analytics', 'monitoring'
]


def demo_flow_once(db_engine: SAEngine, user_ids: list, role_ids: list,
                   op_timer: DemoTimer, stats: DemoStats):
    """
    Execute one iteration of the demo flow:
    1. Login (create session) - Regional write
    2. Check user info - Global read
    3. Update last login - Global write
    4. Check role/permissions - Global read
    5. Perform actions (create audit logs) - RBR writes
    6. Logout (end session) - Regional write
    7. Read recent audit log - RBR read
    8. Read session - Regional read (current)
    9. Read session with AOST - Regional follower read
    """

    # Pick a random user and role
    user_id = choice(user_ids)
    role_id = choice(role_ids)

    # ==========================================================================
    # 1. LOGIN - Create session (Regional write)
    # ==========================================================================
    session_id = uuid4()
    login_time = dt.now()

    op_timer.start()
    run_transaction(
        db_engine,
        lambda conn: create_session(
            conn, session_id, user_id, login_time,
            ip_address='192.168.1.100', user_agent='Demo App'
        )
    )
    stats.add_to_stats(DemoStats.OP_LOGIN, op_timer.stop())

    # ==========================================================================
    # 2. READ USER - Check user info (Global read)
    # ==========================================================================
    op_timer.start()
    run_transaction(
        db_engine,
        lambda conn: get_user(conn, user_id)
    )
    stats.add_to_stats(DemoStats.OP_READ_USER, op_timer.stop())

    # ==========================================================================
    # 3. UPDATE LAST LOGIN - Update user's last login time (Global write)
    # ==========================================================================
    op_timer.start()
    run_transaction(
        db_engine,
        lambda conn: update_last_login(conn, user_id, login_time)
    )
    stats.add_to_stats(DemoStats.OP_UPDATE_USER, op_timer.stop())

    # ==========================================================================
    # 4. READ ROLE - Check user's roles/permissions (Global read)
    # ==========================================================================
    op_timer.start()
    run_transaction(
        db_engine,
        lambda conn: get_role(conn, role_id)
    )
    stats.add_to_stats(DemoStats.OP_READ_ROLE, op_timer.stop())

    # ==========================================================================
    # 5. PERFORM ACTIONS - Create audit log entries (RBR writes)
    # ==========================================================================
    audit_ids = []
    for i in range(NUM_AUDIT_ACTIONS):
        action = choice(ACTIONS)
        resource = choice(RESOURCES)

        op_timer.start()
        audit_id = run_transaction(
            db_engine,
            lambda conn: create_audit_log(
                conn, user_id, session_id, action, resource,
                result='success',
                metadata={'action_number': i + 1, 'duration_ms': randint(10, 500)}
            )
        )
        stats.add_to_stats(DemoStats.OP_CREATE_AUDIT, op_timer.stop())
        audit_ids.append(audit_id)

    # ==========================================================================
    # 6. LOGOUT - End session (Regional write)
    # ==========================================================================
    logout_time = dt.now()

    op_timer.start()
    run_transaction(
        db_engine,
        lambda conn: end_session(conn, session_id, logout_time)
    )
    stats.add_to_stats(DemoStats.OP_LOGOUT, op_timer.stop())

    # ==========================================================================
    # 7. READ AUDIT LOG - Read recent audit entry (RBR read)
    # ==========================================================================
    # Pick one of the audit logs we just created
    audit_id = choice(audit_ids)

    op_timer.start()
    run_transaction(
        db_engine,
        lambda conn: get_recent_audit_log(conn, audit_id)
    )
    stats.add_to_stats(DemoStats.OP_READ_AUDIT, op_timer.stop())

    # ==========================================================================
    # 8. READ SESSION - Read session details (Regional read - current)
    # ==========================================================================
    op_timer.start()
    run_transaction(
        db_engine,
        lambda conn: get_session(conn, session_id)
    )
    stats.add_to_stats(DemoStats.OP_READ_SESSION, op_timer.stop())

    # ==========================================================================
    # 9. READ SESSION (AOST) - Follower read (Regional AOST read)
    # ==========================================================================
    op_timer.start()
    run_transaction(
        db_engine,
        lambda conn: get_session_aost(conn, session_id)
    )
    stats.add_to_stats(DemoStats.OP_READ_SESSION_AOST, op_timer.stop())


def main():
    """Main demo loop"""
    print("IAM Demo starting...")
    print(f"Database URI: {DB_URI}")
    print()

    # Start Prometheus metrics HTTP server
    try:
        start_http_server(METRICS_PORT)
        print(f"Prometheus metrics server started on port {METRICS_PORT}")
        print(f"Metrics available at: http://localhost:{METRICS_PORT}/metrics")
        print()
    except OSError as e:
        print(f"Warning: Could not start metrics server on port {METRICS_PORT}: {e}")
        print("Continuing without Prometheus metrics...")
        print()

    stats = DemoStats(STATS_INTERVAL_SECS)
    op_timer = DemoTimer()

    db_engine = create_engine(DB_URI)

    # Query the gateway region and node ID from the database
    region = run_transaction(
        db_engine,
        lambda conn: get_gateway_region(conn)
    )
    node_id = run_transaction(
        db_engine,
        lambda conn: get_node_id(conn)
    )

    # Set connection info for stats display
    stats.set_connection_info(region, node_id)

    print(f"Connected to region: {region}, node: {node_id}")
    print()

    # Build lists of users and roles to randomly select from
    print("Loading user and role lists...")
    user_ids = run_transaction(
        db_engine,
        lambda conn: get_users(conn)
    )
    print(f"{len(user_ids)} active users found")

    role_ids = run_transaction(
        db_engine,
        lambda conn: get_roles(conn)
    )
    print(f"{len(role_ids)} roles found")
    print()

    # Main demo loop
    while True:
        demo_flow_once(db_engine, user_ids, role_ids, op_timer, stats)
        stats.display_if_ready()


if __name__ == '__main__':
    # Gracefully handle CTRL-C
    def sigint_handler(signal, frame):
        print("\nShutting down...")
        sys.exit(0)
    signal.signal(signal.SIGINT, sigint_handler)

    main()
