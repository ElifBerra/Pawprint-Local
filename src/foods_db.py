"""The food catalogue.

Foods live in SQLite rather than in the JSON file, because the point is that
the user adds their own from the bag in their kitchen. `data/foods.json` is
only seed data — clearly marked as samples — so the dropdown is not empty on
first run.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from . import config
from .db import connect
from .models import Food

logger = logging.getLogger(__name__)

SEED_PATH = config.ROOT_DIR / "data" / "foods.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS foods (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    species        TEXT    NOT NULL DEFAULT 'both',
    kcal_per_100g  REAL    NOT NULL,
    protein_pct    REAL    NOT NULL,
    fat_pct        REAL    NOT NULL,
    fibre_pct      REAL    DEFAULT 0,
    moisture_pct   REAL    DEFAULT 10,
    ash_pct        REAL    DEFAULT 0,
    pack_size_g    REAL,
    life_stage     TEXT,
    is_sample      INTEGER DEFAULT 0,
    created_at     TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name)
);
"""

COLUMNS = ("id, name, species, kcal_per_100g, protein_pct, fat_pct, "
           "fibre_pct, moisture_pct, ash_pct, pack_size_g, life_stage, "
           "is_sample")


def _row_to_food(row) -> Food:
    return Food(
        id=row[0], name=row[1], species=row[2], kcal_per_100g=row[3],
        protein_pct=row[4], fat_pct=row[5], fibre_pct=row[6],
        moisture_pct=row[7], ash_pct=row[8], pack_size_g=row[9],
        life_stage=row[10], is_sample=bool(row[11]),
    )


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        existing = {r[1] for r in conn.execute("PRAGMA table_info(foods)")}
        for column, definition in (("pack_size_g", "REAL"),
                                   ("life_stage", "TEXT")):
            if column not in existing:
                conn.execute(f"ALTER TABLE foods ADD COLUMN {column} {definition}")


def seed_from_json(path=SEED_PATH) -> int:
    """Load the sample foods once. Existing entries are left alone."""
    if not path.exists():
        return 0

    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    added = 0
    for entry in payload.get("foods", []):
        if get_by_name(entry["name"]) is not None:
            continue
        save(Food(
            name=entry["name"],
            species=entry.get("species", "both"),
            kcal_per_100g=entry["kcal_per_100g"],
            protein_pct=entry["protein_pct"],
            fat_pct=entry["fat_pct"],
            fibre_pct=entry.get("fibre_pct", 0.0),
            moisture_pct=entry.get("moisture_pct", 10.0),
            ash_pct=entry.get("ash_pct", 0.0),
            is_sample=entry.get("sample", True),
        ))
        added += 1

    if added:
        logger.info("Seeded %d sample foods", added)
    return added


def save(food: Food) -> Food:
    """Insert a new food, or update it when food.id is set."""
    values = (
        food.name, food.species, food.kcal_per_100g, food.protein_pct,
        food.fat_pct, food.fibre_pct, food.moisture_pct, food.ash_pct,
        food.pack_size_g, food.life_stage, int(food.is_sample),
    )
    with connect() as conn:
        if food.id is None:
            cursor = conn.execute(
                "INSERT INTO foods (name, species, kcal_per_100g, protein_pct, "
                "fat_pct, fibre_pct, moisture_pct, ash_pct, pack_size_g, "
                "life_stage, is_sample) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            food.id = cursor.lastrowid
        else:
            conn.execute(
                "UPDATE foods SET name=?, species=?, kcal_per_100g=?, "
                "protein_pct=?, fat_pct=?, fibre_pct=?, moisture_pct=?, "
                "ash_pct=?, pack_size_g=?, life_stage=?, is_sample=? "
                "WHERE id=?",
                values + (food.id,),
            )
    return food


def get(food_id: int) -> Optional[Food]:
    with connect() as conn:
        row = conn.execute(
            f"SELECT {COLUMNS} FROM foods WHERE id=?", (food_id,)
        ).fetchone()
    return _row_to_food(row) if row else None


def get_by_name(name: str) -> Optional[Food]:
    with connect() as conn:
        row = conn.execute(
            f"SELECT {COLUMNS} FROM foods WHERE name=? COLLATE NOCASE", (name,)
        ).fetchone()
    return _row_to_food(row) if row else None


def list_foods(species: Optional[str] = None) -> List[Food]:
    """Foods for a species, plus anything marked 'both'.

    Real entries first, then the samples: what the user typed off their own bag
    should sit above data they did not enter.
    """
    query = f"SELECT {COLUMNS} FROM foods"
    params: tuple = ()
    if species:
        query += " WHERE species IN (?, 'both')"
        params = (species,)
    query += " ORDER BY is_sample, name COLLATE NOCASE"

    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_food(row) for row in rows]


def delete(food_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM foods WHERE id=?", (food_id,))


def count() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM foods").fetchone()[0]
