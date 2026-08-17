"""Tests for the rule engine.

This is the module that tells an owner to reduce a portion or take an animal to
a vet, and it is the one where four separate gaps were found by accident during
development: weight loss was not handled at all, implausible data was not
checked, the rules could contradict each other, and a rename broke every caller.

Each of those is a test here.
"""

from datetime import date, timedelta

import pytest

from src import insights, nutrition, pets_db
from src.models import FeedingRecord, WeightRecord

from conftest import add_feeding, add_stools, add_weights, has


# --- Weight gain ---------------------------------------------------------

def test_steady_weight_produces_no_gain_warning(dog):
    add_weights(dog, (4, 28.0), (3, 28.0), (2, 28.0), (1, 28.0), (0, 28.0))
    found = insights.generate(dog)
    assert not has(found, "weight is rising")
    assert not has(found, "weight gain")


def test_weight_gain_is_flagged(dog):
    add_weights(dog, (4, 29.0), (3, 29.2), (2, 29.6), (1, 30.0), (0, 30.4))
    assert has(insights.generate(dog), "weight is rising", level="warning")


def test_weight_gain_is_linked_to_a_change_of_food(dog, food, store):
    from src import foods_db
    from src.models import Food

    other = foods_db.save(Food(
        name="Previous Food", kcal_per_100g=330, protein_pct=22, fat_pct=10,
        moisture_pct=10,
    ))
    add_weights(dog, (4, 29.0), (3, 29.2), (2, 29.6), (1, 30.0), (0, 30.4))
    add_feeding(dog, other, 400, weeks_ago=8)
    add_feeding(dog, food, 400, weeks_ago=4)

    found = insights.generate(dog)
    assert has(found, "follows a change of food", level="warning")
    # The date of the change belongs in the message, not just the fact of it.
    detail = next(f for f in found if "change of food" in f.title("en")).detail("en")
    assert "Previous Food" not in detail
    assert food.name in detail


def test_gain_without_a_food_change_says_so(dog, food):
    add_weights(dog, (4, 29.0), (3, 29.2), (2, 29.6), (1, 30.0), (0, 30.4))
    add_feeding(dog, food, 400, weeks_ago=8)

    found = insights.generate(dog)
    assert has(found, "weight is rising")
    detail = next(f for f in found if "rising" in f.title("en")).detail("en")
    assert "no change of food" in detail.lower()


# --- Weight loss ---------------------------------------------------------
# Missing entirely at first: a 25 kg drop produced no finding at all.

def test_weight_loss_is_flagged(dog):
    add_weights(dog, (4, 30.0), (3, 29.8), (2, 29.4), (1, 29.2), (0, 29.0))
    assert has(insights.generate(dog), "weight is falling")


def test_rapid_loss_is_a_warning_not_a_suggestion(dog):
    # Over 5% of body weight in three weeks.
    add_weights(dog, (4, 30.0), (3, 30.0), (2, 28.0), (1, 26.5), (0, 25.0))
    found = insights.generate(dog)
    assert has(found, "rapid weight loss", level="warning")

    detail = next(f for f in found if "rapid" in f.title("en").lower()).detail("en")
    assert "vet" in detail.lower()


def test_loss_is_reported_at_a_lower_bar_than_gain(dog):
    """Unexplained loss matters more than the same amount of gain."""
    losing = insights.LOSS_THRESHOLD_KG
    gaining = insights.GAIN_THRESHOLD_KG
    assert losing <= gaining


# --- Data quality --------------------------------------------------------
# Also missing at first: 30.2 kg followed by 5.0 kg was analysed as real.

def test_an_impossible_jump_is_flagged(dog):
    add_weights(dog, (2, 30.0), (1, 30.2), (0, 5.0))
    assert has(insights.generate(dog), "typing error", level="warning")


def test_a_normal_change_is_not_flagged_as_a_typo(dog):
    add_weights(dog, (2, 28.0), (1, 28.4), (0, 28.9))
    assert not has(insights.generate(dog), "typing error")


def test_a_future_date_is_flagged(dog):
    pets_db.add_weight(WeightRecord(
        pet_id=dog.id, recorded_on=date.today() + timedelta(days=8),
        weight_kg=28.0,
    ))
    add_weights(dog, (1, 28.0))
    assert has(insights.generate(dog), "future", level="warning")


def test_data_quality_is_reported_before_conclusions(dog):
    """A doubtful number should be questioned before it drives advice."""
    add_weights(dog, (2, 30.0), (1, 30.2), (0, 5.0))
    found = insights.generate(dog)
    titles = [f.title("en").lower() for f in found]
    typo = next(i for i, t in enumerate(titles) if "typing error" in t)
    others = [i for i, t in enumerate(titles) if "weight" in t and i != typo]
    assert all(typo < i for i in others)


# --- Target weight -------------------------------------------------------

def test_above_target_is_reported(dog):
    add_weights(dog, (1, 30.5), (0, 30.5))
    assert has(insights.generate(dog), "above target")


def test_below_target_is_reported(dog):
    add_weights(dog, (1, 24.0), (0, 24.0))
    found = insights.generate(dog)
    assert has(found, "below target", level="warning")


