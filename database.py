import sqlite3

DB_FILE = "steam.db"


def create_database():
    """Creates the tables (leaves them alone if they already exist)."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                appid        INTEGER  PRIMARY KEY,
                name         TEXT     NOT NULL,
                developer    TEXT     DEFAULT '',
                publisher    TEXT     DEFAULT '',
                genre        TEXT     DEFAULT '',
                release_date TEXT     DEFAULT '',
                is_free      INTEGER  DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS player_counts (
                id           INTEGER  PRIMARY KEY AUTOINCREMENT,
                appid        INTEGER  NOT NULL,
                player_count INTEGER  NOT NULL,
                timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id               INTEGER  PRIMARY KEY AUTOINCREMENT,
                appid            INTEGER  NOT NULL,
                price_tr         REAL     NOT NULL,
                original_price   REAL     DEFAULT 0,
                discount_percent INTEGER  DEFAULT 0,
                timestamp        DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Add the is_free column to older databases (ignore the error if it exists)
        try:
            conn.execute("ALTER TABLE games ADD COLUMN is_free INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass


class DB:
    """All database access goes through this class (static methods, no instance needed)."""

    @staticmethod
    def connect():
        return sqlite3.connect(DB_FILE)

    @staticmethod
    def upsert_game(appid, name, developer="", publisher="",
                    genre="", release_date="", is_free=False):
        with DB.connect() as conn:
            conn.execute("""
                INSERT INTO games(appid, name, developer, publisher,
                                  genre, release_date, is_free)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(appid) DO UPDATE SET
                name     = excluded.name,
                developer= excluded.developer,
                publisher= excluded.publisher,
                genre    = excluded.genre,
                release_date = excluded.release_date,
                is_free  = excluded.is_free
            """, (appid, name, developer, publisher, genre, release_date, int(is_free)))

    @staticmethod
    def is_free_game(appid):
        with DB.connect() as conn:
            row = conn.execute(
                "SELECT is_free FROM games WHERE appid=?", (appid,)
            ).fetchone()
            return bool(row[0]) if row else False

    @staticmethod
    def save_player_count(appid, count, timestamp=None):
        with DB.connect() as conn:
            if timestamp:
                conn.execute(
                    "INSERT INTO player_counts(appid, player_count, timestamp) VALUES (?,?,?)",
                    (appid, count, timestamp))
            else:
                conn.execute(
                    "INSERT INTO player_counts(appid, player_count) VALUES (?,?)",
                    (appid, count))

    @staticmethod
    def save_price(appid, price, original, discount, timestamp=None):
        with DB.connect() as conn:
            if timestamp:
                conn.execute("""
                    INSERT INTO price_history
                        (appid, price_tr, original_price, discount_percent, timestamp)
                    VALUES (?,?,?,?,?)
                """, (appid, price, original, discount, timestamp))
            else:
                conn.execute("""
                    INSERT INTO price_history
                        (appid, price_tr, original_price, discount_percent)
                    VALUES (?,?,?,?)
                """, (appid, price, original, discount))

    @staticmethod
    def all_games():
        with DB.connect() as conn:
            return conn.execute("SELECT appid, name FROM games ORDER BY name").fetchall()

    @staticmethod
    def has_data(appid):
        with DB.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM player_counts WHERE appid=?", (appid,)
            ).fetchone()[0]
            return count > 0

    @staticmethod
    def player_history(appid, start, end, time_unit):
        grouping = {
            "hour":  "strftime('%Y-%m-%d %H:00:00', timestamp)",
            "day":   "strftime('%Y-%m-%d', timestamp)",
            "month": "strftime('%Y-%m', timestamp)",
        }[time_unit]
        with DB.connect() as conn:
            return conn.execute(f"""
                SELECT {grouping} AS t, AVG(player_count)
                FROM player_counts
                WHERE appid = ? AND timestamp BETWEEN ? AND ?
                GROUP BY t
                ORDER BY t
            """, (appid, start, end)).fetchall()

    @staticmethod
    def price_history(appid, start, end):
        with DB.connect() as conn:
            return conn.execute("""
                SELECT strftime('%Y-%m-%d', timestamp), AVG(price_tr)
                FROM price_history
                WHERE appid = ? AND timestamp BETWEEN ? AND ?
                GROUP BY strftime('%Y-%m-%d', timestamp)
                ORDER BY timestamp
            """, (appid, start, end)).fetchall()

    @staticmethod
    def clear_data(appid):
        """Deletes every player-count and price record of a game."""
        with DB.connect() as conn:
            conn.execute("DELETE FROM player_counts WHERE appid=?", (appid,))
            conn.execute("DELETE FROM price_history  WHERE appid=?", (appid,))
