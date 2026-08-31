"""
load_raw.py
------------
Loads the generated CSVs into a DuckDB warehouse file, under a raw schema.

WHY 
Simulates how a custom Python extractor hitting the Google Ads / Meta Ads / Shopify APIs would land data
data straight into your warehouse. dbt then takes over from there. This script does
not clean, dedupe, or standardize anything. That work happens in the dbt
staging layer "raw ingestion" vs "transformation".

DuckDB is used as a stand-in for a cloud warehouse.
"""

import duckdb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "warehouse.duckdb"

RAW_TABLES = {
    "campaigns": "campaigns.csv",
    "ad_spend": "ad_spend.csv",
    "clicks": "clicks.csv",
    "customers": "customers.csv",
    "orders": "orders.csv",
}


def main():
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")

    for table_name, csv_file in RAW_TABLES.items():
        csv_path = RAW_DIR / csv_file
        con.execute(f"""
            CREATE OR REPLACE TABLE raw.{table_name} AS
            SELECT * FROM read_csv_auto('{csv_path.as_posix()}', header=True)
        """)
        count = con.execute(f"SELECT COUNT(*) FROM raw.{table_name}").fetchone()[0]
        print(f"  raw.{table_name:<10} <- {csv_file:<20} ({count:,} rows)")

    print(f"\nLoaded into {DB_PATH}")
    con.close()


if __name__ == "__main__":
    main()
