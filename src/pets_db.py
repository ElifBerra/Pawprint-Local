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
from .models import (FeedingRecord, Pet, StoolRecord, VaccineRecord,
                     WeightRecord)

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
    grams          REAL NOT NULL,
    food_id        INTEGER REFERENCES foods(id),
    food_brand     TEXT,
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

CREATE TABLE IF NOT EXISTS vaccine_records (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id        INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    given_on      TEXT NOT NULL,
    vaccine_key   TEXT NOT NULL,
    vet_name      TEXT,
    batch         TEXT,
    note          TEXT,
    next_due_on   TEXT
);

CREATE INDEX IF NOT EXISTS idx_vaccine_pet  ON vaccine_records(pet_id, given_on);
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
    """Create the pet tables if they are not already there, then migrate."""
    with connect() as conn:
        conn.executescript(SCHEMA)
    _migrate()
    logger.info("Pet tables ready")


def _columns(conn, table: str) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate() -> None:
    """Bring an older database up to the current schema.

    Two changes since the first version: feeding is recorded in grams rather
    than cups, and the profile carries neuter status because it moves the
    energy requirement by about 12%.

    A cup is not a unit — the same cup of two foods differs by roughly 20% in
    weight — so old cup values are converted with a stated assumption rather
    than pretended to be exact.
    """
    CUP_GRAMS = 100.0

    with connect() as conn:
        pet_columns = _columns(conn, "pets")
        if "neutered" not in pet_columns:
            conn.execute("ALTER TABLE pets ADD COLUMN neutered INTEGER")
            logger.info("Added pets.neutered")

        feeding = _columns(conn, "feeding_records")
        if not feeding or "grams" in feeding:
            return

        logger.info("Migrating feeding_records from cups to grams")
        # sqlite3 commits before running executescript, so a failure partway
        # through leaves the scratch table behind. Clear it first rather than
        # requiring the user to repair the database by hand.
        conn.executescript("""
            DROP TABLE IF EXISTS feeding_records_new;
            CREATE TABLE feeding_records_new (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                pet_id         INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
                recorded_on    TEXT NOT NULL,
                grams          REAL NOT NULL,
                food_id        INTEGER REFERENCES foods(id),
                food_brand     TEXT,
                meals_per_day  INTEGER,
                note           TEXT
            );
        """)
        conn.execute(
            "INSERT INTO feeding_records_new "
            "(id, pet_id, recorded_on, grams, food_id, food_brand, "
            " meals_per_day, note) "
            "SELECT id, pet_id, recorded_on, portion_cups * ?, NULL, food_brand, "
            "meals_per_day, "
            "COALESCE(note || ' | ', '') || 'converted from cups at ' "
            "  || ? || ' g/cup' "
            "FROM feeding_records",
            (CUP_GRAMS, CUP_GRAMS),
        )
        conn.executescript("""
            DROP TABLE feeding_records;
            ALTER TABLE feeding_records_new RENAME TO feeding_records;
            CREATE INDEX IF NOT EXISTS idx_feeding_pet
                ON feeding_records(pet_id, recorded_on);
        """)


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
        neutered=None if row[8] is None else bool(row[8]),
    )


PET_COLUMNS = ("id, name, species, breed, birth_date, sex, target_weight_kg, "
               "owner_name, neutered")


def save_pet(pet: Pet) -> Pet:
    """Insert a new pet, or update it when pet.id is set."""
    values = (
        pet.name, pet.species, pet.breed, _from_date(pet.birth_date),
        pet.sex, pet.target_weight_kg, pet.owner_name,
        None if pet.neutered is None else int(pet.neutered),
    )
    with connect() as conn:
        if pet.id is None:
            cursor = conn.execute(
                "INSERT INTO pets (name, species, breed, birth_date, sex, "
                "target_weight_kg, owner_name, neutered) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            pet.id = cursor.lastrowid
        else:
            conn.execute(
                "UPDATE pets SET name=?, species=?, breed=?, birth_date=?, sex=?, "
                "target_weight_kg=?, owner_name=?, neutered=? WHERE id=?",
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
        for table in ("weight_records", "feeding_records", "stool_records",
                      "vaccine_records"):
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
            "INSERT INTO feeding_records (pet_id, recorded_on, grams, food_id, "
            "food_brand, meals_per_day, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (record.pet_id, _from_date(record.recorded_on), record.grams,
             record.food_id, record.food_brand, record.meals_per_day,
             record.note),
        )
        record.id = cursor.lastrowid
    return record


FEEDING_COLUMNS = ("id, pet_id, recorded_on, grams, food_id, food_brand, "
                   "meals_per_day, note")


def _row_to_feeding(r) -> FeedingRecord:
    return FeedingRecord(
        id=r[0], pet_id=r[1], recorded_on=_to_date(r[2]), grams=r[3],
        food_id=r[4], food_brand=r[5], meals_per_day=r[6], note=r[7],
    )


def feedings(pet_id: int) -> List[FeedingRecord]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {FEEDING_COLUMNS} FROM feeding_records WHERE pet_id=? "
            "ORDER BY recorded_on",
            (pet_id,),
        ).fetchall()
    return [_row_to_feeding(r) for r in rows]


def current_feeding(pet_id: int) -> Optional[FeedingRecord]:
    records = feedings(pet_id)
    return records[-1] if records else None


def _food_key(record: FeedingRecord):
    """What identifies the food, whichever way the record was created."""
    return record.food_id if record.food_id is not None else record.food_brand


def last_food_change(pet_id: int) -> Optional[FeedingRecord]:
    """The record where the food last differed from the one before it.

    This is what lets an insight say "the weight gain lines up with the food
    change on 12 July" instead of just "the weight is going up".
    """
    records = feedings(pet_id)
    for previous, current in zip(reversed(records[:-1]), reversed(records[1:])):
        if _food_key(current) != _food_key(previous):
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


def add_vaccine(record: VaccineRecord) -> VaccineRecord:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO vaccine_records (pet_id, given_on, vaccine_key, "
            "vet_name, batch, note, next_due_on) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (record.pet_id, _from_date(record.given_on), record.vaccine_key,
             record.vet_name, record.batch, record.note,
             _from_date(record.next_due_on)),
        )
        record.id = cursor.lastrowid
    return record


def vaccines(pet_id: int) -> List[VaccineRecord]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, pet_id, given_on, vaccine_key, vet_name, batch, note, "
            "next_due_on FROM vaccine_records WHERE pet_id=? ORDER BY given_on",
            (pet_id,),
        ).fetchall()
    return [
        VaccineRecord(
            id=r[0], pet_id=r[1], given_on=_to_date(r[2]), vaccine_key=r[3],
            vet_name=r[4], batch=r[5], note=r[6], next_due_on=_to_date(r[7]),
        )
        for r in rows
    ]


def delete_vaccine(record_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM vaccine_records WHERE id=?", (record_id,))


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
