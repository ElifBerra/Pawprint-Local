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
from .models import Pet  # noqa: F401  (used in annotations below)

# The prompt grows with every warning, and prompt length is the dominant cost
# on CPU. Three is enough to surface a problem without turning the context into
# a report.
MAX_WARNINGS = 3


def has_useful_records(pet: Pet) -> bool:
    """Whether there is enough on file to be worth putting in a prompt."""
    return bool(pets_db.weights(pet.id) or pets_db.current_feeding(pet.id))


# Embedding of the records blob, keyed by its own text so it is recomputed
# whenever the records change and reused otherwise.
_relevance_cache: dict = {}


def relevance(pet: Pet, query_vector) -> float:
    """How close a question is to what the records are actually about.

    The document threshold has no say here, so without this a question the
    documents rejected still reached the model as long as the animal had
    records — and the model answered it from its own knowledge. Prompting
    could not stop that: phi-3.5-mini knows who won the 1998 World Cup and
    said so however firmly it was told not to.

    The fix is the mechanism the whole project already runs on. Embed what the
    records are about, measure the angle, and if the question is nowhere near
    them, do not call the model at all.
    """
    from . import embeddings

    text = topics_text(pet)
    if not text:
        return 0.0

    if text not in _relevance_cache:
        _relevance_cache.clear()          # one pet, one entry
        _relevance_cache[text] = embeddings.embed_one(text)

    vector = _relevance_cache[text]
    a = embeddings.normalize(vector)
    b = embeddings.normalize(query_vector)
    return float(a @ b)


def search_terms(pet: Optional[Pet]) -> Optional[str]:
    """The few words a user leaves out because they are obvious to them.

    Folded into the text that gets embedded for retrieval, not into the prompt.
    Species carries most of the signal; life stage matters because the document
    collection treats kittens and adults differently.
    """
    if pet is None:
        return None

    parts = [pet.species]
    months = pet.age_months
    if months is not None and months < 12:
        parts.append("kitten" if pet.species == "cat" else "puppy")
    return " ".join(parts)


def topics_text(pet: Pet) -> str:
    """What the records can speak to, as a sentence to embed.

    Subjects rather than values: "weight" rather than "5.0 kg". A question is
    being matched against what the records are about, not against the numbers
    themselves.
    """
    parts = [
        f"{pet.name} the {pet.species}",
        "body weight and weight trend",
        "target weight",
        "food, brand, daily amount in grams, portion and calories",
        "protein and fat intake",
        "stool quality and digestion",
        "vaccinations and their due dates",
        "feeding schedule and meals per day",
    ]
    if pet.breed:
        parts.insert(1, pet.breed)
    return ", ".join(parts)


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

    if data["food_name"]:
        lines.append(f"Current food: {data['food_name']}")
    if data["grams"] is not None:
        line = f"Daily amount: {data['grams']:.0f} g"
        if data["served_kcal"] is not None:
            line += f" ({data['served_kcal']:.0f} kcal)"
        lines.append(line)
    if data["daily_kcal_need"] is not None:
        lines.append(f"Calculated daily energy requirement: "
                     f"{data['daily_kcal_need']:.0f} kcal")
    if data["recommended_grams"] is not None:
        lines.append(f"Amount that would cover it: "
                     f"{data['recommended_grams']:.0f} g of this food")

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

    # Findings from the rule engine go in as well. Without them the assistant
    # answers "is this normal?" from the raw numbers and misses that the rules
    # already flagged something — an implausible weighing, an overdue vaccine,
    # a portion that does not match the requirement.
    #
    # Titles only, and capped. The full detail text roughly doubled the prompt,
    # and on CPU every extra token is measurable time. The title is enough for
    # the model to raise the flag; the user reads the detail on the Insights
    # page, where it is rendered from the same rule and not paraphrased.
    warnings = [f for f in insights.generate(pet) if f.level == "warning"]
    if warnings:
        lines.append("")
        lines.append("ACTIVE WARNINGS — raise any that relate to the question:")
        for item in warnings[:MAX_WARNINGS]:
            lines.append(f"- {item.title('en')}")

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
