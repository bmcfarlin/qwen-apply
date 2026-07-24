import aiosqlite
import os
from loguru import logger
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs.db")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    source TEXT,
    title TEXT,
    link TEXT UNIQUE,
    dtm TEXT,
    description TEXT,
    score REAL,
    resume TEXT,
    saved INTEGER DEFAULT 0,
    applied INTEGER DEFAULT 0,
    archived INTEGER DEFAULT 0,
    min_salary INTEGER,
    max_salary INTEGER
);
"""

_db = None


async def get_db():
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute(CREATE_TABLE_SQL)
        await _db.commit()
    return _db


async def close():
    global _db
    if _db:
        await _db.close()
        _db = None


async def upsert_job(fields):
    db = await get_db()
    link = fields.get("link")
    if not link:
        return

    cursor = await db.execute("SELECT id FROM job WHERE link = ?", (link,))
    row = await cursor.fetchone()

    if row:
        set_clauses = []
        values = []
        for key, value in fields.items():
            if key == "link":
                continue
            set_clauses.append(f"{key} = ?")
            values.append(_serialize(value))
        if set_clauses:
            values.append(link)
            sql = f"UPDATE job SET {', '.join(set_clauses)} WHERE link = ?"
            await db.execute(sql, values)
    else:
        columns = []
        placeholders = []
        values = []
        for key, value in fields.items():
            columns.append(key)
            placeholders.append("?")
            values.append(_serialize(value))
        sql = f"INSERT INTO job ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        await db.execute(sql, values)

    await db.commit()


async def find_jobs(filters=None, sort_by="dtm", sort_order="desc", offset=0, limit=20):
    db = await get_db()
    where_clause, params = _build_where(filters)

    allowed_sort = {"dtm", "score", "title"}
    if sort_by not in allowed_sort:
        sort_by = "dtm"
    order = "DESC" if sort_order == "desc" else "ASC"

    sql = f"SELECT * FROM job {where_clause} ORDER BY {sort_by} {order} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def count_jobs(filters=None):
    db = await get_db()
    where_clause, params = _build_where(filters)
    sql = f"SELECT COUNT(*) FROM job {where_clause}"
    cursor = await db.execute(sql, params)
    row = await cursor.fetchone()
    return row[0] if row else 0


async def find_one(job_id):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM job WHERE job_id = ?", (job_id,))
    row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def update_job(job_id, fields):
    db = await get_db()
    set_clauses = []
    values = []
    for key, value in fields.items():
        set_clauses.append(f"{key} = ?")
        values.append(_serialize(value))
    if set_clauses:
        values.append(job_id)
        sql = f"UPDATE job SET {', '.join(set_clauses)} WHERE job_id = ?"
        await db.execute(sql, values)
        await db.commit()


async def get_jobs_by_source(source):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM job WHERE source = ?", (source,))
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_all_jobs():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM job")
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


def _build_where(filters):
    if not filters:
        return "", []

    clauses = []
    params = []

    if "score" in filters:
        score_filter = filters["score"]
        if "$gte" in score_filter:
            clauses.append("score >= ?")
            params.append(score_filter["$gte"])
        if "$lte" in score_filter:
            clauses.append("score <= ?")
            params.append(score_filter["$lte"])

    if "source" in filters:
        clauses.append("source = ?")
        params.append(filters["source"])

    if "description" in filters:
        desc_filter = filters["description"]
        if "$regex" in desc_filter:
            clauses.append("description LIKE ?")
            params.append(f"%{desc_filter['$regex'].replace(chr(92) + 'b', '')}%")

    if filters.get("saved"):
        clauses.append("saved = 1")

    if filters.get("applied"):
        clauses.append("applied = 1")

    if "archived" in filters:
        arch = filters["archived"]
        if isinstance(arch, dict) and "$ne" in arch:
            if arch["$ne"]:
                clauses.append("(archived = 0 OR archived IS NULL)")
        else:
            clauses.append("archived = ?")
            params.append(1 if arch else 0)

    if clauses:
        return "WHERE " + " AND ".join(clauses), params
    return "", params


def _serialize(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def _row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    if "dtm" in d and d["dtm"]:
        try:
            d["dtm"] = datetime.fromisoformat(d["dtm"])
        except (ValueError, TypeError):
            pass
    return d
