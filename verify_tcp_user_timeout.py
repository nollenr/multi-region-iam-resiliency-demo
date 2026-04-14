#!/usr/bin/env python3.11
"""
Verify that SQLAlchemy -> psycopg -> libpq accepts and reports tcp_user_timeout.

Examples:
  python3.11 verify_tcp_user_timeout.py --timeout-ms 5000
  python3.11 verify_tcp_user_timeout.py --dsn "$CRDB_URL" --timeout-ms 3000
"""

import argparse
import os
import sys

from sqlalchemy import create_engine


def normalize_dsn(dsn: str) -> str:
    """Convert generic URLs into the SQLAlchemy driver form used by the demo."""
    if dsn.startswith("cockroachdb://"):
        return dsn.replace("cockroachdb://", "cockroachdb+psycopg://", 1)
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    return dsn


def get_driver_connection(sa_connection):
    """
    Return the underlying psycopg connection from a SQLAlchemy connection.

    SQLAlchemy wraps the DBAPI connection differently across versions, so we
    check the common attributes in order.
    """
    fairy = sa_connection.connection

    if hasattr(fairy, "driver_connection"):
        return fairy.driver_connection
    if hasattr(fairy, "dbapi_connection"):
        return fairy.dbapi_connection

    return fairy


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Connect with psycopg using tcp_user_timeout and verify it is present."
    )
    parser.add_argument(
        "--dsn",
        help="Connection string. Defaults to CRDB_URL, then DB_URI, then CRDB_CERT_URL.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=5000,
        help="tcp_user_timeout value in milliseconds (default: 5000).",
    )
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=5,
        help="Connection timeout in seconds (default: 5).",
    )
    args = parser.parse_args()

    dsn = args.dsn or os.getenv("CRDB_URL") or os.getenv("DB_URI") or os.getenv("CRDB_CERT_URL")
    if not dsn:
        print("No DSN provided. Set CRDB_URL/DB_URI/CRDB_CERT_URL or pass --dsn.", file=sys.stderr)
        return 2

    dsn = normalize_dsn(dsn)

    print(f"Connecting through SQLAlchemy with tcp_user_timeout={args.timeout_ms} ms")

    try:
        engine = create_engine(
            dsn,
            connect_args={
                "connect_timeout": args.connect_timeout,
                "tcp_user_timeout": args.timeout_ms,
            },
        )

        with engine.connect() as conn:
            driver_conn = get_driver_connection(conn)
            parameters = driver_conn.info.get_parameters()
            reported_value = parameters.get("tcp_user_timeout")

            print(f"Requested tcp_user_timeout: {args.timeout_ms}")
            print(f"Reported tcp_user_timeout:  {reported_value!r}")

            if str(reported_value) == str(args.timeout_ms):
                print("PASS: SQLAlchemy/psycopg/libpq accepted and reported tcp_user_timeout.")
                return 0

            print("FAIL: tcp_user_timeout was not reported as expected.")
            print(f"Available connection parameters: {parameters}")
            return 1

    except Exception as exc:
        print(f"Connection test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
