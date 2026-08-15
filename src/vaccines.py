"""Vaccination schedule and what is due next.

The rules encoded here are the ones stated in data/docs/vaccination-schedule.md,
so the reminder and the RAG answer cannot disagree with one another. If that
document is edited, this table should be edited with it.

Everything is arithmetic on dates. Nothing here asks the language model, for
the same reason as insights.py: a reminder that says "overdue by 12 days" has
to say the same thing every time it is opened.

Schedules vary by country, by product and by the individual animal. The
interface presents these as a default to check with a vet, not as instructions.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from . import pets_db
from .models import Pet, VaccineDue, VaccineRecord

DUE_SOON_DAYS = 30

# start_weeks           age at which the first dose is normally given
# series_interval_weeks gap between doses in the initial series
# series_until_weeks    the series continues until at least this age
# first_booster_months  months after the series before the first booster
# booster_months        interval between routine boosters afterwards
SCHEDULES: Dict[str, List[dict]] = {
    "dog": [
        {
            "key": "dhpp", "core": True,
            "name_en": "DHPP (distemper, adenovirus, parainfluenza, parvovirus)",
            "name_tr": "Karma (DHPP)",
            "start_weeks": 6, "series_interval_weeks": 3,
            "series_until_weeks": 16,
            "first_booster_months": 12, "booster_months": 36,
        },
        {
            "key": "rabies", "core": True,
            "name_en": "Rabies", "name_tr": "Kuduz",
            "start_weeks": 12, "series_interval_weeks": None,
            "series_until_weeks": None,
            "first_booster_months": 12, "booster_months": 12,
        },
        {
            "key": "leptospirosis", "core": False,
            "name_en": "Leptospirosis", "name_tr": "Leptospiroz",
            "start_weeks": 12, "series_interval_weeks": 4,
            "series_until_weeks": 16,
            "first_booster_months": 12, "booster_months": 12,
        },
        {
            "key": "bordetella", "core": False,
            "name_en": "Bordetella (kennel cough)", "name_tr": "Bordetella (kennel öksürüğü)",
            "start_weeks": 8, "series_interval_weeks": None,
            "series_until_weeks": None,
            "first_booster_months": 12, "booster_months": 12,
        },
    ],
    "cat": [
        {
            "key": "fvrcp", "core": True,
            "name_en": "FVRCP (rhinotracheitis, calicivirus, panleukopenia)",
            "name_tr": "Karma (FVRCP)",
            "start_weeks": 6, "series_interval_weeks": 3,
            "series_until_weeks": 16,
            "first_booster_months": 12, "booster_months": 36,
        },
        {
            "key": "rabies", "core": True,
            "name_en": "Rabies", "name_tr": "Kuduz",
            "start_weeks": 12, "series_interval_weeks": None,
            "series_until_weeks": None,
            "first_booster_months": 12, "booster_months": 12,
        },
        {
            "key": "felv", "core": False,
            "name_en": "Feline leukaemia (FeLV)", "name_tr": "Feline lösemi (FeLV)",
            "start_weeks": 8, "series_interval_weeks": 4,
            "series_until_weeks": 12,
            "first_booster_months": 12, "booster_months": 12,
        },
    ],
}


def schedule_for(species: str) -> List[dict]:
    return SCHEDULES.get(species, SCHEDULES["dog"])


def find(species: str, key: str) -> Optional[dict]:
    return next((v for v in schedule_for(species) if v["key"] == key), None)


def _add_months(start: date, months: int) -> date:
    """Same day, n months later, clamped to the end of a short month."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or
              year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30,
              31][month - 1])
    return date(year, month, day)


def _series_complete(rule: dict, doses: List[VaccineRecord], pet: Pet) -> bool:
    """Whether the initial course looks finished.

    Two ways to be done: the last dose fell after the age the series runs to,
    or there is no series for this vaccine and one dose has been given.
    """
    if not doses:
        return False
    if rule["series_until_weeks"] is None:
        return True
    if pet.birth_date is None:
        # Without a date of birth, treat two or more doses as a finished course.
        return len(doses) >= 2
    age_at_last = (doses[-1].given_on - pet.birth_date).days / 7
    return age_at_last >= rule["series_until_weeks"]


def next_due(pet: Pet, rule: dict, doses: List[VaccineRecord]) -> tuple:
    """(due date or None, reason in English, reason in Turkish)."""
    today = date.today()

    # A date written on the card by the vet beats any general rule.
    explicit = [d for d in doses if d.next_due_on]
    if explicit:
        stated = max(d.next_due_on for d in explicit)
        return stated, "date given by the vet", "veteriner tarafından yazılan tarih"

    if not doses:
        if pet.birth_date is None:
            return None, "no doses recorded and no date of birth", \
                   "kayıtlı doz yok ve doğum tarihi girilmemiş"
        first = pet.birth_date + timedelta(weeks=rule["start_weeks"])
        return (max(first, today) if first < today else first,
                f"first dose is normally given at {rule['start_weeks']} weeks",
                f"ilk doz normalde {rule['start_weeks']}. haftada yapılır")

    last = doses[-1].given_on

    if not _series_complete(rule, doses, pet) and rule["series_interval_weeks"]:
        weeks = rule["series_interval_weeks"]
        return (last + timedelta(weeks=weeks),
                f"initial course continues every {weeks} weeks until "
                f"{rule['series_until_weeks']} weeks of age",
                f"ilk seri {rule['series_until_weeks']}. haftaya kadar "
                f"{weeks} haftada bir sürer")

    if len(doses) == 1 or (rule["series_until_weeks"] and
                           not any(d for d in doses[:-1])):
        months = rule["first_booster_months"]
        return (_add_months(last, months),
                f"first booster {months} months after the course",
                f"ilk rapel seriden {months} ay sonra")

    months = rule["booster_months"]
    return (_add_months(last, months),
            f"routine booster every {months} months",
            f"rutin rapel {months} ayda bir")


def status_for(due_on: Optional[date]) -> tuple:
    """(status, days until — negative when overdue)."""
    if due_on is None:
        return "unknown", None
    days = (due_on - date.today()).days
    if days < 0:
        return "overdue", days
    if days <= DUE_SOON_DAYS:
        return "due_soon", days
    return "scheduled", days


def due_list(pet: Pet, include_optional: bool = True) -> List[VaccineDue]:
    """Every vaccine for this species, with its next date. Most urgent first."""
    records = pets_db.vaccines(pet.id)
    out: List[VaccineDue] = []

    for rule in schedule_for(pet.species):
        if not include_optional and not rule["core"]:
            continue

        doses = [r for r in records if r.vaccine_key == rule["key"]]
        doses.sort(key=lambda r: r.given_on)

        due_on, reason_en, reason_tr = next_due(pet, rule, doses)
        status, days = status_for(due_on)

        out.append(VaccineDue(
            key=rule["key"],
            name_en=rule["name_en"],
            name_tr=rule["name_tr"],
            core=rule["core"],
            doses_given=len(doses),
            last_given=doses[-1].given_on if doses else None,
            due_on=due_on,
            status=status,
            days_until=days,
            reason_en=reason_en,
            reason_tr=reason_tr,
        ))

    order = {"overdue": 0, "due_soon": 1, "scheduled": 2, "unknown": 3}
    out.sort(key=lambda d: (order[d.status], d.days_until
                            if d.days_until is not None else 9999))
    return out


def next_appointment(pet: Pet) -> Optional[VaccineDue]:
    """The single most pressing item, for the reminder line."""
    items = [d for d in due_list(pet) if d.status in ("overdue", "due_soon")]
    return items[0] if items else None
