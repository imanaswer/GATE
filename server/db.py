from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from server.settings import settings

# DATABASE_URL must point at Supabase's TRANSACTION pooler (port 6543), not the
# direct database port. Serverless instances × direct connections is the classic
# way to exhaust Postgres. The pool below is a small per-instance reuse cache on
# top of that pooler — deliberately tiny, not a second connection pool.
def _no_server_side_prepare(conn) -> None:
    """pgbouncer in transaction mode hands each statement whatever backend
    connection is free, so a server-side prepared statement is not there the
    next time it is used. psycopg auto-prepares after the 5th execution of the
    same query text, which is why this only ever bit loops: building a paper
    runs one SELECT per question, and the 6th blew up with
    DuplicatePreparedStatement. Set on the pool so every caller is covered, not
    just the loop that happened to be reported."""
    conn.prepare_threshold = None


pool = ConnectionPool(
    settings.database_url,
    min_size=0,
    max_size=settings.db_pool_max,
    kwargs={"row_factory": dict_row, "autocommit": True},
    configure=_no_server_side_prepare,
    open=False,
)


@contextmanager
def cursor():
    """Autocommit cursor for single statements."""
    with pool.connection() as conn, conn.cursor() as cur:
        yield cur


@contextmanager
def transaction():
    """All-or-nothing. Use for anything that writes more than one row."""
    with pool.connection() as conn:
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.autocommit = True


def fetch_one(sql: str, params: tuple = ()):
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetch_all(sql: str, params: tuple = ()):
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()
