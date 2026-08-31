"""
marketing_pipeline_dag.py
--------------------------
Orchestrates the marketing analytics pipeline end to end:

    generate synthetic data -> load into the warehouse -> dbt build (staging
    -> intermediate -> marts, plus all tests) -> dbt docs

"""

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_ROOT = os.environ.get("MARKETING_PIPELINE_HOME", "/workspaces/marketing-analytics-pipeline")
VENV_BIN = f"{PROJECT_ROOT}/.venv/bin"
DBT_PROJECT_DIR = f"{PROJECT_ROOT}/dbt_project"

default_args = {
    "owner": "analytics_engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="marketing_pipeline",
    description="End-to-end marketing analytics pipeline: ingest -> transform -> test",
    default_args=default_args,
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["analytics-engineering", "marketing", "dbt"],
) as dag:

    generate_synthetic_data = BashOperator(
        task_id="generate_synthetic_data",
        bash_command=f"{VENV_BIN}/python {PROJECT_ROOT}/scripts/generate_data.py",
        doc_md="Stands in for an ad-platform / web-analytics / CRM extraction step. Regenerates the raw CSVs in data/raw/.",
    )

    load_raw_to_warehouse = BashOperator(
        task_id="load_raw_to_warehouse",
        bash_command=f"{VENV_BIN}/python {PROJECT_ROOT}/scripts/load_raw.py",
        doc_md="Loads the raw CSVs into the `raw` schema of the DuckDB warehouse, untransformed.",
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && "
            f"DBT_PROFILES_DIR={DBT_PROJECT_DIR} {VENV_BIN}/dbt build"
        ),
        doc_md="Runs the full dbt DAG: seeds -> staging -> intermediate -> marts, plus every schema and singular test.",
    )

    dbt_docs_generate = BashOperator(
        task_id="dbt_docs_generate",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && "
            f"DBT_PROFILES_DIR={DBT_PROJECT_DIR} {VENV_BIN}/dbt docs generate"
        ),
        doc_md="Regenerates the dbt documentation site (data catalog + lineage graph).",
    )

    generate_synthetic_data >> load_raw_to_warehouse >> dbt_build >> dbt_docs_generate