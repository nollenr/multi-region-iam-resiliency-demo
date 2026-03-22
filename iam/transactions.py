"""
IAM Transaction Functions
Database operations for the multi-region IAM demo
"""

from datetime import datetime as dt
from typing import List
from uuid import UUID

from sqlalchemy.engine import Connection, Row
from sqlalchemy.sql import text


# =============================================================================
# UTILITY OPERATIONS
# =============================================================================

def get_gateway_region(conn: Connection) -> str:
    """Get the current gateway region"""
    sql = text("SELECT gateway_region()::STRING AS region")
    result = conn.execute(sql).one()
    return result.region


def get_node_id(conn: Connection) -> int:
    """Get the current node ID"""
    # CockroachDB function to get the node ID of the gateway
    sql = text("SELECT crdb_internal.node_id()")
    result = conn.execute(sql).one()
    # Result is a single column, access by index
    return result[0]


# =============================================================================
# USER OPERATIONS (Global Table)
# =============================================================================

def get_user(conn: Connection, user_id: UUID) -> Row:
    """Read a user by ID"""
    sql = text(
        "SELECT id, username, email, created_at, last_login, status "
        "FROM users WHERE id = :id"
    )
    return conn.execute(sql, {"id": user_id}).one()


def get_users(conn: Connection) -> List[UUID]:
    """Get list of all active user IDs"""
    sql = text("SELECT id FROM users WHERE status = 'active'")
    return [row.id for row in conn.execute(sql).all()]


def update_last_login(conn: Connection, user_id: UUID, login_time: dt) -> None:
    """Update user's last login timestamp"""
    sql = text(
        "UPDATE users SET last_login = :login_time WHERE id = :id"
    )
    conn.execute(sql, {"id": user_id, "login_time": login_time})


# =============================================================================
# ROLE OPERATIONS (Global Table)
# =============================================================================

def get_role(conn: Connection, role_id: UUID) -> Row:
    """Read a role by ID"""
    sql = text(
        "SELECT id, role_name, description, permissions "
        "FROM roles WHERE id = :id"
    )
    return conn.execute(sql, {"id": role_id}).one()


def get_roles(conn: Connection) -> List[UUID]:
    """Get list of all role IDs"""
    sql = text("SELECT id FROM roles")
    return [row.id for row in conn.execute(sql).all()]


def get_user_roles(conn: Connection, user_id: UUID) -> List[Row]:
    """Get all roles assigned to a user"""
    sql = text(
        "SELECT r.id, r.role_name, r.permissions, ur.assigned_at "
        "FROM user_roles ur "
        "JOIN roles r ON ur.role_id = r.id "
        "WHERE ur.user_id = :user_id"
    )
    return conn.execute(sql, {"user_id": user_id}).all()


# =============================================================================
# SESSION OPERATIONS (Regional Table)
# =============================================================================

def create_session(conn: Connection, session_id: UUID, user_id: UUID,
                   login_time: dt, ip_address: str = None, user_agent: str = None) -> UUID:
    """
    Create a new session (regional write)
    Region is automatically populated using gateway_region()
    """
    sql = text(
        "INSERT INTO sessions (id, user_id, region, login_time, status, ip_address, user_agent) "
        "VALUES (:id, :user_id, gateway_region()::STRING, :login_time, 'active', :ip_address, :user_agent) "
        "RETURNING id"
    )
    result = conn.execute(sql, {
        "id": session_id,
        "user_id": user_id,
        "login_time": login_time,
        "ip_address": ip_address,
        "user_agent": user_agent
    }).one()
    return result.id


def end_session(conn: Connection, session_id: UUID, logout_time: dt) -> None:
    """End a session (regional write)"""
    sql = text(
        "UPDATE sessions SET logout_time = :logout_time, status = 'completed' "
        "WHERE id = :id"
    )
    conn.execute(sql, {"id": session_id, "logout_time": logout_time})


def get_session(conn: Connection, session_id: UUID) -> Row:
    """Read session details"""
    sql = text(
        "SELECT id, user_id, region, login_time, logout_time, status "
        "FROM sessions WHERE id = :id"
    )
    return conn.execute(sql, {"id": session_id}).one_or_none()


def get_session_aost(conn: Connection, session_id: UUID) -> Row:
    """
    Read session details using follower reads (AOST)
    This demonstrates reading from local replicas without going to the leaseholder
    """
    sql = text(
        "SELECT id, user_id, region, login_time, logout_time, status "
        "FROM sessions AS OF SYSTEM TIME follower_read_timestamp() "
        "WHERE id = :id"
    )
    return conn.execute(sql, {"id": session_id}).one_or_none()


# =============================================================================
# AUDIT LOG OPERATIONS (Regional-by-Row Table)
# =============================================================================

def create_audit_log(conn: Connection, user_id: UUID, session_id: UUID,
                     action: str, resource: str,
                     result: str = 'success', metadata: dict = None) -> UUID:
    """
    Create an audit log entry (regional-by-row write)
    crdb_region is automatically set to the gateway region
    """
    sql = text(
        "INSERT INTO audit_logs (user_id, session_id, action, resource, result, metadata) "
        "VALUES (:user_id, :session_id, :action, :resource, :result, CAST(:metadata AS JSONB)) "
        "RETURNING id"
    )

    import json
    metadata_json = json.dumps(metadata) if metadata else '{}'

    result_row = conn.execute(sql, {
        "user_id": user_id,
        "session_id": session_id,
        "action": action,
        "resource": resource,
        "result": result,
        "metadata": metadata_json
    }).one()
    return result_row.id


def get_recent_audit_log(conn: Connection, audit_id: UUID) -> Row:
    """
    Read a recent audit log entry from the local region
    Filters to local region using crdb_region = gateway_region()
    """
    sql = text(
        "SELECT id, user_id, session_id, action, resource, result, timestamp, crdb_region "
        "FROM audit_logs "
        "WHERE crdb_region = CAST(gateway_region() AS crdb_internal_region) AND id = :id"
    )
    return conn.execute(sql, {"id": audit_id}).one_or_none()


def get_audit_log_aost(conn: Connection, audit_id: UUID) -> Row:
    """
    Read an audit log entry using follower reads (AOST)
    This demonstrates reading from local replicas without going to the leaseholder
    Filters to local region using crdb_region = gateway_region()
    """
    sql = text(
        "SELECT id, user_id, session_id, action, resource, result, timestamp, crdb_region "
        "FROM audit_logs AS OF SYSTEM TIME follower_read_timestamp() "
        "WHERE crdb_region = CAST(gateway_region() AS crdb_internal_region) AND id = :id"
    )
    return conn.execute(sql, {"id": audit_id}).one_or_none()


def get_user_audit_logs(conn: Connection, user_id: UUID, limit: int = 10) -> List[Row]:
    """Get recent audit logs for a specific user"""
    sql = text(
        "SELECT id, action, resource, result, timestamp, crdb_region "
        "FROM audit_logs "
        "WHERE user_id = :user_id "
        "ORDER BY timestamp DESC "
        "LIMIT :limit"
    )
    return conn.execute(sql, {"user_id": user_id, "limit": limit}).all()
