"""Create the demo animal and eight weeks of records.

The scenario is deliberate rather than random: Bella is slightly over her
target weight, the gain starts shortly after a change of food, and her stool
records stay normal throughout. That combination exercises every rule in
insights.py and gives the demo something to actually say.

Run:  python -m scripts.seed_demo            # only if no pets exist
      python -m scripts.seed_demo --reset    # wipe pets and rebuild
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from src import pets_db
from src.models import FeedingRecord, Pet, StoolRecord, WeightRecord

# Weeks back from today, and the weight on that day. Near-flat while she was on
# the old food, then a clear rise that starts after the switch four weeks ago.
# The last three weeks come to +0.8 kg, which is what the weight rule reacts to.
WEIGHT_CURVE = [
    (8, 28.9),
    (7, 29.0),
    (6, 29.1),
    (5, 29.2),
    (4, 29.3),
    (3, 29.4),
    (2, 29.7),
    (1, 30.0),
    (0, 30.2),
]

# One soft day in a month of daily records: 29 of 30 normal, so the digestion
# rule reports a healthy figure without the data looking artificially perfect.
STOOL_PATTERN = ["normal"] * 11 + ["soft"] + ["normal"] * 18


def build(reset: bool) -> Pet:
    pets_db.init_db()

    if reset:
        for existing in pets_db.list_pets():
            pets_db.delete_pet(existing.id)
        print("Existing pets removed.")

    today = date.today()

    pet = pets_db.save_pet(Pet(
        name="Bella",
        species="dog",
        breed="Golden Retriever",
        birth_date=date(today.year - 3, 5, 15),
        sex="female",
        target_weight_kg=28.0,
        owner_name="Ahmet Yılmaz",
    ))
    print(f"Pet created: {pet.name} (id={pet.id})")

    for weeks_ago, kg in WEIGHT_CURVE:
        pets_db.add_weight(WeightRecord(
            pet_id=pet.id,
            recorded_on=today - timedelta(weeks=weeks_ago),
            weight_kg=kg,
        ))
    print(f"{len(WEIGHT_CURVE)} weight records added.")

    # The old food, then the switch that the weight curve reacts to.
    pets_db.add_feeding(FeedingRecord(
        pet_id=pet.id,
        recorded_on=today - timedelta(weeks=8),
        food_brand="Vetline Balance",
        portion_cups=2.0,
        meals_per_day=2,
        note="Previous food",
    ))
    pets_db.add_feeding(FeedingRecord(
        pet_id=pet.id,
        recorded_on=today - timedelta(weeks=4, days=3),
        food_brand="Acme Premium",
        portion_cups=2.5,
        meals_per_day=2,
        note="Switched brands; portion kept by eye rather than by the guide",
    ))
    print("2 feeding records added (one change of brand).")

    for index, quality in enumerate(STOOL_PATTERN):
        pets_db.add_stool(StoolRecord(
            pet_id=pet.id,
            recorded_on=today - timedelta(days=index),
            quality=quality,
            frequency_per_day=1.0,
        ))
    print(f"{len(STOOL_PATTERN)} stool records added.")

    return pet


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo pet.")
    parser.add_argument("--reset", action="store_true",
                        help="delete existing pets first")
    args = parser.parse_args()

    pets_db.init_db()
    if pets_db.list_pets() and not args.reset:
        print("A pet already exists. Use --reset to rebuild the demo data.")
        return

    pet = build(args.reset)

    from src import insights
    data = insights.summary(pet)
    print(
        f"\n{pet.name}: {data['current_weight_kg']} kg "
        f"(target {data['target_weight_kg']} kg, "
        f"{data['weight_change_kg']:+.1f} kg over "
        f"{data['weight_change_weeks']} weeks)"
    )
    print(f"Food: {data['food_brand']} {data['portion_cups']} cups "
          f"(guideline {data['recommended_cups']})")
    print(f"Stool normal: {data['stool_normal_pct']}%\n")

    for item in insights.generate(pet):
        print(f"  [{item.level:<10}] {item.title('en')}")
        print(f"               {item.detail('en')}")


if __name__ == "__main__":
    main()
