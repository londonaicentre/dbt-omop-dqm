import json
import os
import sys
import psycopg
import argparse
from loguru import logger
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime


class ArtifactProcessingError(Exception):
    """Base exception for artifact processing errors."""

    pass


class ArtifactNotFoundError(ArtifactProcessingError):
    """Raised when required artifact files are not found."""

    pass


class ProjectDirError(ArtifactProcessingError):
    """Raised when the project directory is not specified or found."""

    pass


class DuplicateInvocationIdError(ArtifactProcessingError):
    """Raised when results for an invocation ID already exist."""

    pass


class DatabaseError(ArtifactProcessingError):
    """Raised for database connection or query errors."""

    pass


# Module Constants
VALID_CATEGORIES = {"completeness", "plausibility", "conformance", "anomaly_detection"}
VALID_THRESHOLD_TYPES = {"static_number", "static_percentage"}


@dataclass
class Manifest:
    category: str = None
    threshold_type: str = None
    threshold: int = None


@dataclass
class RunResult:
    invocation_id: str
    unique_id: str
    status: str
    execution_time: float
    node_name: str
    resource_type: str
    generated_at: datetime
    message: str = None
    compiled_code: str = None
    relation_name: str = None
    violations: int = 0
    category: str = None
    threshold_type: str = None
    threshold: int = None


# Database configuration
DB_CONFIG = {
    "dbname": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}


def verify_artifacts(project_root, run_results_path, manifest_path):
    """Verify that required dbt artifact files exist."""
    if not project_root.exists():
        raise ProjectDirError(f"Project directory does not exist: {project_root}")

    missing_files = []
    if not run_results_path.exists():
        missing_files.append(str(run_results_path))
    if not manifest_path.exists():
        missing_files.append(str(manifest_path))

    if missing_files:
        logger.error(f"The following files were not found: {', '.join(missing_files)}")
        logger.info(
            "Please run dbt first to generate these files or check your project path."
        )
        logger.error(f"Expected files in: {project_root}")
        # Raise exception instead of exiting
        raise ArtifactNotFoundError(
            f"The following files were not found: {', '.join(missing_files)}"
        )


def get_project_root(args):
    """Gets artifacts directory from arguments or environment and returns artifact paths."""
    if args.project_dir:
        root = Path(args.project_dir)
    elif project_dir := os.getenv("DBT_PROJECT_ROOT"):
        root = Path(project_dir)
    else:
        logger.error(
            "DBT Artifacts directory must be specified via --project-dir argument or DBT_PROJECT_ROOT environment variable"
        )
        # Raise exception instead of exiting
        raise ProjectDirError(
            "DBT Artifacts directory must be specified via --project-dir argument or DBT_PROJECT_ROOT environment variable"
        )

    # Return root and artifact paths
    return (
        root,
        root / "run_results.json",
        root / "manifest.json",
    )


def check_invocation_id_exists(cur, invocation_id):
    """Checks if results for a specific dbt run already exist in database."""
    cur.execute(
        """
        SELECT COUNT(*)
        FROM dbt_artifacts.run_results
        WHERE invocation_id = %s;
        """,
        (invocation_id,),
    )

    count = cur.fetchone()[0]
    return count > 0


