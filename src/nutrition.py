"""Energy and macronutrient analysis.

Arithmetic only. Like insights.py, nothing here goes near the language model:
these numbers drive statements such as "6 g short of the protein minimum", and
a figure like that has to be identical every time the page is opened.

Two standard pieces of veterinary nutrition are used:

1. Resting Energy Requirement, RER = 70 x bodyweight_kg ^ 0.75, multiplied by a
   life-stage factor to give the Maintenance Energy Requirement (MER).

2. AAFCO nutrient profile minimums, expressed on a dry matter basis. Labels
   print "as fed" percentages, so intake is converted to dry matter before
   comparison — otherwise a wet food looks deficient purely because it is 78%
   water.

These are MINIMUMS for a complete diet, not targets, and not veterinary advice.
The interface says so wherever a figure is shown.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from . import foods_db, pets_db
from .models import Food, MealNutrition, Pet

# --- Energy --------------------------------------------------------------

# Multipliers applied to RER. Widely published maintenance factors; the exact
# figure for an individual animal is a veterinary judgement.
MER_FACTORS: Dict[str, Dict[str, float]] = {
    "dog": {
        "growth_early": 3.0,     # under 4 months
        "growth_late": 2.0,      # 4-12 months
        "adult_neutered": 1.6,
        "adult_intact": 1.8,
        "adult_unknown": 1.7,    # neuter status not stated
        "weight_loss": 1.0,
    },
    "cat": {
        "growth_early": 2.5,
        "growth_late": 2.0,
        "adult_neutered": 1.2,
        "adult_intact": 1.4,
        "adult_unknown": 1.3,
        "weight_loss": 0.8,
    },
}

# AAFCO nutrient profile minimums, percent of dry matter.
AAFCO_MINIMUMS: Dict[str, Dict[str, Dict[str, float]]] = {
    "dog": {
        "growth": {"protein": 22.5, "fat": 8.5},
        "adult": {"protein": 18.0, "fat": 5.5},
    },
    "cat": {
        "growth": {"protein": 30.0, "fat": 9.0},
        "adult": {"protein": 26.0, "fat": 9.0},
    },
}

GROWTH_UNTIL_MONTHS = 12
EARLY_GROWTH_MONTHS = 4

# Energy intake outside this band of the requirement is worth a comment.
ENERGY_TOLERANCE = 0.10


def rer(weight_kg: float) -> float:
    """Resting Energy Requirement in kcal per day."""
    return 70.0 * (weight_kg ** 0.75)


def life_stage(pet: Pet) -> str:
    """"growth" or "adult", from date of birth. Unknown age is treated as adult."""
    months = pet.age_months
    if months is None:
        return "adult"
    return "growth" if months < GROWTH_UNTIL_MONTHS else "adult"


def mer_factor(pet: Pet, weight_loss: bool = False) -> tuple[float, str]:
    """The multiplier and the label explaining which one was used."""
    table = MER_FACTORS.get(pet.species, MER_FACTORS["dog"])
    months = pet.age_months

    if weight_loss and life_stage(pet) == "adult":
        return table["weight_loss"], "weight_loss"
    if months is not None and months < EARLY_GROWTH_MONTHS:
        return table["growth_early"], "growth_early"
    if months is not None and months < GROWTH_UNTIL_MONTHS:
        return table["growth_late"], "growth_late"
    if pet.neutered is True:
        return table["adult_neutered"], "adult_neutered"
    if pet.neutered is False:
        return table["adult_intact"], "adult_intact"
    return table["adult_unknown"], "adult_unknown"


def daily_energy(pet: Pet, weight_loss: bool = False) -> Optional[dict]:
    """Daily energy requirement, or None without a weight on file."""
    latest = pets_db.latest_weight(pet.id)
    if latest is None:
        return None

    # Energy is calculated from target weight when the animal is over it:
    # feeding an overweight animal for the weight it currently is keeps it there.
    basis_kg = latest.weight_kg
    basis = "current"
    if pet.target_weight_kg and latest.weight_kg > pet.target_weight_kg * 1.05:
        basis_kg = pet.target_weight_kg
        basis = "target"

    resting = rer(basis_kg)
    factor, factor_name = mer_factor(pet, weight_loss)

    return {
        "weight_kg": round(basis_kg, 2),
        "basis": basis,
        "rer_kcal": round(resting),
        "factor": factor,
        "factor_name": factor_name,
        "mer_kcal": round(resting * factor),
        "life_stage": life_stage(pet),
        "neuter_known": pet.neutered is not None,
    }


# --- One serving ---------------------------------------------------------

def meal(food: Food, grams: float) -> MealNutrition:
    """What a given weight of a given food delivers."""
    return MealNutrition(
        grams=grams,
        kcal=round(grams * food.kcal_per_gram, 1),
        protein_g=round(grams * food.protein_pct / 100, 1),
        fat_g=round(grams * food.fat_pct / 100, 1),
        fibre_g=round(grams * food.fibre_pct / 100, 1),
        dry_matter_g=round(grams * food.dry_matter_pct / 100, 1),
    )


def grams_for_energy(food: Food, kcal: float) -> float:
    """How much of this food covers a given number of calories."""
    return round(kcal / food.kcal_per_gram) if food.kcal_per_gram else 0.0


# --- Requirements --------------------------------------------------------

def minimums(pet: Pet) -> Dict[str, float]:
    """AAFCO dry-matter minimums for this animal's species and life stage."""
    species = AAFCO_MINIMUMS.get(pet.species, AAFCO_MINIMUMS["dog"])
    return species[life_stage(pet)]


