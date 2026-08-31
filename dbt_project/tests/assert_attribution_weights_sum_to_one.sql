-- For every order that has at least one touchpoint, each attribution model's weights must sum to exactly 1.0. If this ever fails, the
-- attribution logic itself is broken, not the data.

select
    order_id,
    sum(first_touch_weight) as first_touch_total,
    sum(last_touch_weight)  as last_touch_total,
    sum(linear_weight)      as linear_total
from {{ ref('fct_attribution_touchpoints') }}
where not is_dark_order
group by order_id
having
    abs(sum(first_touch_weight) - 1.0) > 0.001
    or abs(sum(last_touch_weight) - 1.0) > 0.001
    or abs(sum(linear_weight) - 1.0) > 0.001