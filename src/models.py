"""Shared data types.

This is the contract between the ingestion side (chunking, db, ingest) and
the query side (retrieve, rag, cli). Both halves import from here, so they can
be built independently as long as these shapes hold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

import numpy as np


@dataclass
class Chunk:
    """A passage of a source document, with its embedding."""

    source: str          # file name, e.g. "vaccination.md"
    chunk_index: int     # position within that file, 0-based
    content: str
    embedding: Optional[np.ndarray] = None   # float32, shape (dim,)
    id: Optional[int] = None                 # set by the database


@dataclass
class Retrieved:
    """A chunk plus how well it matched the query."""

    chunk: Chunk
    score: float


@dataclass
class Answer:
    """The result of a full RAG round trip."""

    text: str
    sources: List[str] = field(default_factory=list)
    retrieved: List[Retrieved] = field(default_factory=list)
    latency_s: float = 0.0
    used_fallback: bool = False
    used_pet_record: bool = False   # True when the animal's own data fed the prompt


# --- The animal and its records ------------------------------------------
#
# The document collection is general knowledge. These types hold what is true
# of one specific animal, which is what turns "puppies need 3-4 meals a day"
# into "Bella is being fed 2.5 cups when the guide says 2.0".


@dataclass
class Pet:
    """Profile of one animal."""

    name: str
    species: str = "dog"              # "dog" | "cat"
    breed: Optional[str] = None
    birth_date: Optional[date] = None
    sex: Optional[str] = None         # "female" | "male"
    target_weight_kg: Optional[float] = None
    owner_name: Optional[str] = None
    # Changes daily energy need by roughly 12%, so it is asked rather than
    # assumed. None means "not stated" and the calculation says so.
    neutered: Optional[bool] = None
    id: Optional[int] = None

    @property
    def age_months(self) -> Optional[int]:
        if self.birth_date is None:
            return None
        today = date.today()
        return (today.year - self.birth_date.year) * 12 + today.month - self.birth_date.month

    def age_text(self, lang: str = "en") -> str:
        months = self.age_months
        if months is None:
            return "-"
        years, rest = divmod(months, 12)
        if lang == "tr":
            parts = ([f"{years} yıl"] if years else []) + ([f"{rest} ay"] if rest else [])
            return " ".join(parts) or "0 ay"
        parts = ([f"{years} yr"] if years else []) + ([f"{rest} mo"] if rest else [])
        return " ".join(parts) or "0 mo"


@dataclass
class WeightRecord:
    """One weighing."""

    pet_id: int
    recorded_on: date
    weight_kg: float
    id: Optional[int] = None


@dataclass
class Food:
    """A food and the numbers from its guaranteed analysis panel.

    Percentages are "as fed" — exactly as printed on the bag — because that is
    what the user can read off the label without doing arithmetic. Conversion to
    a dry matter basis, which is what nutritional minimums are expressed in,
    happens in nutrition.py.
    """

    name: str
    kcal_per_100g: float
    protein_pct: float
    fat_pct: float
    species: str = "both"             # "dog" | "cat" | "both"
    fibre_pct: float = 0.0
    moisture_pct: float = 10.0        # dry food is typically 8-12%
    ash_pct: float = 0.0
    # Bag size. Does not affect nutrition — a 420 g and a 1 kg bag of the same
    # product have identical values per 100 g — but it is how the product is
    # bought, and it lets the app say how long a bag will last.
    pack_size_g: Optional[float] = None
    life_stage: Optional[str] = None  # "kitten" | "puppy" | "adult" | "senior"
    is_sample: bool = False           # seeded example, not a real product
    id: Optional[int] = None

    @property
    def dry_matter_pct(self) -> float:
        return 100.0 - self.moisture_pct

    @property
    def kcal_per_gram(self) -> float:
        return self.kcal_per_100g / 100.0


@dataclass
class FeedingRecord:
    """What the animal was fed, as of a date.

    Stored in grams. Bags and labels are in grams, and a "cup" is not a unit —
    the same cup of two different foods differs by 20% in weight.
    """

    pet_id: int
    recorded_on: date
    grams: float
    food_id: Optional[int] = None
    food_brand: Optional[str] = None   # kept for records predating the catalog
    meals_per_day: Optional[int] = None
    note: Optional[str] = None
    id: Optional[int] = None


@dataclass
class MealNutrition:
    """What one amount of one food actually delivers."""

    grams: float
    kcal: float
    protein_g: float
    fat_g: float
    fibre_g: float
    dry_matter_g: float

    @property
    def protein_dm_pct(self) -> float:
        return self.protein_g / self.dry_matter_g * 100 if self.dry_matter_g else 0.0

    @property
    def fat_dm_pct(self) -> float:
        return self.fat_g / self.dry_matter_g * 100 if self.dry_matter_g else 0.0


@dataclass
class StoolRecord:
    """Stool quality and frequency, a practical proxy for digestive health."""

    pet_id: int
    recorded_on: date
    quality: str                      # "normal" | "soft" | "loose" | "hard"
    frequency_per_day: Optional[float] = None
    id: Optional[int] = None


@dataclass
class VaccineRecord:
    """One dose actually given."""

    pet_id: int
    given_on: date
    vaccine_key: str                  # "dhpp" | "rabies" | "fvrcp" | ...
    vet_name: Optional[str] = None
    batch: Optional[str] = None
    note: Optional[str] = None
    # Set only when the vet wrote a specific date on the card, which overrides
    # whatever the standard interval would suggest.
    next_due_on: Optional[date] = None
    id: Optional[int] = None


@dataclass
class VaccineDue:
    """What is coming up, or overdue, for one vaccine."""

    key: str
    name_en: str
    name_tr: str
    core: bool
    doses_given: int
    last_given: Optional[date]
    due_on: Optional[date]
    status: str                       # overdue | due_soon | scheduled | unknown
    days_until: Optional[int]
    reason_en: str
    reason_tr: str

    def name(self, lang: str = "en") -> str:
        return self.name_tr if lang == "tr" else self.name_en

    def reason(self, lang: str = "en") -> str:
        return self.reason_tr if lang == "tr" else self.reason_en


@dataclass
class Insight:
    """One finding produced by the rules in insights.py.

    Deliberately not generated by the language model: these drive warnings a
    user may act on, so they have to be reproducible and explainable.
    """

    level: str                        # "warning" | "positive" | "suggestion"
    title_en: str
    title_tr: str
    detail_en: str
    detail_tr: str

    def title(self, lang: str = "en") -> str:
        return self.title_tr if lang == "tr" else self.title_en

    def detail(self, lang: str = "en") -> str:
        return self.detail_tr if lang == "tr" else self.detail_en
