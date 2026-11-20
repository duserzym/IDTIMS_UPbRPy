"""Temporary layout stress data; repeated rows are not a scientific sample."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def long_fraction_fixture(destination):
    with (ROOT / "tests/data/synthetic_template_2535.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    with Path(destination).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for index in range(40):
            row = dict(rows[index % len(rows)])
            row["Grain ID"] = f"SYN-{index // 6 + 1}_zircon_z{index + 1}a_long-label"
            writer.writerow(row)
    return Path(destination)
