"""Shared fixtures.

The rule engine reads from the database at almost every step, so testing it
against a real SQLite file in a temp directory is both simpler and more honest
than mocking every accessor. The file is thrown away after each test.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src import config, db, foods_db, pets_db
from src.models import FeedingRecord, Food, Pet, StoolRecord, WeightRecord


@pytest.fixture
def store(tmp_path, monkeypatch):
    """An empty database, isolated per test."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    pets_db.init_db()
    foods_db.init_db()
    return tmp_path / "test.db"


@pytest.fixture
def food(store) -> Food:
    """A middle-of-the-road adult dry food, comfortably above the minimums."""
    return foods_db.save(Food(
        name="Test Dry", species="both", kcal_per_100g=380,
        protein_pct=26, fat_pct=14, fibre_pct=3, moisture_pct=10, ash_pct=7,
    ))


@pytest.fixture
def thin_food(store) -> Food:
    """Below the protein minimum for a cat, above it for a dog."""
    return foods_db.save(Food(
        name="Low Protein", species="both", kcal_per_100g=350,
        protein_pct=19, fat_pct=10, fibre_pct=3, moisture_pct=10, ash_pct=7,
    ))


@pytest.fixture
def dog(store) -> Pet:
    """Adult neutered dog, 30 kg, target 28 kg."""
    return pets_db.save_pet(Pet(
        name="Test Dog", species="dog", breed="Test Breed",
        birth_date=date.today() - timedelta(days=365 * 3),
        sex="female", target_weight_kg=28.0, neutered=True,
    ))


@pytest.fixture
def cat(store) -> Pet:
    """Adult neutered cat, target 4.5 kg."""
    return pets_db.save_pet(Pet(
        name="Test Cat", species="cat",
        birth_date=date.today() - timedelta(days=365 * 4),
        sex="male", target_weight_kg=4.5, neutered=True,
    ))


@pytest.fixture
def kitten(store) -> Pet:
    """Three months old — growth life stage, higher minimums."""
    return pets_db.save_pet(Pet(
        name="Test Kitten", species="cat",
        birth_date=date.today() - timedelta(days=90),
        target_weight_kg=4.0,
    ))


# --- Builders ------------------------------------------------------------

def add_weights(pet: Pet, *pairs) -> None:
    """add_weights(pet, (weeks_ago, kg), ...)"""
    today = date.today()
    for weeks_ago, kg in pairs:
        pets_db.add_weight(WeightRecord(
            pet_id=pet.id,
            recorded_on=today - timedelta(weeks=weeks_ago),
            weight_kg=kg,
        ))


def add_feeding(pet: Pet, food: Food, grams: float, weeks_ago: int = 0,
                meals: int = 2) -> FeedingRecord:
    return pets_db.add_feeding(FeedingRecord(
        pet_id=pet.id,
        recorded_on=date.today() - timedelta(weeks=weeks_ago),
        grams=grams, food_id=food.id, food_brand=food.name,
        meals_per_day=meals,
    ))


def add_stools(pet: Pet, qualities) -> None:
    today = date.today()
    for index, quality in enumerate(qualities):
        pets_db.add_stool(StoolRecord(
            pet_id=pet.id,
            recorded_on=today - timedelta(days=index),
            quality=quality, frequency_per_day=1.0,
        ))


def titles(findings, lang: str = "en"):
    return [f.title(lang) for f in findings]


def has(findings, fragment: str, level: str = None) -> bool:
    """Whether any finding's title contains a fragment, optionally by level."""
    fragment = fragment.lower()
    return any(
        fragment in f.title("en").lower() and (level is None or f.level == level)
        for f in findings
    )
