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


# =============================================================================
# BEHAVIOR PROFILE OPERATIONS (Global Table with Vectors)
# =============================================================================

def get_user_behavior_profile(conn: Connection, user_id: UUID) -> Row:
    """Get user's behavior profile including vector"""
    sql = text(
        "SELECT user_id, behavior_vector, profile_type, sample_count, last_updated "
        "FROM user_behavior_profiles WHERE user_id = :user_id"
    )
    return conn.execute(sql, {"user_id": user_id}).one_or_none()


def compute_current_login_vector(login_time: dt, region: str, regions: list,
                                last_login_time: dt = None, user_id: UUID = None) -> List[float]:
    """
    Compute an 8-dimensional behavior vector for the current login.

    Vector dimensions match user_behavior_profiles:
    1. Hour of day (normalized 0-1)
    2. Day of week (normalized 0-1)
    3. Region consistency (0-1, based on primary region)
    4. Time since last login (log-scaled, normalized)
    5. Session duration pattern (placeholder - use average)
    6. Login frequency (placeholder - use average)
    7. Recent failure rate (placeholder - assume low)
    8. Activity level (placeholder - use average)

    Note: Some dimensions require historical data. For real-time detection,
    we use defaults for unknown values.
    """
    import math

    # 1. Hour of day (0-23 -> 0-1)
    hour = login_time.hour
    v1 = hour / 23.0

    # 2. Day of week (0-6 -> 0-1)
    day = login_time.weekday()  # Monday = 0, Sunday = 6
    v2 = day / 6.0

    # 3. Region consistency (encode current region index)
    try:
        region_idx = regions.index(region)
    except ValueError:
        region_idx = 0  # Default to first region if not found
    v3 = region_idx / max(1, len(regions) - 1)

    # 4. Time since last login (log-scaled)
    if last_login_time:
        time_diff = (login_time - last_login_time).total_seconds() / 3600.0  # hours
        time_diff = max(0.1, time_diff)  # Avoid log(0)
        v4 = min(1.0, math.log(time_diff) / 5.12)  # log(168 hours) ~= 5.12
    else:
        v4 = 0.5  # Default for first login

    # 5-8: Use defaults for dimensions that require historical tracking
    # In a production system, these would be computed from user history
    v5 = 0.5  # Session duration - assume average
    v6 = 0.5  # Login frequency - assume average
    v7 = 0.02  # Failure rate - assume low
    v8 = 0.5  # Activity level - assume average

    return [v1, v2, v3, v4, v5, v6, v7, v8]


def cosine_distance(vec1: List[float], vec2: List[float]) -> float:
    """
    Compute cosine distance between two vectors.
    Cosine distance = 1 - cosine similarity
    Returns a value between 0 (identical) and 2 (opposite)
    """
    import math

    # Ensure vectors are same length
    if len(vec1) != len(vec2):
        raise ValueError(f"Vectors must be same length: {len(vec1)} vs {len(vec2)}")

    # Compute dot product and magnitudes
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    # Avoid division by zero
    if magnitude1 == 0 or magnitude2 == 0:
        return 1.0  # Orthogonal

    # Cosine similarity
    cosine_sim = dot_product / (magnitude1 * magnitude2)

    # Cosine distance
    return 1.0 - cosine_sim


def detect_login_anomaly(conn: Connection, user_id: UUID, session_id: UUID,
                        login_time: dt, region: str, regions: list,
                        threshold: float = 0.3) -> tuple:
    """
    Detect if a login is anomalous based on user's behavior profile.

    Returns: (is_anomaly: bool, anomaly_score: float, details: dict)

    Args:
        threshold: Cosine distance threshold above which login is considered anomalous
                  (0.0 = identical, 1.0 = orthogonal, higher = more different)
    """
    # Get user's behavior profile
    profile = get_user_behavior_profile(conn, user_id)
    if not profile:
        # No profile exists - cannot detect anomaly
        return (False, 0.0, {"reason": "no_profile"})

    # Parse stored vector (comes as string like "[0.1,0.2,...]")
    profile_vector_str = profile.behavior_vector
    if isinstance(profile_vector_str, str):
        # Remove brackets and split by comma
        profile_vector = [float(x) for x in profile_vector_str.strip('[]').split(',')]
    else:
        # Already a list
        profile_vector = list(profile_vector_str)

    # Get user's last login time for time-since-last-login calculation
    user = get_user(conn, user_id)
    last_login = user.last_login if user else None

    # Compute current login vector
    current_vector = compute_current_login_vector(
        login_time=login_time,
        region=region,
        regions=regions,
        last_login_time=last_login,
        user_id=user_id
    )

    # Compute anomaly score (cosine distance)
    anomaly_score = cosine_distance(current_vector, profile_vector)

    # Determine if anomalous
    is_anomaly = anomaly_score > threshold

    # Build details
    details = {
        "threshold": threshold,
        "hour": login_time.hour,
        "day": login_time.strftime("%A"),
        "region": region,
        "time_since_last_login_hours": (
            (login_time - last_login).total_seconds() / 3600.0
            if last_login else None
        )
    }

    return (is_anomaly, anomaly_score, details)


def log_login_anomaly(conn: Connection, user_id: UUID, session_id: UUID,
                     anomaly_score: float, current_vector: List[float],
                     profile_vector: List[float], details: dict) -> UUID:
    """Log a detected login anomaly to the database"""
    import json

    # Format vectors as strings for storage
    current_vec_str = '[' + ','.join(str(v) for v in current_vector) + ']'
    profile_vec_str = '[' + ','.join(str(v) for v in profile_vector) + ']'

    sql = text(
        "INSERT INTO login_anomalies "
        "(user_id, session_id, anomaly_score, current_vector, profile_vector, anomaly_details) "
        "VALUES (:user_id, :session_id, :anomaly_score, :current_vector, :profile_vector, "
        "CAST(:anomaly_details AS JSONB)) "
        "RETURNING id"
    )

    result = conn.execute(sql, {
        "user_id": user_id,
        "session_id": session_id,
        "anomaly_score": anomaly_score,
        "current_vector": current_vec_str,
        "profile_vector": profile_vec_str,
        "anomaly_details": json.dumps(details)
    }).one()

    return result.id


def update_user_behavior_profile(conn: Connection, user_id: UUID,
                                new_vector: List[float], learning_rate: float = 0.1) -> None:
    """
    Update user's behavior profile using exponential moving average.

    Args:
        learning_rate: Weight given to new observation (0.1 = 10% new, 90% old)
    """
    # Get current profile
    profile = get_user_behavior_profile(conn, user_id)
    if not profile:
        return  # No profile to update

    # Parse current vector
    current_vector_str = profile.behavior_vector
    if isinstance(current_vector_str, str):
        current_vector = [float(x) for x in current_vector_str.strip('[]').split(',')]
    else:
        current_vector = list(current_vector_str)

    # Compute updated vector using exponential moving average
    updated_vector = [
        (1 - learning_rate) * old_val + learning_rate * new_val
        for old_val, new_val in zip(current_vector, new_vector)
    ]

    # Format for SQL
    updated_vector_str = '[' + ','.join(str(v) for v in updated_vector) + ']'

    # Update database
    sql = text(
        "UPDATE user_behavior_profiles "
        "SET behavior_vector = :vector, "
        "    profile_type = 'learned', "
        "    sample_count = sample_count + 1, "
        "    last_updated = now() "
        "WHERE user_id = :user_id"
    )

    conn.execute(sql, {
        "user_id": user_id,
        "vector": updated_vector_str
    })
