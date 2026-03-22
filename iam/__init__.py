"""
IAM Demo Module
Multi-region IAM demonstration for CockroachDB
"""

from .helpers import DemoStats, DemoTimer, run_transaction
from .transactions import (
    get_gateway_region, get_node_id,
    get_user, get_users, update_last_login,
    get_role, get_roles, get_user_roles,
    create_session, end_session, get_session, get_session_aost,
    create_audit_log, get_recent_audit_log, get_audit_log_aost, get_user_audit_logs
)

__all__ = [
    'DemoStats', 'DemoTimer', 'run_transaction',
    'get_gateway_region', 'get_node_id',
    'get_user', 'get_users', 'update_last_login',
    'get_role', 'get_roles', 'get_user_roles',
    'create_session', 'end_session', 'get_session', 'get_session_aost',
    'create_audit_log', 'get_recent_audit_log', 'get_audit_log_aost', 'get_user_audit_logs'
]
