with source as (

    select * from {{ source('raw', 'campaigns') }}

),

cleaned as (

    select
        campaign_id,
        trim(campaign_name) as campaign_name,
        lower(trim(channel)) as channel,
        objective,
        cast(start_date as date) as start_date,
        cast(end_date as date) as end_date,
        daily_budget

    from source

)

select * from cleaned