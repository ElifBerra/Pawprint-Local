"""HTTP API for the Pawprint web interface.

A thin layer: every endpoint delegates to the same modules the CLI uses, so the
browser cannot get different behaviour from what was measured. Runs on
localhost only — there is no authentication because nothing leaves the machine.

Run:  uvicorn src.api:app --reload
      python -m src.serve          (convenience wrapper)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import (config, db, foods_db, foundry, insights, nutrition, pets_db,
               rag, report, vaccines)
from .models import (FeedingRecord, Food, Pet, StoolRecord, VaccineRecord,
                     WeightRecord)

logger = logging.getLogger(__name__)

WEB_DIR = config.ROOT_DIR / "web"

app = FastAPI(title="Pawprint-Local", version="2.0")


# --- Request bodies ------------------------------------------------------

class PetIn(BaseModel):
    name: str
    species: str = "dog"
    breed: Optional[str] = None
    birth_date: Optional[date] = None
    sex: Optional[str] = None
    target_weight_kg: Optional[float] = None
    owner_name: Optional[str] = None
    neutered: Optional[bool] = None
    id: Optional[int] = None


class FoodIn(BaseModel):
    """The guaranteed analysis panel, as printed on the bag."""

    name: str = Field(min_length=1, max_length=120)
    species: str = Field(default="both", pattern="^(dog|cat|both)$")
    kcal_per_100g: float = Field(gt=0, lt=900)
    protein_pct: float = Field(ge=0, le=100)
    fat_pct: float = Field(ge=0, le=100)
    fibre_pct: float = Field(default=0, ge=0, le=100)
    moisture_pct: float = Field(default=10, ge=0, le=95)
    ash_pct: float = Field(default=0, ge=0, le=100)
    id: Optional[int] = None


class RecordIn(BaseModel):
    """Shared date validation.

    A record dated in the future silently distorts every trend, because they
    are all computed from the most recent weighing. Cheaper to reject here than
    to explain the resulting numbers later.
    """

    recorded_on: date

    @field_validator("recorded_on")
    @classmethod
    def not_in_the_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("recorded_on cannot be in the future")
        return value


class WeightIn(RecordIn):
    weight_kg: float = Field(gt=0, lt=200)


class FeedingIn(RecordIn):
    """Grams, and either a food already in the catalogue or a new one.

    `new_food` is the "Other" path: the user reads the panel off a bag we have
    never seen, and it is saved to the catalogue at the same time so they never
    type it twice.
    """

    grams: float = Field(gt=0, lt=5000)
    food_id: Optional[int] = None
    new_food: Optional[FoodIn] = None
    meals_per_day: Optional[int] = Field(default=None, ge=1, le=10)
    note: Optional[str] = None


class StoolIn(RecordIn):
    quality: str = Field(pattern="^(normal|soft|loose|hard)$")
    frequency_per_day: Optional[float] = Field(default=None, ge=0, le=20)


class VaccineIn(BaseModel):
    """A dose that was given. Unlike the others this is dated in the past by
    definition, but next_due_on is allowed to be in the future — that is the
    date the vet wrote on the card."""

    given_on: date
    vaccine_key: str = Field(min_length=1, max_length=40)
    vet_name: Optional[str] = None
    batch: Optional[str] = None
    note: Optional[str] = None
    next_due_on: Optional[date] = None

    @field_validator("given_on")
    @classmethod
    def not_in_the_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("given_on cannot be in the future")
        return value


class AskIn(BaseModel):
    question: str
    lang: str = config.DEFAULT_LANGUAGE
    top_k: Optional[int] = None
    threshold: Optional[float] = None


# --- Helpers -------------------------------------------------------------

def _pet_or_404(pet_id: Optional[int] = None) -> Pet:
    pet = pets_db.get_pet(pet_id) if pet_id else pets_db.first_pet()
    if pet is None:
        raise HTTPException(404, "No pet on file. Run scripts/seed_demo.py.")
    return pet


def _pet_dict(pet: Pet, lang: str) -> dict:
    return {
        "id": pet.id,
        "name": pet.name,
        "species": pet.species,
        "breed": pet.breed,
        "birth_date": pet.birth_date.isoformat() if pet.birth_date else None,
        "sex": pet.sex,
        "target_weight_kg": pet.target_weight_kg,
        "owner_name": pet.owner_name,
        "neutered": pet.neutered,
        "age_text": pet.age_text(lang),
    }


def _food_dict(food: Food) -> dict:
    return {
        "id": food.id,
        "name": food.name,
        "species": food.species,
        "kcal_per_100g": food.kcal_per_100g,
        "protein_pct": food.protein_pct,
        "fat_pct": food.fat_pct,
        "fibre_pct": food.fibre_pct,
        "moisture_pct": food.moisture_pct,
        "ash_pct": food.ash_pct,
        "is_sample": food.is_sample,
    }


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    pets_db.init_db()
    foods_db.init_db()
    foods_db.seed_from_json()
    logger.info("API ready")


# --- Status --------------------------------------------------------------

@app.get("/api/status")
def status(lang: str = config.DEFAULT_LANGUAGE) -> dict:
    """What the interface needs to render before any user action."""
    corpus = db.stats()
    pet = pets_db.first_pet()

    reminder = None
    if pet is not None:
        upcoming = vaccines.next_appointment(pet)
        if upcoming is not None:
            reminder = {
                "name": upcoming.name(lang),
                "due_on": upcoming.due_on.isoformat() if upcoming.due_on else None,
                "status": upcoming.status,
                "days_until": upcoming.days_until,
            }

    return {
        "corpus": corpus,
        "has_pet": pet is not None,
        "pet": _pet_dict(pet, lang) if pet else None,
        "reminder": reminder,
        "languages": list(config.LANGUAGES),
        "answer_language": config.answer_language(lang),
        "turkish_answers_enabled": config.EXPERIMENTAL_TURKISH_ANSWERS,
        "models": {
            "chat": config.CHAT_MODEL_ALIAS,
            "embedding": config.EMBEDDING_MODEL_ALIAS,
        },
        "retrieval": {
            "top_k": config.TOP_K,
            "threshold": config.threshold(lang),
        },
    }


@app.post("/api/warmup")
def warmup() -> dict:
    """Load the models so the first question is not the slow one."""
    foundry.get_chat_client()
    foundry.get_embedding_client()
    return {"ready": True}


# --- Pet profile ---------------------------------------------------------

@app.get("/api/pet")
def get_pet(lang: str = config.DEFAULT_LANGUAGE) -> dict:
    return _pet_dict(_pet_or_404(), lang)


@app.put("/api/pet")
def put_pet(body: PetIn, lang: str = config.DEFAULT_LANGUAGE) -> dict:
    existing = pets_db.first_pet()
    pet = Pet(
        id=body.id or (existing.id if existing else None),
        name=body.name,
        species=body.species,
        breed=body.breed,
        birth_date=body.birth_date,
        sex=body.sex,
        target_weight_kg=body.target_weight_kg,
        owner_name=body.owner_name,
        neutered=body.neutered,
    )
    return _pet_dict(pets_db.save_pet(pet), lang)


# --- Records -------------------------------------------------------------

@app.get("/api/records")
def get_records() -> dict:
    pet = _pet_or_404()
    return {
        "weights": [
            {"id": r.id, "recorded_on": r.recorded_on.isoformat(),
             "weight_kg": r.weight_kg}
            for r in pets_db.weights(pet.id)
        ],
        "feedings": [
            {"id": r.id, "recorded_on": r.recorded_on.isoformat(),
             "grams": r.grams, "food_id": r.food_id,
             "food_brand": r.food_brand, "meals_per_day": r.meals_per_day,
             "note": r.note}
            for r in pets_db.feedings(pet.id)
        ],
        "stools": [
            {"id": r.id, "recorded_on": r.recorded_on.isoformat(),
             "quality": r.quality, "frequency_per_day": r.frequency_per_day}
            for r in pets_db.stools(pet.id)
        ],
    }


@app.post("/api/records/weight")
def post_weight(body: WeightIn) -> dict:
    pet = _pet_or_404()
    record = pets_db.add_weight(WeightRecord(
        pet_id=pet.id, recorded_on=body.recorded_on, weight_kg=body.weight_kg,
    ))
    return {"id": record.id}


@app.post("/api/records/feeding")
def post_feeding(body: FeedingIn) -> dict:
    pet = _pet_or_404()

    food_id = body.food_id
    created = None

    if body.new_food is not None:
        existing = foods_db.get_by_name(body.new_food.name)
        if existing is not None:
            food_id = existing.id
        else:
            created = foods_db.save(Food(**body.new_food.model_dump(
                exclude={"id"}
            )))
            food_id = created.id

    if food_id is None:
        raise HTTPException(400, "Pick a food or provide its label values.")

    food = foods_db.get(food_id)
    if food is None:
        raise HTTPException(404, "Unknown food.")

    record = pets_db.add_feeding(FeedingRecord(
        pet_id=pet.id, recorded_on=body.recorded_on, grams=body.grams,
        food_id=food.id, food_brand=food.name,
        meals_per_day=body.meals_per_day, note=body.note,
    ))
    return {
        "id": record.id,
        "food": _food_dict(food),
        "created_food": created is not None,
        "meal": {
            "kcal": nutrition.meal(food, body.grams).kcal,
            "protein_g": nutrition.meal(food, body.grams).protein_g,
        },
    }


# --- Vaccinations --------------------------------------------------------

@app.get("/api/vaccines")
def get_vaccines(lang: str = config.DEFAULT_LANGUAGE) -> dict:
    """Doses given, and what is due next for each vaccine."""
    pet = _pet_or_404()
    schedule = {v["key"]: v for v in vaccines.schedule_for(pet.species)}

    return {
        "records": [
            {
                "id": r.id,
                "given_on": r.given_on.isoformat(),
                "vaccine_key": r.vaccine_key,
                "name": (schedule.get(r.vaccine_key, {}).get(
                    "name_tr" if lang == "tr" else "name_en", r.vaccine_key)),
                "vet_name": r.vet_name,
                "batch": r.batch,
                "note": r.note,
                "next_due_on": r.next_due_on.isoformat() if r.next_due_on else None,
            }
            for r in reversed(pets_db.vaccines(pet.id))
        ],
        "due": [
            {
                "key": d.key,
                "name": d.name(lang),
                "core": d.core,
                "doses_given": d.doses_given,
                "last_given": d.last_given.isoformat() if d.last_given else None,
                "due_on": d.due_on.isoformat() if d.due_on else None,
                "status": d.status,
                "days_until": d.days_until,
                "reason": d.reason(lang),
            }
            for d in vaccines.due_list(pet)
        ],
        "catalogue": [
            {"key": v["key"],
             "name": v["name_tr"] if lang == "tr" else v["name_en"],
             "core": v["core"]}
            for v in vaccines.schedule_for(pet.species)
        ],
    }


@app.post("/api/vaccines")
def post_vaccine(body: VaccineIn) -> dict:
    pet = _pet_or_404()
    record = pets_db.add_vaccine(VaccineRecord(
        pet_id=pet.id, given_on=body.given_on, vaccine_key=body.vaccine_key,
        vet_name=body.vet_name, batch=body.batch, note=body.note,
        next_due_on=body.next_due_on,
    ))
    return {"id": record.id}


@app.delete("/api/vaccines/{record_id}")
def delete_vaccine(record_id: int) -> dict:
    pets_db.delete_vaccine(record_id)
    return {"deleted": record_id}


# --- Food catalogue ------------------------------------------------------

@app.get("/api/foods")
def get_foods(species: Optional[str] = None) -> dict:
    """Foods this animal could eat. Samples are flagged, not hidden."""
    if species is None:
        pet = pets_db.first_pet()
        species = pet.species if pet else None
    return {"foods": [_food_dict(f) for f in foods_db.list_foods(species)]}


@app.post("/api/foods")
def post_food(body: FoodIn) -> dict:
    if foods_db.get_by_name(body.name) is not None:
        raise HTTPException(409, "A food with that name already exists.")
    food = foods_db.save(Food(**body.model_dump(exclude={"id"})))
    return _food_dict(food)


@app.delete("/api/foods/{food_id}")
def delete_food(food_id: int) -> dict:
    foods_db.delete(food_id)
    return {"deleted": food_id}


# --- Nutrition -----------------------------------------------------------

@app.get("/api/nutrition")
def get_nutrition() -> dict:
    """Energy and macros: what is being fed against what is needed."""
    pet = _pet_or_404()
    analysis = nutrition.analyse(pet)
    if analysis is None:
        return {"available": False, "reason": "no_weight"}
    if analysis.get("food") is None:
        return {"available": False, "reason": "no_food", "energy": analysis["energy"]}
    return {"available": True, **analysis}


@app.get("/api/nutrition/compare")
def compare_nutrition(ids: str = "") -> dict:
    """Same animal, several foods: how many grams a day each would take."""
    pet = _pet_or_404()
    if ids.strip():
        food_ids = [int(part) for part in ids.split(",") if part.strip().isdigit()]
    else:
        food_ids = [f.id for f in foods_db.list_foods(pet.species)]
    return {"foods": nutrition.compare_foods(pet, food_ids)}


@app.post("/api/records/stool")
def post_stool(body: StoolIn) -> dict:
    pet = _pet_or_404()
    record = pets_db.add_stool(StoolRecord(
        pet_id=pet.id, recorded_on=body.recorded_on, quality=body.quality,
        frequency_per_day=body.frequency_per_day,
    ))
    return {"id": record.id}


# --- Insights ------------------------------------------------------------

@app.get("/api/insights")
def get_insights(lang: str = config.DEFAULT_LANGUAGE) -> dict:
    pet = _pet_or_404()
    found = insights.generate(pet)
    return {
        "summary": insights.summary(pet),
        "weights": [
            {"recorded_on": r.recorded_on.isoformat(), "weight_kg": r.weight_kg}
            for r in pets_db.weights(pet.id, limit=12)
        ],
        "insights": [
            {"level": i.level, "title": i.title(lang), "detail": i.detail(lang)}
            for i in found
        ],
    }


# --- Question answering --------------------------------------------------

@app.post("/api/ask")
def ask(body: AskIn):
    """Stream the answer as newline-delimited JSON.

    Each line is one object: {"type": "token"} while generating, then a single
    {"type": "done"} carrying sources, timing and the retrieved passages.
    """
    pet = pets_db.first_pet()
    answer_lang = config.answer_language(body.lang)

    def events():
        generator = rag.answer_stream(
            body.question,
            k=body.top_k,
            threshold=body.threshold,
            pet=pet,
            lang=answer_lang,
        )
        while True:
            try:
                piece = next(generator)
                yield json.dumps({"type": "token", "text": piece}) + "\n"
            except StopIteration as stop:
                result = stop.value
                yield json.dumps({
                    "type": "done",
                    "text": result.text,
                    "sources": result.sources,
                    "latency_s": round(result.latency_s, 1),
                    "used_fallback": result.used_fallback,
                    "used_pet_record": result.used_pet_record,
                    "answer_language": answer_lang,
                    "retrieved": [
                        {
                            "source": r.chunk.source,
                            "chunk_index": r.chunk.chunk_index,
                            "score": round(r.score, 3),
                            "content": r.chunk.content,
                        }
                        for r in result.retrieved
                    ],
                }) + "\n"
                return
            except Exception as exc:  # keep the stream well-formed on failure
                logger.exception("Answer failed")
                yield json.dumps({
                    "type": "error",
                    "message": f"{type(exc).__name__}: {exc}",
                }) + "\n"
                return

    return StreamingResponse(events(), media_type="application/x-ndjson")


# --- Vet report ----------------------------------------------------------

@app.get("/api/report")
def get_report(lang: str = config.DEFAULT_LANGUAGE) -> dict:
    return report.build(_pet_or_404(), lang)


@app.get("/api/report.pdf")
def get_report_pdf(lang: str = config.DEFAULT_LANGUAGE):
    pet = _pet_or_404()
    path = report.write_pdf(pet, lang)
    stamp = datetime.now().strftime("%Y%m%d")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"pawprint-{pet.name.lower()}-{stamp}.pdf",
    )


# --- Static front end ----------------------------------------------------
# Mounted last so the API routes above take precedence.

if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
