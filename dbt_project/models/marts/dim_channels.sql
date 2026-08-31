-- Static reference data (which channels are paid, what platform each runs on) lives in a dbt seed 
--rather than being derived from transaction data, I maintain it. This model
-- is a check so other marts can ref() a "dim_" name instead of reaching for the seed directly

select * from {{ ref('channel_reference') }}