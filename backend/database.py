import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "foodvision.db"


def normalize_food_name(text: str) -> str:

    if not text or not isinstance(text, str):
        return ""
    s = text.strip().lower().replace(" ", "_").replace("-", "_")
    s = re.sub(r"_+", "_", s).strip("_")  
    return s or "unknown"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            image_path TEXT,
            original_label TEXT,
            corrected_label TEXT,
            calories REAL,
            protein REAL,
            carbs REAL,
            fat REAL,
            raw_response TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS food_cache (
            name TEXT PRIMARY KEY,
            corrected_label TEXT NOT NULL,
            calories REAL NOT NULL,
            protein REAL NOT NULL,
            carbs REAL NOT NULL,
            fat REAL NOT NULL,
            base_unit TEXT NOT NULL DEFAULT '100g',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS meal_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 1,
            calories REAL NOT NULL,
            protein REAL NOT NULL,
            carbs REAL NOT NULL,
            fat REAL NOT NULL,
            FOREIGN KEY (meal_id) REFERENCES uploads(id)
        )
    """)

    conn.commit()
    conn.close()


def get_food_from_cache(normalized_name: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT name, corrected_label, calories, protein, carbs, fat, base_unit
        FROM food_cache WHERE name = ?
    """, (normalized_name,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def insert_food_cache(
    name: str,
    corrected_label: str,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    base_unit: str = "100g",
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO food_cache (name, corrected_label, calories, protein, carbs, fat, base_unit, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(name) DO UPDATE SET
            corrected_label = excluded.corrected_label,
            calories = excluded.calories,
            protein = excluded.protein,
            carbs = excluded.carbs,
            fat = excluded.fat,
            base_unit = excluded.base_unit,
            updated_at = datetime('now')
    """, (name, corrected_label, calories, protein, carbs, fat, base_unit))
    conn.commit()
    conn.close()


def insert_upload(
    image_path: str | None,
    original_label: str | None,
    corrected_label: str | None,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    raw_response: str | None = None,
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO uploads (image_path, original_label, corrected_label, calories, protein, carbs, fat, raw_response)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (image_path, original_label, corrected_label, calories, protein, carbs, fat, raw_response))
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_meal(meal_id: int) -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM uploads WHERE id = ?", (meal_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_meal_correction(
    meal_id: int,
    corrected_label: str,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    items: list[dict],
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE uploads
        SET corrected_label = ?, calories = ?, protein = ?, carbs = ?, fat = ?
        WHERE id = ?
    """, (corrected_label, calories, protein, carbs, fat, meal_id))
    cur.execute("DELETE FROM meal_items WHERE meal_id = ?", (meal_id,))
    for it in items:
        m = it.get("macros", {})
        cur.execute("""
            INSERT INTO meal_items (meal_id, name, quantity, calories, protein, carbs, fat)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            meal_id,
            it.get("name", ""),
            it.get("quantity", 1),
            m.get("calories", 0),
            m.get("protein", 0),
            m.get("carbs", 0),
            m.get("fat", 0),
        ))
    conn.commit()
    conn.close()


def insert_meal_items(meal_id: int, items: list[dict]) -> None:
    if not items:
        return
    conn = get_connection()
    cur = conn.cursor()
    for it in items:
        m = it.get("macros", {})
        cur.execute("""
            INSERT INTO meal_items (meal_id, name, quantity, calories, protein, carbs, fat)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            meal_id,
            it.get("name", ""),
            it.get("quantity", 1),
            m.get("calories", 0),
            m.get("protein", 0),
            m.get("carbs", 0),
            m.get("fat", 0),
        ))
    conn.commit()
    conn.close()


def get_meal_items(meal_id: int) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT name, quantity, calories, protein, carbs, fat
        FROM meal_items WHERE meal_id = ? ORDER BY id
    """, (meal_id,))
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "name": row["name"],
            "quantity": row["quantity"],
            "macros": {
                "calories": row["calories"],
                "protein": row["protein"],
                "carbs": row["carbs"],
                "fat": row["fat"],
            },
        }
        for row in rows
    ]


def get_history(limit: int = 50) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, created_at, image_path, original_label, corrected_label, calories, protein, carbs, fat
        FROM uploads ORDER BY created_at DESC LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    out = []
    for row in rows:
        meal_id = row["id"]
        items = get_meal_items(meal_id)
        out.append({
            "meal_id": meal_id,
            "created_at": row["created_at"],
            "image_path": row["image_path"],
            "original_label": row["original_label"],
            "corrected_label": row["corrected_label"],
            "totals": {
                "calories": row["calories"],
                "protein": row["protein"],
                "carbs": row["carbs"],
                "fat": row["fat"],
            },
            "items": items,
        })
    return out


def delete_meal(meal_id: int) -> list[str]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT image_path FROM uploads WHERE id = ?", (meal_id,))
    row = cur.fetchone()
    image_paths: list[str] = []
    if row and row["image_path"]:
        image_paths.append(row["image_path"])
    cur.execute("DELETE FROM meal_items WHERE meal_id = ?", (meal_id,))
    cur.execute("DELETE FROM uploads WHERE id = ?", (meal_id,))
    conn.commit()
    conn.close()
    return image_paths


def clear_history() -> list[str]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT image_path FROM uploads")
    rows = cur.fetchall()
    image_paths = [row["image_path"] for row in rows if row["image_path"]]
    cur.execute("DELETE FROM meal_items")
    cur.execute("DELETE FROM uploads")
    conn.commit()
    conn.close()
    return image_paths

