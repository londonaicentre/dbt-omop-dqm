import os
import sys
import psycopg
from loguru import logger
from dataclasses import dataclass, asdict
from datetime import datetime
from psycopg.rows import dict_row

# Threshold Statuses
STATUS_TEST_PASSED = "Test Passed"
STATUS_EXCEEDED_THRESHOLD = "Exceeded Threshold"
STATUS_NOT_CONFIGURED = "Not Configured"
STATUS_INSUFFICIENT_RUNS = "Insufficient Runs"
STATUS_ABOVE_THRESHOLD = "Above Threshold"
STATUS_BELOW_THRESHOLD = "Below Threshold"
STATUS_WITHIN_THRESHOLD = "Within Threshold"

# Row Count Anomaly Config
HISTORICAL_RUNS = (
    4  # Number of historical runs to consider for moving average calculation
)

# Timezone
TARGET_TIMEZONE = "Europe/London"  # Needed to convert dbt UTC timestamps to local time


@dataclass
class RowCountResult:
    """Result of a row count analysis including threshold status and bounds."""

    threshold_status: str
    upper_bound: int
    lower_bound: int


@dataclass
class TestResult:
    invocation_id: str
    test_name: str
    clean_test_name: str
    status: str
    execution_time: float
    generated_at: datetime
    category: str = None
    violations: int = 0
    threshold: int = None
    threshold_type: str = None
    threshold_status: str = None


# Database configuration
DB_CONFIG = {
    "dbname": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}


def update_threshold_status(test_result, historical_violations=None):
    """Update threshold status based on threshold type."""

    if test_result.status == "pass":
        test_result.threshold_status = STATUS_TEST_PASSED

    elif test_result.threshold_type in ["static_number", "static_percentage"]:
        test_result.threshold_status = calculate_static_threshold(
            test_result.violations, test_result.threshold
        )

    else:
        test_result.threshold_status = STATUS_NOT_CONFIGURED


def calculate_static_threshold(violations, threshold):
    """Calculate threshold status for static number"""
    if violations > threshold:
        return STATUS_EXCEEDED_THRESHOLD
    else:
        return STATUS_TEST_PASSED


def clean_test_name(test_name):
    """Remove threshold value from test name."""
    if "__" in test_name:
        return test_name.split("__")[0]
    return test_name


def setup_tables(cur):
    """Create the database schema and tables we need."""
    # Create schema
    cur.execute("CREATE SCHEMA IF NOT EXISTS metrics;")

    # Create table for storing results
    cur.execute("""
    CREATE TABLE IF NOT EXISTS metrics.historical_results (
        invocation_id TEXT,
        test_name TEXT,
        clean_test_name TEXT,
        category TEXT,
        status TEXT,
        violations INTEGER,
        execution_time FLOAT,
        generated_at TIMESTAMP,
        threshold INTEGER,
        threshold_type TEXT,
        threshold_status TEXT
    );
    """)

    # Create table for model row counts
    cur.execute("""
    CREATE TABLE IF NOT EXISTS metrics.row_count_anomalies (
        invocation_id TEXT,
        model_name TEXT,
        row_count INTEGER,
        threshold INTEGER,
        threshold_status TEXT,
        row_upper_bound FLOAT,
        row_lower_bound FLOAT,
        generated_at TIMESTAMP
    );
    """)

    # Create view for latest results
    cur.execute("""
    CREATE OR REPLACE VIEW metrics.latest_results AS
    WITH latest_invocation AS (
        SELECT invocation_id
        FROM metrics.historical_results
        ORDER BY generated_at DESC
        LIMIT 1
    )
    SELECT
        h.invocation_id,
        h.clean_test_name,
        h.category,
        h.status,
        h.violations,
        h.execution_time,
        h.generated_at,
        h.threshold,
        h.threshold_type,
        h.threshold_status
    FROM metrics.historical_results h
    JOIN latest_invocation li ON h.invocation_id = li.invocation_id;
    """)

    # Create view for violations history
    cur.execute("""
    CREATE OR REPLACE VIEW metrics.violations_history AS
    SELECT
        clean_test_name,
        threshold_type,
        generated_at,
        violations,
        category,
        threshold,
        test_name
    FROM metrics.historical_results
    ORDER BY clean_test_name, threshold_type, generated_at;
    """)


def get_new_test_results(cur):
    """Gets Data Quality tests that haven't been processed yet."""
    cur.execute("""
        SELECT DISTINCT 
            r.invocation_id,
            r.node_name,
            r.category,
            r.status,
            r.violations,
            r.execution_time,
            r.generated_at,
            r.threshold,
            r.threshold_type
        FROM dbt_artifacts.run_results r
        LEFT JOIN metrics.historical_results h ON r.invocation_id = h.invocation_id
        WHERE r.resource_type = 'test'
        AND h.invocation_id IS NULL
        AND (r.category != 'anomaly_detection' OR r.category IS NULL)
    """)
    return cur.fetchall()