def required_grams(pet: Pet, food: Food, energy: dict) -> Dict[str, float]:
    """Protein and fat in grams per day, at the minimum, on this food.

    Derived from the energy requirement: the animal has to eat enough of this
    food to cover its calories, and that amount of food carries a certain
    amount of dry matter, of which the minimum share must be protein.
    """
    target_grams = grams_for_energy(food, energy["mer_kcal"])
    dry_matter = target_grams * food.dry_matter_pct / 100
    limits = minimums(pet)
    return {
        "food_grams": target_grams,
        "dry_matter_g": round(dry_matter, 1),
        "protein_g": round(dry_matter * limits["protein"] / 100, 1),
        "fat_g": round(dry_matter * limits["fat"] / 100, 1),
    }


# --- Current diet --------------------------------------------------------

def current_food(pet: Pet) -> Optional[Food]:
    """The food from the most recent feeding record."""
    record = pets_db.current_feeding(pet.id)
    if record is None:
        return None
    if record.food_id:
        food = foods_db.get(record.food_id)
        if food:
            return food
    if record.food_brand:
        return foods_db.get_by_name(record.food_brand)
    return None


def analyse(pet: Pet) -> Optional[dict]:
    """Full picture: what is being fed against what is needed.

    Returns None when there is nothing to compare — no weight, no feeding
    record, or a food whose label was never entered.
    """
    energy = daily_energy(pet)
    if energy is None:
        return None

    record = pets_db.current_feeding(pet.id)
    food = current_food(pet)
    if record is None or food is None:
        return {"energy": energy, "food": None}

    served = meal(food, record.grams)
    required = required_grams(pet, food, energy)
    limits = minimums(pet)

    energy_ratio = served.kcal / energy["mer_kcal"] if energy["mer_kcal"] else 0

    return {
        "energy": energy,
        "food": {
            "id": food.id,
            "name": food.name,
            "is_sample": food.is_sample,
            "kcal_per_100g": food.kcal_per_100g,
            "protein_pct": food.protein_pct,
            "fat_pct": food.fat_pct,
            "fibre_pct": food.fibre_pct,
            "moisture_pct": food.moisture_pct,
        },
        "served": {
            "grams": served.grams,
            "kcal": served.kcal,
            "protein_g": served.protein_g,
            "fat_g": served.fat_g,
            "fibre_g": served.fibre_g,
            "dry_matter_g": served.dry_matter_g,
            "protein_dm_pct": round(served.protein_dm_pct, 1),
            "fat_dm_pct": round(served.fat_dm_pct, 1),
        },
        "required": required,
        "minimums_dm_pct": limits,
        "deltas": {
            "kcal": round(served.kcal - energy["mer_kcal"], 1),
            "grams": round(served.grams - required["food_grams"], 1),
            "protein_g": round(served.protein_g - required["protein_g"], 1),
            "fat_g": round(served.fat_g - required["fat_g"], 1),
        },
        "energy_ratio": round(energy_ratio, 3),
        "meets_protein_minimum": served.protein_dm_pct >= limits["protein"],
        "meets_fat_minimum": served.fat_dm_pct >= limits["fat"],
    }


