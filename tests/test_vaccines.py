"""Tests for the vaccination schedule.

The rules mirror data/docs/vaccination-schedule.md, so the reminder and the
assistant's answer cannot disagree. If that document changes, these tests
should be the first thing that fails.
"""

from datetime import date, timedelta

import pytest

from src import pets_db, vaccines
from src.models import Pet, VaccineRecord


def give(pet: Pet, key: str, days_ago: int, next_due: date = None) -> None:
    pets_db.add_vaccine(VaccineRecord(
        pet_id=pet.id, vaccine_key=key,
        given_on=date.today() - timedelta(days=days_ago),
        next_due_on=next_due,
    ))


def find(pet: Pet, key: str):
    return next(d for d in vaccines.due_list(pet) if d.key == key)


# --- Schedules -----------------------------------------------------------

def test_cats_and_dogs_have_different_schedules():
    dog_keys = {v["key"] for v in vaccines.schedule_for("dog")}
    cat_keys = {v["key"] for v in vaccines.schedule_for("cat")}
    assert "dhpp" in dog_keys and "dhpp" not in cat_keys
    assert "fvrcp" in cat_keys and "fvrcp" not in dog_keys
    assert "rabies" in dog_keys and "rabies" in cat_keys


def test_core_and_optional_are_distinguished():
    core = {v["key"] for v in vaccines.schedule_for("dog") if v["core"]}
    assert core == {"dhpp", "rabies"}


# --- Nothing given yet ---------------------------------------------------

def test_first_dose_is_due_at_the_documented_age(store):
    pet = pets_db.save_pet(Pet(
        name="Puppy", species="dog",
        birth_date=date.today() - timedelta(weeks=2),
    ))
    due = find(pet, "dhpp")
    assert due.doses_given == 0
    # The document says six to eight weeks; the rule uses six.
    assert due.due_on == pet.birth_date + timedelta(weeks=6)
    assert "6 weeks" in due.reason("en")


def test_without_a_date_of_birth_nothing_can_be_calculated(store):
    pet = pets_db.save_pet(Pet(name="Stray", species="cat"))
    due = find(pet, "fvrcp")
    assert due.due_on is None
    assert due.status == "unknown"


# --- The initial course --------------------------------------------------

def test_the_course_continues_at_the_stated_interval(store):
    pet = pets_db.save_pet(Pet(
        name="Puppy", species="dog",
        birth_date=date.today() - timedelta(weeks=8),
    ))
    give(pet, "dhpp", days_ago=7)

    due = find(pet, "dhpp")
    assert due.doses_given == 1
    assert due.due_on == date.today() - timedelta(days=7) + timedelta(weeks=3)
    assert "course" in due.reason("en")


def test_after_the_course_the_next_step_is_the_yearly_booster(store):
    """A dose given past sixteen weeks of age completes the course."""
    pet = pets_db.save_pet(Pet(
        name="Grown", species="dog",
        birth_date=date.today() - timedelta(weeks=30),
    ))
    give(pet, "dhpp", days_ago=60)      # given at about 21 weeks

    due = find(pet, "dhpp")
    assert "booster" in due.reason("en")
    assert due.due_on.year == (date.today() - timedelta(days=60)).year + 1


def test_routine_boosters_follow_the_long_interval(store):
    pet = pets_db.save_pet(Pet(
        name="Adult", species="dog",
        birth_date=date.today() - timedelta(days=365 * 4),
    ))
    give(pet, "dhpp", days_ago=365 * 2)
    give(pet, "dhpp", days_ago=365)

    due = find(pet, "dhpp")
    assert due.doses_given == 2
    # DHPP boosters run every three years after the first one.
    assert due.due_on.year == (date.today() - timedelta(days=365)).year + 3


# --- The vet's own date wins --------------------------------------------

def test_a_date_written_on_the_card_overrides_the_rule(store):
    pet = pets_db.save_pet(Pet(
        name="Adult", species="cat",
        birth_date=date.today() - timedelta(days=365 * 3),
    ))
    stated = date.today() + timedelta(days=40)
    give(pet, "rabies", days_ago=300, next_due=stated)

    due = find(pet, "rabies")
    assert due.due_on == stated
    assert "vet" in due.reason("en")


# --- Status --------------------------------------------------------------

def test_a_past_date_is_overdue(store):
    pet = pets_db.save_pet(Pet(
        name="Late", species="cat",
        birth_date=date.today() - timedelta(days=365 * 3),
    ))
    give(pet, "rabies", days_ago=10, next_due=date.today() - timedelta(days=12))

    due = find(pet, "rabies")
    assert due.status == "overdue"
    assert due.days_until == -12


def test_a_date_inside_the_window_is_due_soon(store):
    pet = pets_db.save_pet(Pet(
        name="Soon", species="cat",
        birth_date=date.today() - timedelta(days=365 * 3),
    ))
    give(pet, "rabies", days_ago=10, next_due=date.today() + timedelta(days=7))
    assert find(pet, "rabies").status == "due_soon"


def test_a_distant_date_is_merely_scheduled(store):
    pet = pets_db.save_pet(Pet(
        name="Later", species="cat",
        birth_date=date.today() - timedelta(days=365 * 3),
    ))
    give(pet, "rabies", days_ago=10,
         next_due=date.today() + timedelta(days=vaccines.DUE_SOON_DAYS + 30))
    assert find(pet, "rabies").status == "scheduled"


# --- Ordering and the reminder ------------------------------------------

def test_the_most_urgent_comes_first(store):
    pet = pets_db.save_pet(Pet(
        name="Mixed", species="dog",
        birth_date=date.today() - timedelta(days=365 * 3),
    ))
    give(pet, "rabies", days_ago=5, next_due=date.today() + timedelta(days=200))
    give(pet, "dhpp", days_ago=5, next_due=date.today() - timedelta(days=20))

    order = [d.status for d in vaccines.due_list(pet)]
    assert order[0] == "overdue"


def test_the_reminder_picks_the_pressing_item(store):
    pet = pets_db.save_pet(Pet(
        name="Mixed", species="dog",
        birth_date=date.today() - timedelta(days=365 * 3),
    ))
    give(pet, "dhpp", days_ago=5, next_due=date.today() - timedelta(days=20))

    upcoming = vaccines.next_appointment(pet)
    assert upcoming is not None
    assert upcoming.key == "dhpp"
    assert upcoming.status == "overdue"


def test_no_reminder_when_nothing_is_pressing(store):
    pet = pets_db.save_pet(Pet(
        name="Fine", species="cat",
        birth_date=date.today() - timedelta(days=365 * 3),
    ))
    for key in ("fvrcp", "rabies", "felv"):
        give(pet, key, days_ago=5, next_due=date.today() + timedelta(days=300))
    assert vaccines.next_appointment(pet) is None


# --- Language ------------------------------------------------------------

def test_names_and_reasons_exist_in_both_languages(store):
    pet = pets_db.save_pet(Pet(
        name="Both", species="cat",
        birth_date=date.today() - timedelta(days=365 * 2),
    ))
    for due in vaccines.due_list(pet):
        assert due.name("en") and due.name("tr")
        assert due.reason("en") and due.reason("tr")


# --- Month arithmetic ----------------------------------------------------

def test_month_addition_survives_short_months():
    assert vaccines._add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert vaccines._add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert vaccines._add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
