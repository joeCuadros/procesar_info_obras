import os
from dotenv import load_dotenv, find_dotenv
from psycopg2.pool import SimpleConnectionPool

load_dotenv(find_dotenv())
DSN = {"host": os.getenv("POSTGRES_HOST", "localhost"), "port": int(os.getenv("POSTGRES_PORT", 5432)), "dbname": os.getenv("POSTGRES_DB"), "user": os.getenv("POSTGRES_USER"), "password": os.getenv("POSTGRES_PASSWORD")}
pool = SimpleConnectionPool(minconn=1, maxconn=10, **DSN)

def get_conn():
    return pool.getconn()

def put_conn(conn):
    pool.putconn(conn)