import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "contacts.db"))


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                department TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(contacts)")}
        if "note" not in cols:
            conn.execute("ALTER TABLE contacts ADD COLUMN note TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone)")


def add_contact(name: str, phone: str, department: str) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO contacts (name, phone, department) VALUES (?, ?, ?)",
            (name, phone, department),
        )
        return cur.lastrowid


def get_contact(contact_id: int) -> sqlite3.Row | None:
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()


def update_contact(contact_id: int, field: str, value: str) -> None:
    if field not in ("name", "phone", "department", "note"):
        raise ValueError(f"bad field: {field}")
    with _conn() as conn:
        conn.execute(
            f"UPDATE contacts SET {field} = ? WHERE id = ?", (value, contact_id)
        )


def append_note(contact_id: int, text: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE contacts SET note = TRIM(CASE WHEN note = '' THEN ? "
            "ELSE note || char(10) || ? END) WHERE id = ?",
            (text, text, contact_id),
        )


def delete_contact(contact_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))


def get_departments() -> list[tuple[str, int]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT department, COUNT(*) AS cnt FROM contacts "
            "GROUP BY department ORDER BY department"
        ).fetchall()
    return [(r["department"], r["cnt"]) for r in rows]


def get_contacts_by_department(department: str) -> list[sqlite3.Row]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contacts WHERE department = ?", (department,)
        ).fetchall()
    return sorted(rows, key=lambda r: r["name"].lower())


def search_contacts(query: str) -> list[sqlite3.Row]:
    # Фильтрация в Python: LIKE/lower() в SQLite нечувствительны к регистру
    # только для ASCII, а имена — кириллица.
    q = query.lower()
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM contacts").fetchall()
    found = [
        r
        for r in rows
        if q in r["name"].lower() or q in r["phone"].lower() or q in r["note"].lower()
    ]
    return sorted(found, key=lambda r: r["name"].lower())


def digits(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())


def phone_key(text: str) -> str:
    # Мобильные 8XXX и +7XXX — один и тот же номер.
    d = digits(text)
    if len(d) == 11 and d[0] == "8":
        d = "7" + d[1:]
    return d


def find_by_phone(query: str) -> list[sqlite3.Row]:
    # Сравнение по одним цифрам: "8-900-123-45-67" находится и по "89001234567".
    q = digits(query)
    if not q:
        return []
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM contacts").fetchall()
    key = phone_key(query)
    exact = [r for r in rows if phone_key(r["phone"]) == key]
    if exact:
        return sorted(exact, key=lambda r: r["name"].lower())
    partial = [r for r in rows if q in digits(r["phone"])]
    return sorted(partial, key=lambda r: r["name"].lower())
