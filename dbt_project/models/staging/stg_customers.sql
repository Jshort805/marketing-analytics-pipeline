with source as (

    select * from {{ source('raw', 'customers') }}

),

cleaned as (

    select
        user_id,
        cast(first_seen_date as date) as first_seen_date,
        cast(signup_date as date) as signup_date,
        country,
        coalesce(device_type, 'unknown') as device_type

    from source

)

select * from cleaned