def analyse_record(pet: Pet, record_id: int) -> Optional[dict]:
    """One feeding record on its own, for when a row is clicked."""
    record = next((r for r in pets_db.feedings(pet.id) if r.id == record_id), None)
    if record is None:
        return None

    food = None
    if record.food_id:
        food = foods_db.get(record.food_id)
    if food is None and record.food_brand:
        food = foods_db.get_by_name(record.food_brand)
    if food is None:
        return None

    energy = daily_energy(pet)
    served = meal(food, record.grams)
    limits = minimums(pet)

    out = {
        "record_id": record.id,
        "recorded_on": record.recorded_on.isoformat(),
        "meals_per_day": record.meals_per_day,
        "note": record.note,
        "food": {"id": food.id, "name": food.name, "is_sample": food.is_sample,
                 "kcal_per_100g": food.kcal_per_100g},
        "served": {
            "grams": served.grams, "kcal": served.kcal,
            "protein_g": served.protein_g, "fat_g": served.fat_g,
            "fibre_g": served.fibre_g, "dry_matter_g": served.dry_matter_g,
            "protein_dm_pct": round(served.protein_dm_pct, 1),
            "fat_dm_pct": round(served.fat_dm_pct, 1),
        },
        "minimums_dm_pct": limits,
        "meets_protein_minimum": served.protein_dm_pct >= limits["protein"],
        "meets_fat_minimum": served.fat_dm_pct >= limits["fat"],
    }

    if record.meals_per_day:
        per_meal = meal(food, record.grams / record.meals_per_day)
        out["per_meal"] = {
            "grams": round(per_meal.grams, 1), "kcal": per_meal.kcal,
            "protein_g": per_meal.protein_g, "fat_g": per_meal.fat_g,
        }

    if energy:
        required = required_grams(pet, food, energy)
        out["energy"] = energy
        out["required"] = required
        out["deltas"] = {
            "kcal": round(served.kcal - energy["mer_kcal"], 1),
            "grams": round(served.grams - required["food_grams"], 1),
            "protein_g": round(served.protein_g - required["protein_g"], 1),
            "fat_g": round(served.fat_g - required["fat_g"], 1),
        }
    return out


def daily_series(pet: Pet, days: int) -> List[dict]:
    """What was fed on each of the last `days` days.

    Feeding records say "from this date, this amount of this food". They are
    carried forward until the next record, which is how the data is actually
    entered — nobody logs an identical row every morning.
    """
    records = sorted(pets_db.feedings(pet.id), key=lambda r: r.recorded_on)
    if not records:
        return []

    today = date.today()
    out: List[dict] = []

    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        active = [r for r in records if r.recorded_on <= day]
        if not active:
            out.append({"date": day.isoformat(), "kcal": None, "grams": None,
                        "protein_g": None, "food": None})
            continue

        record = active[-1]
        food = None
        if record.food_id:
            food = foods_db.get(record.food_id)
        if food is None and record.food_brand:
            food = foods_db.get_by_name(record.food_brand)

        if food is None:
            out.append({"date": day.isoformat(), "kcal": None,
                        "grams": record.grams, "protein_g": None, "food": None})
            continue

        served = meal(food, record.grams)
        out.append({
            "date": day.isoformat(), "grams": served.grams, "kcal": served.kcal,
            "protein_g": served.protein_g, "fat_g": served.fat_g,
            "food": food.name,
        })

    return out


def analyse_period(pet: Pet, days: int) -> Optional[dict]:
    """Average daily intake over a window, against the same daily requirement."""
    energy = daily_energy(pet)
    if energy is None:
        return None

    series = daily_series(pet, days)
    covered = [d for d in series if d["kcal"] is not None]
    if not covered:
        return {"days": days, "covered_days": 0, "energy": energy, "series": series}

    count = len(covered)
    mean = lambda key: round(sum(d[key] for d in covered) / count, 1)

    avg_kcal = mean("kcal")
    foods = []
    for day in covered:
        if day["food"] and day["food"] not in foods:
            foods.append(day["food"])

    return {
        "days": days,
        "covered_days": count,
        "energy": energy,
        "foods": foods,
        "average": {
            "kcal": avg_kcal,
            "grams": mean("grams"),
            "protein_g": mean("protein_g"),
            "fat_g": mean("fat_g"),
        },
        "total": {
            "kcal": round(sum(d["kcal"] for d in covered)),
            "grams": round(sum(d["grams"] for d in covered)),
        },
        "deltas": {"kcal": round(avg_kcal - energy["mer_kcal"], 1)},
        "energy_ratio": round(avg_kcal / energy["mer_kcal"], 3)
        if energy["mer_kcal"] else 0,
        "series": series,
    }


def compare_foods(pet: Pet, food_ids: List[int]) -> List[dict]:
    """Side by side: how much of each food covers the same daily energy."""
    energy = daily_energy(pet)
    if energy is None:
        return []

    out = []
    for food_id in food_ids:
        food = foods_db.get(food_id)
        if food is None:
            continue
        required = required_grams(pet, food, energy)
        served = meal(food, required["food_grams"])
        limits = minimums(pet)
        out.append({
            "id": food.id,
            "name": food.name,
            "is_sample": food.is_sample,
            "grams_per_day": required["food_grams"],
            "kcal": served.kcal,
            "protein_g": served.protein_g,
            "fat_g": served.fat_g,
            "protein_dm_pct": round(served.protein_dm_pct, 1),
            "meets_protein_minimum": served.protein_dm_pct >= limits["protein"],
        })
    return out
