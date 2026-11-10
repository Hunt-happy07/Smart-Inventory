"""
database_mysql.py
------------------
MySQL version of database.py — use this instead if you've installed
MySQL on your own Windows machine and created a database for this project.

SETUP BEFORE RUNNING THIS FILE:
1. Install MySQL Community Server + MySQL Workbench (dev.mysql.com/downloads)
2. In MySQL Workbench, run:  CREATE DATABASE inventory_db;
3. Install the connector:    pip install mysql-connector-python
4. Fill in YOUR MySQL root password below (or a dedicated user's password)
5. Rename this file to database.py (replacing the SQLite one), OR
   change the import in app.py and ml_model.py from
   "from database import ..." to "from database_mysql import ..."

Run this file once to create the tables: python database_mysql.py
"""

import mysql.connector
from mysql.connector import Error

# ---- EDIT THESE 4 LINES WITH YOUR OWN MYSQL DETAILS ----
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "YOUR_MYSQL_PASSWORD_HERE"
DB_NAME = "inventory_db"
# ----------------------------------------------------------


def get_connection():
    """
    Returns a live connection to the MySQL database.
    Every route in app.py calls this to get a fresh connection.
    """
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )
    return conn


class DictCursorConn:
    """
    Small wrapper so the rest of the app (written for sqlite3.Row,
    which lets you do row['column_name']) works unchanged with MySQL,
    which normally returns plain tuples.
    """
    def __init__(self, conn):
        self._conn = conn

    def execute(self, query, params=()):
        cur = self._conn.cursor(dictionary=True)  # dictionary=True -> row['col'] access
        cur.execute(query, params)
        return cur

    def executemany(self, query, seq_of_params):
        cur = self._conn.cursor()
        cur.executemany(query, seq_of_params)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def init_db():
    try:
        conn = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        cur.execute(f"USE {DB_NAME}")

        # PRODUCT table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                category VARCHAR(100) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                quantity INT NOT NULL DEFAULT 0,
                reorder_level INT NOT NULL DEFAULT 10,
                barcode VARCHAR(64) NULL UNIQUE,
                expiry_date DATE NULL
            )
        """)

        # SALES HISTORY table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sales_history (
                sale_id INT AUTO_INCREMENT PRIMARY KEY,
                product_id INT NOT NULL,
                sale_date DATE NOT NULL,
                qty_sold INT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(product_id)
            )
        """)

        # SUPPLIER table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS suppliers (
                supplier_id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                contact VARCHAR(50),
                product_id INT,
                FOREIGN KEY (product_id) REFERENCES products(product_id)
            )
        """)

        # Upgrading an OLD MySQL database? Run these two lines once in Workbench:
        #   ALTER TABLE products ADD COLUMN barcode VARCHAR(64) NULL UNIQUE;
        #   ALTER TABLE products ADD COLUMN expiry_date DATE NULL;
        conn.commit()
        conn.close()
        print(f"MySQL database '{DB_NAME}' initialized successfully.")

    except Error as e:
        print("MySQL connection failed. Check your host/user/password in database_mysql.py")
        print("Error detail:", e)


if __name__ == "__main__":
    init_db()
