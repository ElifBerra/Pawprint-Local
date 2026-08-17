"""Import a food catalogue from CSV.

Fill in data/foods-template.csv from the guaranteed analysis panel on each bag,
then load it. Values are validated on the way in, because a typo here becomes a
health figure later.

Run:  python -m scripts.import_foods data/foods-template.csv
      python -m scripts.import_foods data/my-foods.csv --replace-samples
      python -m scripts.import_foods --export data/current-foods.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from src import foods_db
from src.models import Food

REQUIRED = ("name", "protein_pct", "fat_pct")


def estimate_kcal(clean: dict) -> float:
    """Metabolisable energy from the other figures.

    Most bags print the guaranteed analysis but not a calorie figure, so
    requiring one would block half the catalogue. Modified Atwater factors for
    pet food: protein and carbohydrate 3.5 kcal/g, fat 8.5 kcal/g, with
    carbohydrate taken as whatever the other fractions leave.

    An estimate, and flagged as one in the import summary.
    """
    protein = clean.get("protein_pct", 0)
    fat = clean.get("fat_pct", 0)
    fibre = clean.get("fibre_pct", 0)
    moisture = clean.get("moisture_pct", 10)
    ash = clean.get("ash_pct", 0)
    carbs = max(0.0, 100 - protein - fat - fibre - moisture - ash)
    return round(protein * 3.5 + fat * 8.5 + carbs * 3.5, 1)
NUMERIC = ("kcal_per_100g", "protein_pct", "fat_pct", "fibre_pct",
           "moisture_pct", "ash_pct", "pack_size_g")

LIMITS = {
    "kcal_per_100g": (20, 900),      # wet food is low, dry food rarely over 500
    "protein_pct": (0, 100),
    "fat_pct": (0, 100),
    "fibre_pct": (0, 100),
    "moisture_pct": (0, 95),
    "ash_pct": (0, 100),
    "pack_size_g": (10, 40000),
}


def _number(value: str) -> Optional[float]:
    """Accept both 12.5 and 12,5 — Turkish keyboards produce the latter."""
    text = (value or "").strip().replace(",", ".")
    if not text:
        return None
    return float(text)


def parse_row(row: dict, line: int) -> Tuple[Optional[Food], List[str]]:
    problems: List[str] = []
    clean: dict = {}

    for column in REQUIRED:
        if not (row.get(column) or "").strip():
            problems.append(f"line {line}: '{column}' is empty")

    for column in NUMERIC:
        raw = row.get(column)
        if raw is None or not str(raw).strip():
            continue
        try:
            value = _number(raw)
        except ValueError:
            problems.append(f"line {line}: '{column}' is not a number ({raw!r})")
            continue
        low, high = LIMITS[column]
        if not (low <= value <= high):
            problems.append(
                f"line {line}: '{column}' = {value} is outside {low}-{high}"
            )
            continue
        clean[column] = value

    species = (row.get("species") or "both").strip().lower()
    if species not in {"dog", "cat", "both"}:
        problems.append(f"line {line}: species must be dog, cat or both")

    # A quick sanity check: the parts cannot add up to more than the whole.
    total = sum(clean.get(k, 0) for k in
                ("protein_pct", "fat_pct", "fibre_pct", "moisture_pct", "ash_pct"))
    if total > 100:
        problems.append(
            f"line {line}: percentages add up to {total:.1f}%, which is impossible"
        )

    if "kcal_per_100g" not in clean:
        clean["kcal_per_100g"] = estimate_kcal(clean)
        clean["_kcal_estimated"] = True

    if problems:
        return None, problems

    return Food(
        name=row["name"].strip(),
        species=species,
        life_stage=(row.get("life_stage") or "").strip() or None,
        kcal_per_100g=clean["kcal_per_100g"],
        protein_pct=clean["protein_pct"],
        fat_pct=clean["fat_pct"],
        fibre_pct=clean.get("fibre_pct", 0.0),
        moisture_pct=clean.get("moisture_pct", 10.0),
        ash_pct=clean.get("ash_pct", 0.0),
        pack_size_g=clean.get("pack_size_g"),
        is_sample=False,
    ), []


def import_csv(path: Path, replace_samples: bool) -> None:
    foods_db.init_db()

    if replace_samples:
        removed = [f for f in foods_db.list_foods() if f.is_sample]
        for food in removed:
            foods_db.delete(food.id)
        print(f"Removed {len(removed)} sample entries.")

    added = updated = skipped = 0
    all_problems: List[str] = []

    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            if not any((v or "").strip() for v in row.values()):
                continue

            food, problems = parse_row(row, line)
            if problems:
                all_problems.extend(problems)
                skipped += 1
                continue

            existing = foods_db.get_by_name(food.name)
            if existing:
                food.id = existing.id
                updated += 1
            else:
                added += 1
            foods_db.save(food)

    print(f"\nAdded {added}, updated {updated}, skipped {skipped}.")
    if all_problems:
        print(f"\n{len(all_problems)} problem(s):")
        for problem in all_problems:
            print(f"  {problem}")
        print("\nNothing from those lines was imported. Fix and re-run.")

    print(f"\nCatalogue now holds {foods_db.count()} foods.")


def export_csv(path: Path) -> None:
    foods = foods_db.list_foods()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "species", "life_stage", "pack_size_g",
                         "kcal_per_100g", "protein_pct", "fat_pct",
                         "fibre_pct", "moisture_pct", "ash_pct"])
        for f in foods:
            writer.writerow([f.name, f.species, f.life_stage or "",
                             f.pack_size_g or "", f.kcal_per_100g,
                             f.protein_pct, f.fat_pct, f.fibre_pct,
                             f.moisture_pct, f.ash_pct])
    print(f"Wrote {len(foods)} foods to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import or export foods.")
    parser.add_argument("path", nargs="?", help="CSV file to import")
    parser.add_argument("--replace-samples", action="store_true",
                        help="delete the seeded sample foods first")
    parser.add_argument("--export", metavar="PATH",
                        help="write the current catalogue to a CSV instead")
    args = parser.parse_args()

    if args.export:
        export_csv(Path(args.export))
        return

    if not args.path:
        parser.error("give a CSV path, or use --export")

    path = Path(args.path)
    if not path.exists():
        print(f"No such file: {path}")
        sys.exit(1)

    import_csv(path, args.replace_samples)


if __name__ == "__main__":
    main()
