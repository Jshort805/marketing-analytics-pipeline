-- For every order, find every marketing touchpoint the same user had in the N days beforehand (the attribution lookback window, can set via the
-- attribution_lookback_days variable in dbt_project.yml). This is a LEFT JOIN for "dark" orders) ie they don't have a touchpoint, so they still get
-- one output row, with NULL touchpoint fields

with orders as (
    select * from {{ ref('stg_orders') }}
),

clicks as (
    select * from {{ ref('stg_clicks') }}
),

joined as (
    select
        o.order_id,
        o.user_id,
        o.order_timestamp,
        o.revenue,
        c.click_id,
        c.event_timestamp as touch_timestamp,
        c.channel,
        c.campaign_id
    from orders o
    left join clicks c
        on c.user_id = o.user_id
        and c.event_timestamp <= o.order_timestamp
        and c.event_timestamp >= o.order_timestamp - interval '{{ var("attribution_lookback_days", 30) }} days'
)

select
    *,
    row_number() over (partition by order_id order by touch_timestamp asc) as touch_position,
    count(click_id) over (partition by order_id)                           as total_touches
from joined