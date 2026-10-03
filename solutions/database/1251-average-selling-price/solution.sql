# Write your MySQL query statement below
select p.product_id, ROUND(
    COALESCE(SUM(p.price * u.units)/ sum(u.units),0),
    2
) As average_price
from Prices p
Left join UnitsSold u
    ON p.product_id = u.product_id
    and u.purchase_date BETWEEN p.start_date and p.end_date
GROUP BY p.product_id;
