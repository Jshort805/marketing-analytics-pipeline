-- Turns each (order, touchpoint) pair into a "credit weight" under three competing attribution models. A weight of 1.0 means "100% of this order's
-- revenue belongs to this touchpoint's channel"; weights for a given order always sum to 1.0 (or 0.0 for dark orders, which get no credit anywhere
-- that revenue still shows up as a whole in fct_orders, just not attributed to any channel).
--
--   first_touch_weight : 1.0 on the very first touchpoint only
--   last_touch_weight  : 1.0 on the very last touchpoint only
--   linear_weight       : split evenly across every touchpoint in the journey

with touchpoints as (
    select * from {{ ref('int_order_touchpoints') }}
)

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
    (total_touches = 0) as is_dark_order,
    case when total_touches > 0 and touch_position = 1             then 1.0 else 0.0 end as first_touch_weight,
    case when total_touches > 0 and touch_position = total_touches then 1.0 else 0.0 end as last_touch_weight,
    case when total_touches > 0                                    then 1.0 / total_touches else 0.0 end as linear_weight
from touchpoints