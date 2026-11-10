# Connecting to Your Own MySQL Database (Windows)

By default this project uses **SQLite** — a single file (`inventory.db`), no
install needed. That's why it "just worked" with zero setup.

If you want to instead use a **MySQL database you create yourself on
Windows** (common ask from professors who want to see MySQL specifically),
here's exactly how:

## 1. Install MySQL
- Download **MySQL Community Server** + **MySQL Workbench**:
  https://dev.mysql.com/downloads/installer/
- During setup, choose "Developer Default", set a root password, remember it.

## 2. Create your database
Open MySQL Workbench, connect with root + your password, run:
```sql
CREATE DATABASE inventory_db;
```

## 3. Install the Python connector
In your project terminal:
```bash
pip install mysql-connector-python
```

## 4. Use the MySQL version of database.py
This project includes `database_mysql.py`, already written for MySQL.

Open it and edit these 4 lines with your own details:
```python
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "YOUR_MYSQL_PASSWORD_HERE"   # <-- put your real password
DB_NAME = "inventory_db"
```

Then run it once to create the tables:
```bash
python database_mysql.py
```
You should see: `MySQL database 'inventory_db' initialized successfully.`

## 5. Point the rest of the app at MySQL instead of SQLite

Because MySQL and SQLite return data slightly differently, you need to swap
**one line** in three files — change:
```python
from database import get_connection
```
to:
```python
from database_mysql import get_connection
```

Do this in:
- `app.py`
- `ml_model.py`
- `seed_data.py`

Then also change every `conn.execute("...")` that currently uses
`?` placeholders — MySQL uses `%s` instead of `?`. This means in
`app.py`, `seed_data.py`, and `ml_model.py`, replace every `?` inside a SQL
query string with `%s`.

Example — before (SQLite):
```python
conn.execute("SELECT * FROM products WHERE product_id = ?", (product_id,))
```
After (MySQL):
```python
conn.execute("SELECT * FROM products WHERE product_id = %s", (product_id,))
```

## 6. Re-seed and run
```bash
python seed_data.py
python app.py
```

## Which should you actually use for your project?

**Honestly — for a first project, stick with SQLite.** It's simpler,
requires zero installation on the lab/exam computer, and your DBMS/data
model is identical either way (same tables, same relationships). Switch to
MySQL only if your guide specifically requires it, since MySQL adds real
setup complexity (installing the server, managing credentials, network
issues) that has nothing to do with what your project is actually meant to
demonstrate.

If your professor just wants to see "a real database," you can also just
show them MySQL Workbench with the same schema running as a manual DB —
without needing your whole app to depend on it.
