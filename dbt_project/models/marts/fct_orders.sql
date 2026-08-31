-- Grain: one row per order. An order-level companion to fct_attribution_touchpoints. For anyone who just wants "which
-- single channel gets credit" (first or last-touch) without joining through the full touchpoint-grain table

with weights as (
    select * from {{ ref('int_attribution_weights') }}
),

first_touch as (
    select order_id, channel as first_touch_channel, campaign_id as first_touch_campaign_id
    from weights
    where first_touch_weight = 1.0
),

last_touch as (
    select order_id, channel as last_touch_channel, campaign_id as last_touch_campaign_id
    from weights
    where last_touch_weight = 1.0
),

order_summary as (
    select
        order_id,
        user_id,
        order_timestamp,
        revenue,
        max(total_touches)  as num_touches,
        bool_or(is_dark_order) as is_dark_order
    from weights
    group by 1, 2, 3, 4
)

select
    o.order_id,
    o.user_id,
    o.order_timestamp,
    cast(o.order_timestamp as date) as order_date,
    o.revenue,
    o.num_touches,
    o.is_dark_order,
    ft.first_touch_channel,
    ft.first_touch_campaign_id,
    lt.last_touch_channel,
    lt.last_touch_campaign_id,
    cu.country,
    cu.device_type
from order_summary o
left join first_touch ft using (order_id)
left join last_touch lt using (order_id)
left join {{ ref('stg_customers') }} cu using (user_id)