-- Grain: one row per campaign per day. This is close to a straight pass through of stg_ad_spend, enriched with channel/campaign metadata so BI
-- tools can slice spend without an extra join.

with spend as (
    select * from {{ ref('stg_ad_spend') }}
),

campaigns as (
    select * from {{ ref('dim_campaigns') }}
)

select
    s.campaign_id,
    s.spend_date,
    c.channel,
    c.channel_type,
    c.platform,
    c.campaign_name,
    s.impressions,
    s.reported_clicks,
    s.spend,
    s.ctr,
    s.cpc
from spend s
left join campaigns c using (campaign_id)