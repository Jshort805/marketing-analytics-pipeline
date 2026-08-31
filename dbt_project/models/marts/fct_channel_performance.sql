-- Grain: one row per channel, totalled over the whole period covered by the data. ROAS/CAC are rolled up to channel-level TOTALS,
--Spend happens on the day of the click; revenue is credited on the day of the order, hours or days later. Dividing
-- same-day spend by same-day attributed revenue would imply a precision the data doesn't support for this project. 

with spend as (
    select
        channel,
        sum(spend)           as total_spend,
        sum(impressions)     as total_impressions,
        sum(reported_clicks) as total_clicks
    from {{ ref('fct_ad_spend') }}
    group by 1
),

attribution as (
    select
        channel,
        sum(first_touch_revenue) as first_touch_revenue,
        sum(last_touch_revenue)  as last_touch_revenue,
        sum(linear_revenue)      as linear_revenue,
        sum(first_touch_weight)  as first_touch_orders,
        sum(last_touch_weight)   as last_touch_orders,
        sum(linear_weight)       as linear_equivalent_orders
    from {{ ref('fct_attribution_touchpoints') }}
    where channel is not null
    group by 1
),

channels as (
    select * from {{ ref('dim_channels') }}
)

select
    c.channel,
    c.channel_type,
    c.is_paid,
    coalesce(s.total_spend, 0)         as total_spend,
    coalesce(s.total_impressions, 0)   as total_impressions,
    coalesce(s.total_clicks, 0)        as total_clicks,
    coalesce(a.first_touch_revenue, 0) as first_touch_revenue,
    coalesce(a.last_touch_revenue, 0)  as last_touch_revenue,
    coalesce(a.linear_revenue, 0)      as linear_revenue,
    coalesce(a.first_touch_orders, 0)  as first_touch_orders,
    coalesce(a.last_touch_orders, 0)   as last_touch_orders,
    round(coalesce(a.linear_equivalent_orders, 0), 1) as linear_equivalent_orders,
    case when s.total_clicks > 0 then round(s.total_spend / s.total_clicks, 4) end as avg_cpc,
    case when s.total_impressions > 0 then round(s.total_clicks::double / s.total_impressions, 5) end as avg_ctr,
    case when s.total_spend > 0 then round(a.first_touch_revenue / s.total_spend, 2) end as roas_first_touch,
    case when s.total_spend > 0 then round(a.last_touch_revenue / s.total_spend, 2) end  as roas_last_touch,
    case when s.total_spend > 0 then round(a.linear_revenue / s.total_spend, 2) end      as roas_linear,
    case when a.last_touch_orders > 0 then round(s.total_spend / a.last_touch_orders, 2) end as cac_last_touch,
    case when a.linear_equivalent_orders > 0 then round(s.total_spend / a.linear_equivalent_orders, 2) end as cac_linear
from channels c
left join spend s on c.channel = s.channel
left join attribution a on c.channel = a.channel