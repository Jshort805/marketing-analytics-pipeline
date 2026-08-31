-- Grain: one row per (order, touchpoint) pair; the most granular attribution table,

select
    order_id,
    user_id,
    order_timestamp,
    revenue,
    click_id,
    touch_timestamp,
    channel,
    campaign_id,
    touch_position,
    total_touches,
    is_dark_order,
    first_touch_weight,
    last_touch_weight,
    linear_weight,
    round(revenue * first_touch_weight, 2) as first_touch_revenue,
    round(revenue * last_touch_weight, 2)  as last_touch_revenue,
    round(revenue * linear_weight, 2)      as linear_revenue
from {{ ref('int_attribution_weights') }}