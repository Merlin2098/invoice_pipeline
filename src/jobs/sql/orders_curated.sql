select
    order_id,
    customer_id,
    order_total,
    order_date
from bronze_orders
where order_total is not null;

