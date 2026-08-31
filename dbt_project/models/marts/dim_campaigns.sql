with campaigns as (
    select * from {{ ref('stg_campaigns') }}
),

channels as (
    select * from {{ ref('dim_channels') }}
)

select
    c.campaign_id,
    c.campaign_name,
    c.channel,
    ch.channel_type,
    ch.platform,
    c.objective,
    c.start_date,
    c.end_date,
    c.daily_budget,
    datediff('day', c.start_date, c.end_date) + 1 as flight_length_days
from campaigns c
left join channels ch on c.channel = ch.channel