def test_on_target_is_positive(dog):
    add_weights(dog, (1, 28.0), (0, 28.0))
    found = insights.generate(dog)
    assert has(found, "on target", level="positive")


def test_no_target_weight_is_reported_as_missing(store):
    from src.models import Pet
    pet = pets_db.save_pet(Pet(name="No Target", species="dog"))
    add_weights(pet, (1, 20.0), (0, 20.0))
    assert has(insights.generate(pet), "no target weight")


# --- Portion -------------------------------------------------------------

def test_overfeeding_is_reported_against_the_calculated_need(dog, food):
    add_weights(dog, (1, 28.0), (0, 28.0))
    need = nutrition.daily_energy(dog)["mer_kcal"]
    grams = nutrition.grams_for_energy(food, need * 1.4)
    add_feeding(dog, food, grams)

    found = insights.generate(dog)
    assert has(found, "above the calculated need")
    detail = next(f for f in found if "above the calculated" in f.title("en")).detail("en")
    assert "kcal" in detail


def test_a_portion_within_tolerance_is_not_flagged(dog, food):
    add_weights(dog, (1, 28.0), (0, 28.0))
    need = nutrition.daily_energy(dog)["mer_kcal"]
    add_feeding(dog, food, nutrition.grams_for_energy(food, need))

    found = insights.generate(dog)
    assert not has(found, "calculated need")


def test_underfeeding_a_gaining_overweight_animal_does_not_say_feed_more(dog, food):
    """The scale beats the formula.

    The rules used to say "portion is below the calculated need" for an animal
    that was gaining and already over target — advice that would have made
    things worse.
    """
    add_weights(dog, (4, 29.0), (3, 29.4), (2, 29.8), (1, 30.2), (0, 30.6))
    need = nutrition.daily_energy(dog)["mer_kcal"]
    add_feeding(dog, food, nutrition.grams_for_energy(food, need * 0.6))

    found = insights.generate(dog)
    assert has(found, "does not explain the weight gain", level="warning")
    assert not has(found, "below the calculated need")

    detail = next(f for f in found
                  if "does not explain" in f.title("en")).detail("en").lower()
    assert "do not increase" in detail


# --- Macronutrients ------------------------------------------------------

def test_protein_below_the_minimum_is_a_warning(cat, thin_food):
    add_weights(cat, (1, 4.5), (0, 4.5))
    add_feeding(cat, thin_food, 60)
    assert has(insights.generate(cat), "protein below", level="warning")


def test_the_same_food_passes_for_a_dog(dog, thin_food):
    """19% protein clears the dog minimum and fails the cat one."""
    add_weights(dog, (1, 28.0), (0, 28.0))
    add_feeding(dog, thin_food, 400)
    assert not has(insights.generate(dog), "protein below")


def test_growth_minimums_are_applied_to_a_kitten(kitten, food):
    add_weights(kitten, (1, 2.0), (0, 2.1))
    add_feeding(kitten, food, 60)
    # 26% protein as fed is 28.9% dry matter, below the 30% growth minimum.
    assert has(insights.generate(kitten), "protein below")


# --- Stool ---------------------------------------------------------------

def test_healthy_stool_is_positive(dog):
    add_weights(dog, (1, 28.0), (0, 28.0))
    add_stools(dog, ["normal"] * 20)
    assert has(insights.generate(dog), "digestion", level="positive")


def test_inconsistent_stool_is_a_warning(dog):
    add_weights(dog, (1, 28.0), (0, 28.0))
    add_stools(dog, ["normal"] * 8 + ["loose"] * 12)
    assert has(insights.generate(dog), "stool quality", level="warning")


# --- Missing data --------------------------------------------------------

def test_a_single_weighing_says_a_trend_cannot_be_shown(dog):
    add_weights(dog, (0, 28.0))
    assert has(insights.generate(dog), "not enough weight history")


def test_an_empty_record_does_not_crash(dog):
    assert isinstance(insights.generate(dog), list)


# --- Both languages ------------------------------------------------------

def test_every_finding_carries_both_languages(dog, food):
    add_weights(dog, (4, 29.0), (3, 29.4), (2, 29.8), (1, 30.2), (0, 30.6))
    add_feeding(dog, food, 500)
    add_stools(dog, ["normal"] * 10)

    found = insights.generate(dog)
    assert found
    for item in found:
        assert item.title("en") and item.title("tr")
        assert item.detail("en") and item.detail("tr")
        assert item.title("en") != item.title("tr")


def test_levels_are_from_the_known_set(dog, food):
    add_weights(dog, (2, 29.0), (1, 30.0), (0, 30.6))
    add_feeding(dog, food, 500)
    for item in insights.generate(dog):
        assert item.level in {"warning", "positive", "suggestion"}


# --- Dates ---------------------------------------------------------------

def test_dates_are_written_in_the_right_language():
    day = date(2026, 7, 13)
    assert insights.format_date(day, "en") == "13 July 2026"
    assert insights.format_date(day, "tr") == "13 Temmuz 2026"