def create_tables(cur):
    """Creates database schema and tables for storing dbt artifacts."""
    # Create the dbt_artifacts schema if it doesn't exist
    cur.execute("CREATE SCHEMA IF NOT EXISTS dbt_artifacts;")

    # Drop table to do a clean build
    # cur.execute("DROP TABLE IF EXISTS dbt_artifacts.run_results;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dbt_artifacts.run_results (
            invocation_id TEXT,
            unique_id TEXT,
            status TEXT,
            execution_time FLOAT,
            message TEXT,
            compiled_code TEXT,
            relation_name TEXT,
            violations INTEGER,
            node_name TEXT,
            resource_type TEXT,
            category TEXT,
            threshold_type TEXT,
            threshold INTEGER,
            generated_at TIMESTAMP
        );
    """)


def process_manifest_data(manifest_data):
    """Extracts metadata from dbt manifest for test configurations."""
    meta_dict = {}
    valid_categories = {
        "completeness",
        "plausibility",
        "conformance",
        "anomaly_detection",
    }
    valid_threshold_types = {"static_number", "static_percentage"}

    # Pull nodes data directly in manifest
    category_data = manifest_data["nodes"]
    for unique_id, node in category_data.items():
        # Extract meta data from node
        meta = node.get("meta", {})
        if meta:
            category = meta.get("category")
            if category:
                category = category.lower()
                if category not in valid_categories:
                    logger.warning(
                        f"Invalid category '{category}' in {unique_id}. Must be one of: {', '.join(valid_categories)}. Setting to None."
                    )
                    category = None

            threshold_type = meta.get("threshold_type")
            if threshold_type:
                threshold_type = threshold_type.lower()
                if threshold_type not in valid_threshold_types:
                    logger.warning(
                        f"Invalid threshold_type '{threshold_type}' in {unique_id}. Must be one of: {', '.join(valid_threshold_types)}. Setting to None."
                    )
                    threshold_type = None

            threshold = meta.get("threshold")

            # Validate threshold value if present
            if threshold is not None:
                # Check for negative values
                if threshold < 0:
                    logger.warning(
                        f"Invalid negative threshold {threshold} in {unique_id}. Must be non-negative. Setting to 0."
                    )
                    threshold = 0
                # Ensure percentage not above 100
                elif threshold_type == "static_percentage" and threshold > 100:
                    logger.warning(
                        f"Invalid percentage threshold {threshold} in {unique_id}. Must be between 0 and 100. Setting to 0."
                    )
                    threshold = 0

            meta_dict[unique_id] = Manifest(
                category=category,
                threshold_type=threshold_type,
                threshold=threshold,
            )

    return meta_dict


def process_run_results(run_data, meta_dict):
    """Processes dbt run results and combines them with test metadata."""
    results = []
    metadata = run_data.get("metadata", {})

    for result in run_data["results"]:
        unique_id = result["unique_id"]

        # Generic tests have an extra hexadecimal value after the name, this ensures to not pick that up.
        parts = unique_id.split(".")
        node_name = parts[-2] if len(parts) > 3 else parts[-1] if parts else ""
        resource_type = parts[0] if parts else ""

        meta = meta_dict.get(unique_id, Manifest())

        results.append(
            RunResult(
                invocation_id=metadata.get("invocation_id"),
                unique_id=unique_id,
                status=result["status"],
                execution_time=result["execution_time"],
                message=result.get("message"),
                compiled_code=result.get("compiled_code"),
                relation_name=result.get("relation_name"),
                violations=result.get("failures", 0),
                node_name=node_name,
                resource_type=resource_type,
                category=meta.category,
                threshold_type=meta.threshold_type,
                threshold=meta.threshold,
                generated_at=metadata.get("generated_at", None),
            )
        )

    return results


def load_dbt_artifacts(cur, run_results_path, manifest_path):
    """Loads dbt artifacts from files and stores them in the database."""
    with run_results_path.open("r") as f:
        run_data = json.load(f)

    # Check for duplicate invocation_id
    invocation_id = run_data.get("metadata", {}).get("invocation_id")
    if invocation_id and check_invocation_id_exists(cur, invocation_id):
        logger.error(
            f"Results for invocation_id {invocation_id} already exist in database"
        )
        # Raise exception instead of exiting
        raise DuplicateInvocationIdError(
            f"Results for invocation_id {invocation_id} already exist in database"
        )

    # Load manifest data
    with manifest_path.open("r") as f:
        manifest_data = json.load(f)

    # Process manifest to get meta information
    meta_dict = process_manifest_data(manifest_data)

    # Process run results
    results = process_run_results(run_data, meta_dict)

    # Insert results
    insert_query = """
        INSERT INTO dbt_artifacts.run_results (
            invocation_id, unique_id, status, execution_time, message, compiled_code,
            relation_name, violations, node_name, resource_type, category,
            threshold_type, threshold, generated_at
        )
        VALUES (
            %(invocation_id)s, %(unique_id)s, %(status)s, %(execution_time)s, %(message)s,
            %(compiled_code)s, %(relation_name)s, %(violations)s, %(node_name)s,
            %(resource_type)s, %(category)s, %(threshold_type)s, %(threshold)s,
            %(generated_at)s
        );
    """
    for result in results:
        # Convert dataclass to dictionary for named placeholders
        cur.execute(insert_query, asdict(result))

    logger.success("Successfully processed dbt artifacts")


def main():
    parser = argparse.ArgumentParser(
        description="Parse and load dbt artifacts into PostgreSQL."
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        help="Path to the directory containing dbt artifacts (manifest.json and run_results.json) (required if DBT_PROJECT_ROOT env var is not set)",
    )
    args = parser.parse_args()

    # Get project paths and verify artifacts
    project_root, run_results_path, manifest_path = get_project_root(args)
    logger.info(f"Using dbt artifacts directory: {project_root}")
    verify_artifacts(project_root, run_results_path, manifest_path)

    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                create_tables(cur)
                load_dbt_artifacts(cur, run_results_path, manifest_path)
                logger.success(
                    "Table run_results has been created and populated successfully!"
                )
    except (ArtifactProcessingError, psycopg.Error) as e:
        # Handle known artifact processing or database errors
        logger.error(f"Failed to process dbt artifacts: {e}")
        sys.exit(1)
    except Exception as e:
        # Handle unexpected errors
        logger.exception("An unexpected error occurred during artifact processing")
        sys.exit(1)


if __name__ == "__main__":
    main()
