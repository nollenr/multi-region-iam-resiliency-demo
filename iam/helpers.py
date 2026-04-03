"""
Helper classes and functions for the IAM demo
Includes stats tracking, timing, and transaction retry logic
"""

from datetime import datetime as dt
from statistics import mean
from time import perf_counter, sleep
from threading import RLock

import psycopg
from sqlalchemy.engine import Engine as SAEngine
from sqlalchemy.exc import DatabaseError

# Prometheus metrics
from prometheus_client import Histogram, Counter, Gauge

# Prometheus metrics definitions
operation_latency = Histogram(
    'iam_operation_duration_seconds',
    'Duration of IAM operations in seconds',
    ['operation', 'table_type', 'region']
)

operation_counter = Counter(
    'iam_operations_total',
    'Total number of IAM operations',
    ['operation', 'table_type', 'region']
)

region_status = Gauge(
    'iam_region_status',
    'Region status (1=up, 0=down)',
    ['region']
)

anomaly_counter = Counter(
    'iam_anomalies_detected_total',
    'Total number of login anomalies detected',
    ['region', 'severity']
)


class OpStats():
    """Tracks statistics for a single operation type"""

    def __init__(self, op_name: str) -> None:
        self.name = op_name

        # Stats as they are collected
        self.count = 0
        self.ms_sum = 0.0

        # Stats after being calculated for a reporting interval
        self.last_count = 0
        self.last_ops = 0.0
        self.last_ms_avg = 0.0

    def __str__(self):
        return (f"OpStats: name={self.name} count={self.count} ms_sum={self.ms_sum} "
                f"last_count={self.last_count} last_ops={self.last_ops} last_ms_avg={self.last_ms_avg}")


class DemoStats():
    """
    Thread-safe statistics tracker for demo operations
    All threads should share the same instance
    """

    # Operation types
    OP_LOGIN = 'login'
    OP_READ_USER = 'read_user'
    OP_UPDATE_USER = 'update_user'
    OP_READ_ROLE = 'read_role'
    OP_CREATE_AUDIT = 'create_audit'
    OP_LOGOUT = 'logout'
    OP_READ_SESSION = 'read_session'
    OP_READ_SESSION_AOST = 'read_session_aost'
    OP_READ_AUDIT = 'read_audit'
    OP_ANOMALY_DETECTION = 'anomaly_detection'

    def __init__(self, reporting_interval_secs: int) -> None:
        self.reporting_secs = reporting_interval_secs
        self.lock = RLock()  # Make this thread safe

        self.reporting_timer = DemoTimer()
        self.reporting_timer.start()

        self.region = None
        self.node_id = None

        self.op_names = [
            DemoStats.OP_LOGIN,
            DemoStats.OP_READ_USER,
            DemoStats.OP_UPDATE_USER,
            DemoStats.OP_READ_ROLE,
            DemoStats.OP_CREATE_AUDIT,
            DemoStats.OP_LOGOUT,
            DemoStats.OP_READ_SESSION,
            DemoStats.OP_READ_SESSION_AOST,
            DemoStats.OP_READ_AUDIT,
            DemoStats.OP_ANOMALY_DETECTION
        ]

        # Map operations to table types for Prometheus labels
        self.op_to_table_type = {
            DemoStats.OP_READ_USER: 'global',
            DemoStats.OP_UPDATE_USER: 'global',
            DemoStats.OP_READ_ROLE: 'global',
            DemoStats.OP_LOGIN: 'regional',
            DemoStats.OP_LOGOUT: 'regional',
            DemoStats.OP_READ_SESSION: 'regional',
            DemoStats.OP_READ_SESSION_AOST: 'regional',
            DemoStats.OP_CREATE_AUDIT: 'rbr',
            DemoStats.OP_READ_AUDIT: 'rbr',
            DemoStats.OP_ANOMALY_DETECTION: 'vector'
        }

        self.stats_objs = {}
        for op_name in self.op_names:
            self.stats_objs[op_name] = OpStats(op_name)

        # Anomaly counter
        self.anomaly_count = 0
        self.last_anomaly_count = 0

    def set_connection_info(self, region: str, node_id: int) -> None:
        """Set the region and node_id for display and update Prometheus status"""
        self.region = region
        self.node_id = node_id

        # Set region status to "up" (1) in Prometheus
        if region:
            region_status.labels(region=region).set(1)

    def add_to_stats(self, op_name: str, time_ms: float) -> None:
        """Add an operation timing to the stats and Prometheus metrics"""
        with self.lock:
            stat = self.stats_objs.get(op_name)
            if stat:
                stat.count += 1
                stat.ms_sum += time_ms

            # Record to Prometheus metrics
            table_type = self.op_to_table_type.get(op_name, 'unknown')
            region = self.region or 'unknown'

            # Record latency in seconds
            operation_latency.labels(
                operation=op_name,
                table_type=table_type,
                region=region
            ).observe(time_ms / 1000.0)

            # Increment operation counter
            operation_counter.labels(
                operation=op_name,
                table_type=table_type,
                region=region
            ).inc()

    def increment_anomaly_count(self) -> None:
        """Increment the anomaly detection counter"""
        with self.lock:
            self.anomaly_count += 1

    def calc_and_reset_stats(self) -> None:
        """Calculate aggregate statistics and reset counters"""
        with self.lock:
            for op_name in self.op_names:
                stat = self.stats_objs.get(op_name)

                # Calculate aggregate stats
                if stat.count > 0:
                    stat.last_count = stat.count
                    stat.last_ops = stat.count / self.reporting_secs
                    stat.last_ms_avg = stat.ms_sum / stat.count

                # Reset counting stats
                stat.count = 0
                stat.ms_sum = 0.0

            # Store anomaly count for this interval
            self.last_anomaly_count = self.anomaly_count
            self.anomaly_count = 0

    def display_if_ready(self):
        """Display stats if the reporting interval has elapsed"""
        if self.reporting_timer.get() > self.reporting_secs * 1000:

            self.reporting_timer.start()  # Reset the stats timer
            self.calc_and_reset_stats()

            statstime = dt.now()  # For displaying the time of the stats

            # Calculate grouped statistics
            global_reads_ms = mean([
                self.stats_objs[DemoStats.OP_READ_USER].last_ms_avg,
                self.stats_objs[DemoStats.OP_READ_ROLE].last_ms_avg
            ])
            global_writes_ms = mean([
                self.stats_objs[DemoStats.OP_UPDATE_USER].last_ms_avg
            ])

            regional_writes_ms = mean([
                self.stats_objs[DemoStats.OP_LOGIN].last_ms_avg,
                self.stats_objs[DemoStats.OP_LOGOUT].last_ms_avg
            ])
            regional_reads_ms = mean([
                self.stats_objs[DemoStats.OP_READ_SESSION].last_ms_avg
            ])
            regional_reads_aost_ms = mean([
                self.stats_objs[DemoStats.OP_READ_SESSION_AOST].last_ms_avg
            ])

            rbr_reads_ms = mean([
                self.stats_objs[DemoStats.OP_READ_AUDIT].last_ms_avg
            ])
            rbr_writes_ms = mean([
                self.stats_objs[DemoStats.OP_CREATE_AUDIT].last_ms_avg
            ])

            node_info = f"Node: {self.node_id}" if self.node_id is not None else "Node: N/A (Serverless)"
            print(statstime)
            print(f"Region: {self.region}, {node_info}")
            print('---------------------------------------')
            print('Global tables (users, roles)')
            print(f"  reads:  {global_reads_ms:>8.2f} ms avg")
            print(f"  writes: {global_writes_ms:>8.2f} ms avg")
            print()
            print('Regional tables (sessions)')
            print(f"  reads:  {regional_reads_ms:>8.2f} ms avg")
            print(f"  writes: {regional_writes_ms:>8.2f} ms avg")
            print(f"  AOST:   {regional_reads_aost_ms:>8.2f} ms avg")
            print()
            print('RBR tables (audit_logs)')
            print(f"  reads:  {rbr_reads_ms:>8.2f} ms avg")
            print(f"  writes: {rbr_writes_ms:>8.2f} ms avg")
            print()

            # Show anomaly detection stats if enabled
            anomaly_stat = self.stats_objs.get(DemoStats.OP_ANOMALY_DETECTION)
            if anomaly_stat and anomaly_stat.last_count > 0:
                print('AI/Vector Operations (anomaly detection)')
                print(f"  detection: {anomaly_stat.last_ms_avg:>8.2f} ms avg")
                print(f"  anomalies: {self.last_anomaly_count} detected (last {self.reporting_secs}s)")
                print()


