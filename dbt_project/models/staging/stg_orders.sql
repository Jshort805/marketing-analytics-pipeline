with source as (

    select * from {{ source('raw', 'orders') }}

),

deduplicated as (

    select
        *,
        row_number() over (
            partition by order_id
            order by order_timestamp
        ) as row_num

    from source

),

cleaned as (

    select
        order_id,
        user_id,
        cast(order_timestamp as timestamp) as order_timestamp,
        revenue,
        product_category

    from deduplicated
    where row_num = 1

)

select * from cleaned