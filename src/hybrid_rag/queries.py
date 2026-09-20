from __future__ import annotations

from .models import QueryPlan


SQL_SCHEMA = """
SQLite tables: customers(customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state),
orders(order_id, customer_id, order_status, order_purchase_timestamp, order_delivered_customer_date, order_estimated_delivery_date),
order_items(order_id, order_item_id, product_id, seller_id, price, freight_value),
products(product_id, product_category_name, product_weight_g, product_length_cm, product_height_cm, product_width_cm),
sellers(seller_id, seller_zip_code_prefix, seller_city, seller_state),
category_translation(product_category_name, product_category_name_english).
Useful views: order_summary(order_id, customer_id, order_status, item_revenue, freight_revenue, order_value, delivery_delay_days),
category_sales(category_name, order_count, item_revenue, freight_revenue), seller_sales(seller_id, seller_state, order_count, item_revenue, freight_revenue).
""".strip()

GRAPH_SCHEMA = """
Neo4j labels/properties: Customer(customer_id, customer_unique_id, state), Order(order_id, status),
Product(product_id, category_name), Seller(seller_id, state), Category(name), Region(state).
Relationships: (Customer)-[:PLACED]->(Order)-[:CONTAINS]->(Product),
(Order)-[:FULFILLED_BY]->(Seller), (Product)-[:IN_CATEGORY]->(Category),
(Customer)-[:LOCATED_IN]->(Region), (Seller)-[:LOCATED_IN]->(Region).
""".strip()


MOCK_SQL_PLANS = {
    "top_categories": QueryPlan(
        engine="SQL",
        statement="SELECT category_name, order_count, ROUND(item_revenue, 2) AS item_revenue, ROUND(freight_revenue, 2) AS freight_revenue FROM category_sales ORDER BY item_revenue DESC LIMIT 5",
    ),
    "delivery_delay": QueryPlan(
        engine="SQL",
        statement="SELECT ROUND(AVG(delivery_delay_days), 2) AS average_delivery_delay_days FROM order_summary WHERE delivery_delay_days IS NOT NULL",
    ),
}


MOCK_GRAPH_PLANS = {
    "co_purchased_products": QueryPlan(
        engine="GRAPH",
        statement="""
        MATCH (target:Product {product_id: $product_id})<-[:CONTAINS]-(:Order)-[:FULFILLED_BY]->(seller:Seller)<-[:FULFILLED_BY]-(:Order)-[:CONTAINS]->(other:Product)
        WHERE other.product_id <> target.product_id
        RETURN other.product_id AS product_id, other.category_name AS category_name, count(*) AS same_seller_count
        ORDER BY same_seller_count DESC
        LIMIT 10
        """,
        parameters=[],
    ),
    "customer_product_path": QueryPlan(
        engine="GRAPH",
        statement="""
        MATCH (customer:Customer {customer_id: $customer_id})-[:PLACED]->(order:Order)-[:CONTAINS]->(product:Product)
        RETURN customer.customer_id AS customer_id, order.order_id AS order_id, product.product_id AS product_id, product.category_name AS category_name
        ORDER BY order.order_id
        LIMIT 50
        """,
        parameters=[],
    ),
}