class DemoTimer():
    """
    Simple timer for measuring operation duration
    NOT thread safe - each thread should use its own instance
    """

    def __init__(self) -> None:
        self.starttime: float = None   # Seconds

    def start(self) -> None:
        """Start the timer"""
        self.starttime = perf_counter()

    def stop(self) -> float:
        """Stop the timer and return elapsed time in milliseconds"""
        stoptime = perf_counter()
        time_ms = (stoptime - self.starttime) * 1000
        return time_ms

    def get(self) -> float:
        """Get elapsed time without stopping (same as stop since stop doesn't actually stop)"""
        return self.stop()


def run_transaction(db_engine: SAEngine, txn_func, region=None, max_retries=10):
    """
    Execute a transaction function with automatic retry logic for transient errors

    Handles:
    - Serialization failures (40001) - retry with backoff
    - Statement completion unknown (40003) - retry with backoff
    - Connection errors - retry indefinitely with 1s delay

    Compatible with psycopg3 (psycopg package)

    Args:
        db_engine: SQLAlchemy database engine
        txn_func: Transaction function to execute
        region: Region name for connectivity tracking (optional)
        max_retries: Maximum retry attempts (None for infinite)
    """
    retry_count = 0
    while True:
        try:
            with db_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
                result = txn_func(conn)

                # SUCCESS - mark region as connected
                if region:
                    region_status.labels(region=region).set(1)

                return result

        except DatabaseError as e:
            if max_retries is not None and retry_count >= max_retries:
                raise
            retry_count += 1

            # Transaction isolation error (serialization failure)
            # PG error #: 40001
            #
            # Transient transaction error (statement completion unknown)
            # PG error #: 40003
            if isinstance(e.orig, psycopg.errors.OperationalError) and e.orig.sqlstate in ['40001', '40003']:
                print(f"Retrying {retry_count}/{max_retries} on PG error # {e.orig.sqlstate}")
                continue

            # Connection errors - retry indefinitely with delay
            elif isinstance(e.orig, psycopg.errors.OperationalError):
                # FAILURE - mark region as disconnected
                if region:
                    region_status.labels(region=region).set(0)

                pg_code = ''
                if e.orig.sqlstate is not None:
                    pg_code = f" (PG Error: {e.orig.sqlstate})"
                print(f"Connection lost, attempting to reconnect...{pg_code}")
                retry_count = 0   # Try indefinitely
                sleep(0.5)  # 500ms between retries for fast reconnection in demos
                continue

            # Raise everything else
            else:
                raise
