from __future__ import annotations
import os
from datetime import datetime, timezone
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    category TEXT NOT NULL,
    buy_price REAL NOT NULL DEFAULT 0 CHECK (buy_price >= 0),
    sell_price REAL NOT NULL DEFAULT 0 CHECK (sell_price >= 0),
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price REAL NOT NULL DEFAULT 0 CHECK (unit_price >= 0),
    reason TEXT,
    actor_id INTEGER NOT NULL,
    actor_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_transactions_item ON transactions(item_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at);
"""

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.conn = None

    def _db(self):
        if not self.conn:
            raise RuntimeError("Database is not connected")
        return self.conn

    async def list_items(self, category: str | None = None):
        db = self._db()
        if category:
            cur = await db.execute("SELECT * FROM items WHERE category = ? ORDER BY category, name", (category,))
        else:
            cur = await db.execute("SELECT * FROM items ORDER BY category, name")
        return await cur.fetchall()

    async def get_item(self, name: str):
        cur = await self._db().execute("SELECT * FROM items WHERE name = ?", (name.strip(),))
        return await cur.fetchone()

    async def search_item_names(self, current: str, limit: int = 25):
        cur = await self._db().execute(
            "SELECT name FROM items WHERE name LIKE ? ORDER BY name LIMIT ?",
            (f"{current}%", limit),
        )
        return [r[0] for r in await cur.fetchall()]

    async def categories(self, current: str = "", limit: int = 25):
        cur = await self._db().execute(
            "SELECT DISTINCT category FROM items WHERE category LIKE ? ORDER BY category LIMIT ?",
            (f"{current}%", limit),
        )
        return [r[0] for r in await cur.fetchall()]

    async def create_item(self, name, category, buy_price, sell_price):
        ts = now_iso()
        db = self._db()
        await db.execute(
            "INSERT INTO items(name, category, buy_price, sell_price, quantity, created_at, updated_at) VALUES(?,?,?,?,0,?,?)",
            (name.strip(), category.strip(), buy_price, sell_price, ts, ts),
        )
        await db.commit()
        return await self.get_item(name)

    async def update_item(self, old_name, name, category, buy_price, sell_price):
        db = self._db()
        ts = now_iso()
        await db.execute(
            "UPDATE items SET name=?, category=?, buy_price=?, sell_price=?, updated_at=? WHERE name=?",
            (name.strip(), category.strip(), buy_price, sell_price, ts, old_name.strip()),
        )
        await db.commit()
        return await self.get_item(name)

    async def change_stock(self, name, delta, action, unit_price, reason, actor_id, actor_name):
        db = self._db()
        async with db.execute("BEGIN"):
            cur = await db.execute("SELECT * FROM items WHERE name = ?", (name.strip(),))
            item = await cur.fetchone()
            if not item:
                raise ValueError("Item not found.")
            new_qty = item["quantity"] + delta
            if new_qty < 0:
                raise ValueError(f"Not enough stock. Current stock: {item['quantity']}.")
            ts = now_iso()
            await db.execute("UPDATE items SET quantity=?, updated_at=? WHERE id=?", (new_qty, ts, item["id"]))
            await db.execute(
                "INSERT INTO transactions(item_id, action, quantity, unit_price, reason, actor_id, actor_name, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (item["id"], action, abs(delta), unit_price, reason, actor_id, actor_name, ts),
            )
        await db.commit()
        return await self.get_item(name)

    async def history(self, item_name: str | None = None, limit: int = 20):
        db = self._db()
        if item_name:
            cur = await db.execute(
                "SELECT t.*, i.name AS item_name FROM transactions t JOIN items i ON i.id=t.item_id WHERE i.name=? ORDER BY t.id DESC LIMIT ?",
                (item_name.strip(), limit),
            )
        else:
            cur = await db.execute(
                "SELECT t.*, i.name AS item_name FROM transactions t JOIN items i ON i.id=t.item_id ORDER BY t.id DESC LIMIT ?",
                (limit,),
            )
        return await cur.fetchall()

    async def stats(self):
        db = self._db()
        cur = await db.execute("SELECT COUNT(*) AS item_count, COALESCE(SUM(quantity),0) AS units, COALESCE(SUM(quantity*buy_price),0) AS cost_value, COALESCE(SUM(quantity*sell_price),0) AS retail_value FROM items")
        return await cur.fetchone()
