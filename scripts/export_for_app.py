import duckdb
con = duckdb.connect("warehouse.duckdb", read_only=True)
con.sql("COPY (SELECT * FROM fct_channel_performance) TO 'app/data/channel_performance.parquet'")