def calculate_moving_average_status(historical_counts, current_count, threshold):
    """Calculate threshold status based on moving average of historical counts."""
    if len(historical_counts) < HISTORICAL_RUNS:
        return RowCountResult(STATUS_INSUFFICIENT_RUNS, 0, 0)

    # Calculate moving average including current count
    all_counts = historical_counts[-HISTORICAL_RUNS:] + [current_count]
    moving_avg = sum(all_counts) / len(all_counts)

    # Calculate bounds using threshold percentage
    if moving_avg > 0:
        upper_bound = int(moving_avg * (1 + threshold / 100))
        lower_bound = int(moving_avg * (1 - threshold / 100))

        if current_count > upper_bound:
            return RowCountResult(STATUS_ABOVE_THRESHOLD, upper_bound, lower_bound)
        elif current_count < lower_bound:
            return RowCountResult(STATUS_BELOW_THRESHOLD, upper_bound, lower_bound)
        else:
            # Use 'Within Threshold' for row counts when within bounds
            return RowCountResult(STATUS_WITHIN_THRESHOLD, upper_bound, lower_bound)

    # Use constant for default case (moving_avg <= 0)
    return RowCountResult(STATUS_WITHIN_THRESHOLD, 0, 0)


def get_model_row_counts(cur):
    """Gets row counts for models from dqm_row_count_anomalies tests."""
    cur.execute("""
        SELECT DISTINCT
            r.invocation_id,
            r.node_name,
            r.violations,
            r.threshold,
            r.generated_at
        FROM dbt_artifacts.run_results r
        WHERE r.node_name LIKE '%_dqm_row_count_anomalies_%'
          AND r.resource_type = 'test'
          AND NOT EXISTS (
              SELECT 1
              FROM metrics.row_count_anomalies a
              WHERE a.invocation_id = r.invocation_id
          )
        ORDER BY r.generated_at;
    """)

    rows = cur.fetchall()
    if rows:
        logger.success("Successfully processed model anomaly and row counts.")

    for test in rows:
        node_name = test["node_name"]

        if node_name.startswith("dbt_omop_dqm_dqm_row_count_anomalies_"):
            prefix_removed = node_name[len("dbt_omop_dqm_dqm_row_count_anomalies_") :]
            model_name = prefix_removed.rsplit("_", 1)[0]

            # Get historical counts
            cur.execute(
                """
                SELECT row_count
                FROM metrics.row_count_anomalies
                WHERE model_name = %s
                ORDER BY generated_at DESC
                LIMIT %s
                """,
                (model_name, HISTORICAL_RUNS),
            )

            # Use dictionary access for historical counts
            historical_counts = [row["row_count"] for row in cur.fetchall()]
            # Use dictionary access for current test data
            current_count = test["violations"]  # violations column holds the row count
            threshold = test["threshold"]

            result = calculate_moving_average_status(
                historical_counts, current_count, threshold
            )

            # Use named placeholders
            insert_data = {
                "invocation_id": test["invocation_id"],
                "model_name": model_name,
                "row_count": current_count,
                "threshold": threshold,
                "threshold_status": result.threshold_status,
                "row_upper_bound": result.upper_bound,
                "row_lower_bound": result.lower_bound,
                "generated_at": test["generated_at"],
            }

            # Insert results
            cur.execute(
                f"""
                INSERT INTO metrics.row_count_anomalies (
                    invocation_id, model_name, row_count, threshold, threshold_status,
                    row_upper_bound, row_lower_bound, generated_at
                ) VALUES (
                    %(invocation_id)s, %(model_name)s, %(row_count)s, %(threshold)s,
                    %(threshold_status)s, %(row_upper_bound)s, %(row_lower_bound)s,
                    %(generated_at)s::timestamp AT TIME ZONE 'UTC' AT TIME ZONE '{TARGET_TIMEZONE}'
                )
            """,
                insert_data,
            )


def process_test_results(cur):
    """Process new test results and save them to the database."""
    # Get new results
    results = get_new_test_results(cur)
    if not results:
        return False

    # Process results using dictionary access
    for result in results:  # result is now a dictionary
        # Instantiate TestResult using dictionary keys
        test_result = TestResult(
            invocation_id=result["invocation_id"],
            test_name=result["node_name"],
            clean_test_name="",  # Will be set before insert
            status=result["status"],
            execution_time=result["execution_time"],
            generated_at=result["generated_at"],
            category=result["category"],
            violations=result["violations"],
            threshold=result["threshold"],
            threshold_type=result["threshold_type"],
        )

        # Only process tests that have a category
        if test_result.category is not None:
            # Process test result based on the threshold type
            update_threshold_status(test_result)

            # Save the result
            test_result.clean_test_name = clean_test_name(test_result.test_name)
            cur.execute(
                f"""
                INSERT INTO metrics.historical_results (
                    invocation_id, test_name, clean_test_name, category, status, violations,
                    execution_time, generated_at, threshold, threshold_type,
                    threshold_status
                ) VALUES (
                    %(invocation_id)s, %(test_name)s, %(clean_test_name)s, %(category)s, %(status)s,
                    %(violations)s, %(execution_time)s,
                    %(generated_at)s::timestamp AT TIME ZONE 'UTC' AT TIME ZONE '{TARGET_TIMEZONE}',
                    %(threshold)s, %(threshold_type)s, %(threshold_status)s
                )
            """,
                asdict(test_result),
            )

    return True


def main():
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            # Use dict_row factory for cursors to get results as dictionaries
            with conn.cursor(row_factory=dict_row) as cur:
                setup_tables(cur)

                # Process tests first
                if process_test_results(cur):
                    logger.success(
                        "Successfully processed and stored new data quality tests."
                    )
                else:
                    logger.info("No new data quality tests to process.")

                # Process model row counts
                get_model_row_counts(cur)

    except Exception as e:
        logger.exception("Failed to process data quality tests")
        sys.exit(1)


if __name__ == "__main__":
    main()
