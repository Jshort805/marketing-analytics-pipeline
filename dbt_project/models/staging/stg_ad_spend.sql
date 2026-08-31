-- Ad-platform daily performance rows. Types renamed/derived a couple of fields (cpc, ctr) so downstream marts don't all 
--have to recompute the same ratios.

with source as (
    select * from {{ source('raw', 'ad_spend') }}
)

select
    cast(campaign_id as integer)   as campaign_id,
    cast(date as date)             as spend_date,
    impressions,
    clicks                         as reported_clicks,
    spend,
    case when impressions > 0 then round(clicks / impressions, 5) end as ctr,
    case when clicks > 0 then round(spend / clicks, 4) end            as cpc
from source