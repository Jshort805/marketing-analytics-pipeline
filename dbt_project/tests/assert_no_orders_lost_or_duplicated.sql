-- Reconciles fct_orders back to stg_orders on both row count and total revenue. If the touchpoint join ever fanned out (accidentally duplicating
-- orders) or dropped rows, this would catch it

with staging as (
    select count(*) as order_count, sum(revenue) as total_revenue
    from {{ ref('stg_orders') }}
),

marts as (
    select count(*) as order_count, sum(revenue) as total_revenue
    from {{ ref('fct_orders') }}
)

select
    staging.order_count   as staging_order_count,
    marts.order_count     as marts_order_count,
    staging.total_revenue as staging_total_revenue,
    marts.total_revenue   as marts_total_revenue
from staging, marts
where staging.order_count != marts.order_count
   or abs(staging.total_revenue - marts.total_revenue) > 0.01