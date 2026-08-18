"""The records block that goes into the prompt.

Most of these guard one specific failure. Asked "should I reduce Khaleesi's
portion?", the model retrieved a passage saying a portion should be reduced when
the ribs cannot be felt, saw that the weight differed from target, and answered
"yes, reduce" — for a cat 2.5 kg *under* target. Nothing in the prompt was
false; the model applied a general rule without checking which way the
difference ran.

So the direction is decided here, by comparison, and the model is left to phrase
it. These tests exist because that answer would have gone into a demo video.
"""

from __future__ import annotations

import pytest

from src import insights, pet_context

from conftest import add_feeding, add_weights


def direction_for(pet) -> str:
    return pet_context.feeding_direction(insights.summary(pet)) or ""


# --- Feeding direction ---------------------------------------------------

def test_an_underweight_animal_is_never_told_to_eat_less(cat):
    add_weights(cat, (1, 2.0), (0, 2.0))          # target 4.5 kg
    line = direction_for(cat)
    assert "UNDER its target weight" in line
    assert "Reducing the amount of food would be wrong" in line


def test_an_overweight_animal_is_told_to_reduce(dog):
    add_weights(dog, (1, 33.0), (0, 33.0))        # target 28.0 kg
    assert "OVER its target weight" in direction_for(dog)


def test_an_animal_at_target_is_told_to_hold(dog):
    add_weights(dog, (1, 28.0), (0, 28.0))
    assert "at its target weight" in direction_for(dog)


def test_a_small_difference_counts_as_on_target(dog):
    add_weights(dog, (1, 28.5), (0, 28.5))        # +1.8%, inside tolerance
    assert "at its target weight" in direction_for(dog)


def test_no_direction_without_a_target(store):
    from src.models import Pet
    from src import pets_db
    pet = pets_db.save_pet(Pet(name="No Target", species="dog"))
    add_weights(pet, (1, 20.0), (0, 20.0))
    assert pet_context.feeding_direction(insights.summary(pet)) is None


def test_no_direction_without_a_weighing(dog):
    assert pet_context.feeding_direction(insights.summary(dog)) is None


def test_the_direction_reaches_the_prompt(cat, food):
    add_weights(cat, (1, 2.0), (0, 2.0))
    add_feeding(cat, food, grams=40)
    assert "FEEDING DIRECTION" in pet_context.build(cat)


# --- The rest of the block -----------------------------------------------

def test_numbers_the_model_should_not_have_to_derive(dog, food):
    add_weights(dog, (3, 29.0), (0, 30.0))
    add_feeding(dog, food, grams=400)
    text = pet_context.build(dog)
    for label in ("Current weight", "Target weight", "Difference from target",
                  "Daily amount", "Calculated daily energy requirement"):
        assert label in text, label


def test_warnings_are_capped(cat, thin_food):
    add_weights(cat, (1, 2.0), (0, 2.0))
    add_feeding(cat, thin_food, grams=20)
    lines = pet_context.build(cat).splitlines()
    bullets = [line for line in lines if line.startswith("- ")]
    assert len(bullets) <= pet_context.MAX_WARNINGS


def test_search_terms_carry_species_and_life_stage(cat, kitten):
    assert pet_context.search_terms(cat) == "cat"
    assert pet_context.search_terms(kitten) == "cat kitten"
    assert pet_context.search_terms(None) is None


def test_topics_do_not_leak_values(cat):
    add_weights(cat, (0, 4.2))
    text = pet_context.topics_text(cat)
    assert "weight" in text
    assert "4.2" not in text        # subjects, not numbers — see topics_text


def test_topics_are_written_in_the_question_s_language(cat):
    english = pet_context.topics_text(cat, "en")
    turkish = pet_context.topics_text(cat, "tr")
    assert english != turkish
    assert "kaç aylık" in turkish   # the demo question that was refused
    assert "how old" in english
    assert "kedi" in turkish        # species too, not just the subjects


def test_the_breed_is_kept_out_of_the_topics(dog):
    # It raised "which dog breed is best for an apartment?" and answers nothing.
    assert dog.breed
    assert dog.breed not in pet_context.topics_text(dog)
    assert "breed" not in pet_context.topics_text(dog)


def test_an_unknown_language_falls_back_rather_than_failing(cat):
    assert pet_context.topics_text(cat, "de") == pet_context.topics_text(cat, "en")


def test_both_languages_cover_the_same_subjects(cat):
    # Not a translation check — a check that neither list quietly lost a
    # subject the other has, which would make one language answer questions
    # the other refuses.
    assert len(pet_context._TOPICS["en"]) == len(pet_context._TOPICS["tr"])
