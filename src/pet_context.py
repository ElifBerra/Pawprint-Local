"""Turns one animal's records into a block of text the model can read.

This is the piece that separates Pawprint from a document search box. The
document collection can say "puppies under four months need three to four meals
a day"; only these records can say that Bella is being fed 2.5 cups of a food
whose guideline is 2.0, and that she has gained 0.8 kg since the brand changed.

The facts are computed in insights.py and merely formatted here. Nothing in
this module does arithmetic the model could get wrong.
"""

from __future__ import annotations

from typing import List, Optional

from . import insights, pets_db
from .models import Pet


def has_useful_records(pet: Pet) -> bool:
    """Whether there is enough on file to be worth putting in a prompt."""
    return bool(pets_db.weights(pet.id) or pets_db.current_feeding(pet.id))


def build(pet: Pet, lang: str = "en") -> str:
    """A compact profile-and-records block for the prompt.

    Written as short labelled lines rather than prose: it survives being
    truncated, and the model copies numbers more reliably out of a list than
    out of a paragraph.
    """
    data = insights.summary(pet)
    lines: List[str] = []

    lines.append(f"Name: {pet.name}")
    lines.append(f"Species: {pet.species}")
    if pet.breed:
        lines.append(f"Breed: {pet.breed}")
    age = pet.age_text("en")
    if age != "-":
        lines.append(f"Age: {age}")
    if pet.sex:
        lines.append(f"Sex: {pet.sex}")

    if data["current_weight_kg"] is not None:
        line = f"Current weight: {data['current_weight_kg']} kg"
        if data["measured_on"]:
            line += f" (measured {data['measured_on']})"
        lines.append(line)

    if data["target_weight_kg"] is not None:
        lines.append(f"Target weight: {data['target_weight_kg']} kg")
        if data["over_target_kg"] is not None:
            lines.append(
                f"Difference from target: {data['over_target_kg']:+.1f} kg "
                f"({data['over_target_pct']:+.1f}%)"
            )

    if data["weight_change_kg"] is not None:
        lines.append(
            f"Weight change over the last {data['weight_change_weeks']} weeks: "
            f"{data['weight_change_kg']:+.1f} kg"
        )

    if data["food_brand"]:
        lines.append(f"Current food: {data['food_brand']}")
    if data["portion_cups"] is not None:
        line = f"Daily portion: {data['portion_cups']} cups"
        if data["recommended_cups"] is not None:
            line += f" (manufacturer guideline: {data['recommended_cups']} cups)"
        lines.append(line)

    feeding = pets_db.current_feeding(pet.id)
    if feeding and feeding.meals_per_day:
        lines.append(f"Meals per day: {feeding.meals_per_day}")

    change = pets_db.last_food_change(pet.id)
    if change:
        lines.append(
            f"Food last changed: {change.recorded_on.isoformat()} "
            f"(to {change.food_brand})"
        )

    if data["stool_normal_pct"] is not None:
        lines.append(
            f"Stool normal in the last {insights.STOOL_WINDOW_DAYS} days: "
            f"{data['stool_normal_pct']}%"
        )

    return "\n".join(lines)


def weight_history_text(pet: Pet, limit: int = 8) -> Optional[str]:
    """Recent weighings as one line, for questions about the trend."""
    records = pets_db.weights(pet.id, limit=limit)
    if len(records) < 2:
        return None
    pairs = ", ".join(
        f"{r.recorded_on.isoformat()}: {r.weight_kg} kg" for r in records
    )
    return f"Recent weighings — {pairs}"
