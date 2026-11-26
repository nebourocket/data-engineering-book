import duckdb

con = duckdb.connect()
con.execute("CREATE TABLE products (product_id INTEGER, name VARCHAR)")
con.execute("SELECT * FROM product")
