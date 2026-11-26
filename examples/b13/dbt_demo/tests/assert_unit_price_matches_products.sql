-- 単発テスト (singular test): 返った行が 1 行でもあれば不合格。
-- 明細の単価が商品マスタの価格と食い違う行を探す (正確さ)。
select i.order_id, i.line_no, i.unit_price, p.price
from main.order_items as i
join main.products as p on i.product_id = p.product_id
where i.unit_price <> p.price
