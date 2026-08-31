with source as (

    select * from {{ source('raw', 'clicks') }}

),

cleaned as (

    select
        click_id,
        user_id,
        cast(event_timestamp as timestamp) as event_timestamp,
        channel,
        campaign_id,
        coalesce(device_type, 'unknown') as device_type,
        landing_page,
        country

    from source

)

select * from cleaned