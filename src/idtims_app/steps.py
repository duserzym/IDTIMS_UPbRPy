"""The eight workflow steps of docs/APP_SPEC.md section 3, as data rows.

Steps unlock in order: a step is available once every step before it is
complete (see `services.Session.unlocked`). Steps 1 to 7 are built; Export
is a placeholder.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowStep:
    """One row of the workflow rail."""
    key: str
    title: str
    summary: str
    hint: str
    icon: str
    built: bool = False


STEPS: tuple[WorkflowStep, ...] = (
    WorkflowStep(
        "import", "Import fractions",
        "Open contract or legacy fraction CSVs, or type and paste a new table.",
        "Files are merged by Fraction ID. The linked-error check runs on import; its failures "
        "are marked in the table and listed in the inspector with the allowed interval.",
        "import", built=True),
    WorkflowStep(
        "tracer", "Tracer and weights",
        "Sample and spike weights, tracer, type and collector per fraction.",
        "Inspect the tracer composition and confirm database proposals here. Fill down with Ctrl+D.",
        "concentration", built=True),
    WorkflowStep(
        "fractionation", "Fractionation",
        "Pb fractionation per collector (535) or from 202/205 (2535); U from 233/235.",
        "Values in %/amu with absolute 1σ.", "normalization", built=True),
    WorkflowStep(
        "blanks", "Blanks and common Pb",
        "Pb and U blank, blank composition and initial Pb.",
        "Stacey-Kramers at an estimated age, or user ratios.", "baseline", built=True),
    WorkflowStep(
        "thorium", "Th correction",
        "None, D(Th/U) or Th/U of the magma.",
        "The decay constants in use, λ230 included, are shown.", "downhole", built=True),
    WorkflowStep(
        "reduce", "Reduce",
        "Run the reduction and see per-fraction status.",
        "Strict covariance by default; diagnostic mode is an explicit choice.", "session",
        built=True),
    WorkflowStep(
        "review", "Review",
        "Dates, concordia and weighted means with fractions on and off.",
        "206Pb/238U is the default date (Th-corrected when a Th correction is set). Ctrl-click "
        "(Cmd-click) an ellipse or press E to switch the selected fraction on or off.", "ratios",
        built=True),
    WorkflowStep(
        "export", "Export",
        "BSU data table, full CSV, contract CSV and project file.",
        "Footnotes follow the settings in use.", "export"),
)
