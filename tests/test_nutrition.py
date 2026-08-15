"""Tests for the energy and macronutrient calculations.

The point of most of these is that the result follows the animal — species,
weight, age and neuter status — and never a hardcoded example. A 5 kg kitten
and a 30 kg adult dog must come out with different numbers at every step.

These run without models and without the database.
"""

from datetime import date

import pytest

from src import nutrition
from src.models import Food, Pet


def months_ago(months: int) -> date:
    today = date.today()
    year = today.year + (today.month - months - 1) // 12
    month = (today.month - months - 1) % 12 + 1
    return date(year, month, 1)


@pytest.fixture
def kibble():
    """A typical adult dry food."""
    return Food(
        name="Test Dry", kcal_per_100g=380, protein_pct=24.0, fat_pct=14.0,
        fibre_pct=3.0, moisture_pct=10.0, species="both",
    )


@pytest.fixture
def wet():
    """Wet food: 78% water, so as-fed percentages look tiny."""
    return Food(
        name="Test Wet", kcal_per_100g=85, protein_pct=12.5, fat_pct=4.0,
        fibre_pct=0.5, moisture_pct=78.0, species="cat",
    )


# --- Resting energy ------------------------------------------------------

def test_rer_follows_metabolic_weight():
    # 70 x kg^0.75
    assert nutrition.rer(5) == pytest.approx(234.06, abs=0.5)
    assert nutrition.rer(30) == pytest.approx(897.4, abs=1.0)


def test_rer_is_not_linear_in_weight():
    # Six times the weight is far less than six times the energy. This is the
    # whole reason a per-animal calculation is needed.
    assert nutrition.rer(30) / nutrition.rer(5) == pytest.approx(3.83, abs=0.05)


# --- Life stage and species ---------------------------------------------

def test_cat_and_dog_get_different_factors():
    cat = Pet(name="A", species="cat", birth_date=months_ago(36), neutered=True)
    dog = Pet(name="B", species="dog", birth_date=months_ago(36), neutered=True)
    assert nutrition.mer_factor(cat)[0] == 1.2
    assert nutrition.mer_factor(dog)[0] == 1.6


def test_kitten_is_treated_as_growth():
    kitten = Pet(name="K", species="cat", birth_date=months_ago(3))
    assert nutrition.life_stage(kitten) == "growth"
    assert nutrition.mer_factor(kitten)[0] == 2.5


def test_growth_factor_steps_down_after_four_months():
    early = Pet(name="E", species="dog", birth_date=months_ago(2))
    late = Pet(name="L", species="dog", birth_date=months_ago(8))
    assert nutrition.mer_factor(early)[0] == 3.0
    assert nutrition.mer_factor(late)[0] == 2.0


def test_neuter_status_changes_the_factor():
    base = dict(name="N", species="dog", birth_date=months_ago(36))
    neutered = nutrition.mer_factor(Pet(**base, neutered=True))[0]
    intact = nutrition.mer_factor(Pet(**base, neutered=False))[0]
    unknown = nutrition.mer_factor(Pet(**base))[0]

    assert neutered < unknown < intact
    assert nutrition.mer_factor(Pet(**base))[1] == "adult_unknown"


def test_unknown_birth_date_is_treated_as_adult():
    pet = Pet(name="U", species="dog")
    assert nutrition.life_stage(pet) == "adult"


# --- Minimums ------------------------------------------------------------

def test_cats_need_more_protein_than_dogs():
    cat = Pet(name="C", species="cat", birth_date=months_ago(36))
    dog = Pet(name="D", species="dog", birth_date=months_ago(36))
    assert nutrition.minimums(cat)["protein"] > nutrition.minimums(dog)["protein"]


def test_growth_minimums_are_higher_than_adult():
    puppy = Pet(name="P", species="dog", birth_date=months_ago(5))
    adult = Pet(name="A", species="dog", birth_date=months_ago(36))
    assert nutrition.minimums(puppy)["protein"] == 22.5
    assert nutrition.minimums(adult)["protein"] == 18.0


