# DQM Dashboard Package

This package contains the Python scripts for the Data Quality Monitoring (DQM) dashboard, including the Streamlit application and supporting scripts for processing dbt artifacts.

## Setup and Installation

This package uses `uv` for dependency management and execution.
Ensure you are in the `dashboard/` directory in your terminal.

1.  **Install Dependencies & Package:** Run the following command to create a virtual environment (if it doesn't exist), install dependencies from `pyproject.toml`, and install this package in editable mode:
    ```bash
    uv pip install -e .
    ```

    Alternatively build the package and then install the generated .whl file:
     ```bash
    uv build 
    ```

## Running the Components

Use `uv run` to execute commands within the managed virtual environment.

### 1. Parse dbt Artifacts

To parse `run_results.json` and `manifest.json` from a dbt project run and load them into the database:
```bash
# Replace '../path/to/dbt/project' with the actual path to your dbt project root
uv run python -m dqm_dashboard.parse_dbt_artifacts --project-dir ../path/to/dbt/project
```

### 2. Transform Run Results

To process the parsed dbt results, calculate thresholds, and populate the metrics tables:
```bash
uv run python -m dqm_dashboard.transform_run_results
```

### 3. Streamlit Dashboard

To start the web application:
```bash
uv run dqm-dashboard
```
This uses the entry point defined in `pyproject.toml`. Access the dashboard via the URL provided by Streamlit in your terminal.