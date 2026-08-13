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

from . import config, db, foundry, insights, pets_db, rag, report
from .models import FeedingRecord, Pet, StoolRecord, WeightRecord

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
    food_brand: str
    portion_cups: float = Field(gt=0, lt=50)
    meals_per_day: Optional[int] = Field(default=None, ge=1, le=10)
    note: Optional[str] = None


class StoolIn(RecordIn):
    quality: str = Field(pattern="^(normal|soft|loose|hard)$")
    frequency_per_day: Optional[float] = Field(default=None, ge=0, le=20)


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
        "age_text": pet.age_text(lang),
    }


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    pets_db.init_db()
    logger.info("API ready")


# --- Status --------------------------------------------------------------

@app.get("/api/status")
def status(lang: str = config.DEFAULT_LANGUAGE) -> dict:
    """What the interface needs to render before any user action."""
    corpus = db.stats()
    pet = pets_db.first_pet()
    return {
        "corpus": corpus,
        "has_pet": pet is not None,
        "pet": _pet_dict(pet, lang) if pet else None,
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
             "food_brand": r.food_brand, "portion_cups": r.portion_cups,
             "meals_per_day": r.meals_per_day, "note": r.note,
             "recommended_cups": insights.portion_guidance(r.food_brand)}
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
    record = pets_db.add_feeding(FeedingRecord(
        pet_id=pet.id, recorded_on=body.recorded_on, food_brand=body.food_brand,
        portion_cups=body.portion_cups, meals_per_day=body.meals_per_day,
        note=body.note,
    ))
    return {"id": record.id}


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
