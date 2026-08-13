"""SQLite storage for pets and their health records.

Kept separate from db.py, which owns the document chunks. The two never join:
the document collection is general knowledge that changes when documents are
re-ingested, while these tables hold one household's data and must survive
`ingest --rebuild`.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List, Optional

from .db import connect
from .models import FeedingRecord, Pet, StoolRecord, WeightRecord

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS pets (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    species           TEXT NOT NULL DEFAULT 'dog',
    breed             TEXT,
    birth_date        TEXT,
    sex               TEXT,
    target_weight_kg  REAL,
    owner_name        TEXT,
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS weight_records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id       INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    recorded_on  TEXT NOT NULL,
    weight_kg    REAL NOT NULL,
    UNIQUE(pet_id, recorded_on)
);

CREATE TABLE IF NOT EXISTS feeding_records (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id         INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    recorded_on    TEXT NOT NULL,
    food_brand     TEXT NOT NULL,
    portion_cups   REAL NOT NULL,
    meals_per_day  INTEGER,
    note           TEXT
);

CREATE TABLE IF NOT EXISTS stool_records (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id             INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    recorded_on        TEXT NOT NULL,
    quality            TEXT NOT NULL,
    frequency_per_day  REAL
);

CREATE INDEX IF NOT EXISTS idx_weight_pet   ON weight_records(pet_id, recorded_on);
CREATE INDEX IF NOT EXISTS idx_feeding_pet  ON feeding_records(pet_id, recorded_on);
CREATE INDEX IF NOT EXISTS idx_stool_pet    ON stool_records(pet_id, recorded_on);
"""


def _to_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def _from_date(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def init_db() -> None:
    """Create the pet tables if they are not already there."""
    with connect() as conn:
        conn.executescript(SCHEMA)
    logger.info("Pet tables ready")


# --- Pets ----------------------------------------------------------------

def _row_to_pet(row) -> Pet:
    return Pet(
        id=row[0],
        name=row[1],
        species=row[2],
        breed=row[3],
        birth_date=_to_date(row[4]),
        sex=row[5],
        target_weight_kg=row[6],
        owner_name=row[7],
    )


PET_COLUMNS = "id, name, species, breed, birth_date, sex, target_weight_kg, owner_name"


def save_pet(pet: Pet) -> Pet:
    """Insert a new pet, or update it when pet.id is set."""
    values = (
        pet.name, pet.species, pet.breed, _from_date(pet.birth_date),
        pet.sex, pet.target_weight_kg, pet.owner_name,
    )
    with connect() as conn:
        if pet.id is None:
            cursor = conn.execute(
                "INSERT INTO pets (name, species, breed, birth_date, sex, "
                "target_weight_kg, owner_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            pet.id = cursor.lastrowid
        else:
            conn.execute(
                "UPDATE pets SET name=?, species=?, breed=?, birth_date=?, sex=?, "
                "target_weight_kg=?, owner_name=? WHERE id=?",
                values + (pet.id,),
            )
    return pet


def get_pet(pet_id: int) -> Optional[Pet]:
    with connect() as conn:
        row = conn.execute(
            f"SELECT {PET_COLUMNS} FROM pets WHERE id=?", (pet_id,)
        ).fetchone()
    return _row_to_pet(row) if row else None


def list_pets() -> List[Pet]:
    with connect() as conn:
        rows = conn.execute(f"SELECT {PET_COLUMNS} FROM pets ORDER BY id").fetchall()
    return [_row_to_pet(row) for row in rows]


def first_pet() -> Optional[Pet]:
    """The app is single-household; this is the default selection."""
    pets = list_pets()
    return pets[0] if pets else None


def delete_pet(pet_id: int) -> None:
    with connect() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for table in ("weight_records", "feeding_records", "stool_records"):
            conn.execute(f"DELETE FROM {table} WHERE pet_id=?", (pet_id,))
        conn.execute("DELETE FROM pets WHERE id=?", (pet_id,))


# --- Weight --------------------------------------------------------------

def add_weight(record: WeightRecord) -> WeightRecord:
    """Store a weighing. Re-recording the same day overwrites it."""
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO weight_records (pet_id, recorded_on, weight_kg) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(pet_id, recorded_on) DO UPDATE SET weight_kg=excluded.weight_kg",
            (record.pet_id, _from_date(record.recorded_on), record.weight_kg),
        )
        record.id = cursor.lastrowid
    return record


def weights(pet_id: int, limit: Optional[int] = None) -> List[WeightRecord]:
    """Weighings oldest first, so charts and trends read left to right."""
    query = (
        "SELECT id, pet_id, recorded_on, weight_kg FROM weight_records "
        "WHERE pet_id=? ORDER BY recorded_on"
    )
    with connect() as conn:
        rows = conn.execute(query, (pet_id,)).fetchall()
    records = [
        WeightRecord(id=r[0], pet_id=r[1], recorded_on=_to_date(r[2]), weight_kg=r[3])
        for r in rows
    ]
    return records[-limit:] if limit else records


def latest_weight(pet_id: int) -> Optional[WeightRecord]:
    records = weights(pet_id)
    return records[-1] if records else None


# --- Feeding -------------------------------------------------------------

def add_feeding(record: FeedingRecord) -> FeedingRecord:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO feeding_records (pet_id, recorded_on, food_brand, "
            "portion_cups, meals_per_day, note) VALUES (?, ?, ?, ?, ?, ?)",
            (record.pet_id, _from_date(record.recorded_on), record.food_brand,
             record.portion_cups, record.meals_per_day, record.note),
        )
        record.id = cursor.lastrowid
    return record


def feedings(pet_id: int) -> List[FeedingRecord]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, pet_id, recorded_on, food_brand, portion_cups, "
            "meals_per_day, note FROM feeding_records WHERE pet_id=? "
            "ORDER BY recorded_on",
            (pet_id,),
        ).fetchall()
    return [
        FeedingRecord(
            id=r[0], pet_id=r[1], recorded_on=_to_date(r[2]), food_brand=r[3],
            portion_cups=r[4], meals_per_day=r[5], note=r[6],
        )
        for r in rows
    ]


def current_feeding(pet_id: int) -> Optional[FeedingRecord]:
    records = feedings(pet_id)
    return records[-1] if records else None


def last_food_change(pet_id: int) -> Optional[FeedingRecord]:
    """The record where the brand last differed from the one before it.

    This is what lets an insight say "the weight gain lines up with the food
    change on 12 July" instead of just "the weight is going up".
    """
    records = feedings(pet_id)
    for previous, current in zip(reversed(records[:-1]), reversed(records[1:])):
        if current.food_brand != previous.food_brand:
            return current
    return None


# --- Stool ---------------------------------------------------------------

def add_stool(record: StoolRecord) -> StoolRecord:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO stool_records (pet_id, recorded_on, quality, "
            "frequency_per_day) VALUES (?, ?, ?, ?)",
            (record.pet_id, _from_date(record.recorded_on), record.quality,
             record.frequency_per_day),
        )
        record.id = cursor.lastrowid
    return record


def stools(pet_id: int, since: Optional[date] = None) -> List[StoolRecord]:
    query = (
        "SELECT id, pet_id, recorded_on, quality, frequency_per_day "
        "FROM stool_records WHERE pet_id=?"
    )
    params: tuple = (pet_id,)
    if since:
        query += " AND recorded_on >= ?"
        params += (since.isoformat(),)
    query += " ORDER BY recorded_on"

    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        StoolRecord(
            id=r[0], pet_id=r[1], recorded_on=_to_date(r[2]),
            quality=r[3], frequency_per_day=r[4],
        )
        for r in rows
    ]