# --- One serving ---------------------------------------------------------

def test_meal_scales_with_grams(kibble):
    small = nutrition.meal(kibble, 100)
    large = nutrition.meal(kibble, 300)
    assert large.kcal == pytest.approx(small.kcal * 3, abs=0.5)
    assert large.protein_g == pytest.approx(small.protein_g * 3, abs=0.5)


def test_meal_matches_the_label(kibble):
    served = nutrition.meal(kibble, 200)
    assert served.kcal == pytest.approx(760, abs=1)      # 380 kcal/100 g
    assert served.protein_g == pytest.approx(48, abs=0.5)  # 24%
    assert served.dry_matter_g == pytest.approx(180, abs=0.5)  # 90%


def test_dry_matter_conversion_is_fair_to_wet_food(wet, kibble):
    """As-fed percentages make wet food look deficient; dry matter does not."""
    wet_meal = nutrition.meal(wet, 100)
    dry_meal = nutrition.meal(kibble, 100)

    # As fed, the wet food looks far weaker.
    assert wet.protein_pct < dry_meal.protein_g

    # On a dry matter basis it is actually the stronger of the two.
    assert wet_meal.protein_dm_pct > dry_meal.protein_dm_pct
    assert wet_meal.protein_dm_pct == pytest.approx(56.8, abs=0.5)


def test_grams_for_energy_is_the_inverse_of_meal(kibble):
    grams = nutrition.grams_for_energy(kibble, 760)
    assert grams == pytest.approx(200, abs=1)


def test_denser_food_needs_fewer_grams(kibble, wet):
    assert (nutrition.grams_for_energy(kibble, 500)
            < nutrition.grams_for_energy(wet, 500))


# --- Requirements follow the animal --------------------------------------

def test_required_grams_scale_with_the_animal(kibble):
    """The headline check: a small cat and a large dog get different portions."""
    cat = Pet(name="Cat", species="cat", birth_date=months_ago(36), neutered=True)
    dog = Pet(name="Dog", species="dog", birth_date=months_ago(36), neutered=True)

    cat_energy = {"mer_kcal": round(nutrition.rer(5) * 1.2)}
    dog_energy = {"mer_kcal": round(nutrition.rer(30) * 1.6)}

    cat_need = nutrition.required_grams(cat, kibble, cat_energy)
    dog_need = nutrition.required_grams(dog, kibble, dog_energy)

    assert cat_need["food_grams"] == pytest.approx(74, abs=3)
    assert dog_need["food_grams"] == pytest.approx(378, abs=6)
    assert dog_need["food_grams"] > cat_need["food_grams"] * 4


def test_protein_requirement_uses_the_species_minimum(kibble):
    cat = Pet(name="Cat", species="cat", birth_date=months_ago(36), neutered=True)
    dog = Pet(name="Dog", species="dog", birth_date=months_ago(36), neutered=True)
    energy = {"mer_kcal": 500}

    cat_need = nutrition.required_grams(cat, kibble, energy)
    dog_need = nutrition.required_grams(dog, kibble, energy)

    # Same energy, same food — the cat still needs more protein, because the
    # minimum for cats is higher.
    assert cat_need["protein_g"] > dog_need["protein_g"]


def test_a_food_can_fail_the_minimum_for_one_species_but_not_another():
    low_protein = Food(
        name="Low", kcal_per_100g=350, protein_pct=19.0, fat_pct=10.0,
        moisture_pct=10.0,
    )
    served = nutrition.meal(low_protein, 100)
    dm_pct = served.protein_dm_pct

    dog = Pet(name="D", species="dog", birth_date=months_ago(36))
    cat = Pet(name="C", species="cat", birth_date=months_ago(36))

    assert dm_pct >= nutrition.minimums(dog)["protein"]   # fine for a dog
    assert dm_pct < nutrition.minimums(cat)["protein"]    # short for a cat
