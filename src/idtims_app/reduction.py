"""Qt-free per-fraction reduction for the Reduce step.

`prepare(table, settings, strict, quality)` snapshots everything a run needs
on the GUI thread (a copy of the reducible rows, the column mapping, each
fraction's `covariance_overrides`, the `load_grains` arguments and the reason
each other fraction is left out). `ReductionJob.run()` is then safe to call on
a worker thread: it reduces ONE FRACTION PER `load_grains` CALL, so one bad
fraction never stops the others and each fraction gets its own covariance
overrides. `load_grains` already reduces row by row, so the numbers equal
those of one call over the whole frame (tests/test_app_reduction.py checks
this bit for bit).

Strict covariance is the default. Diagnostic mode (`strict=False`) is passed
through unchanged; a fraction reduced with a substituted covariance is marked
`status == "diagnostic"`. Nothing switches modes on its own.
"""
from __future__ import annotations

import copy
import re
import warnings
from dataclasses import dataclass, field

from IDTIMS_UPbRPy import UPbR
from IDTIMS_UPbRPy.fractions import BLOCKING
from IDTIMS_UPbRPy.quality import DataQualityError

REDUCED, DIAGNOSTIC, NOT_REDUCED = "reduced", "diagnostic", "not_reduced"

DIAGNOSTIC_HINT = ("The project uses strict covariance. Diagnostic mode (on the Reduce step) "
                   "substitutes zero for impossible covariances so the fraction can be reduced, "
                   "but its uncertainties are then not certified. It is a per-project choice; "
                   "nothing is switched automatically.")

# Engine input names, for readable reasons.
_VARIABLES = {
    "Pb_R65m": "measured 206Pb/205Pb", "Pb_R46m": "measured 204Pb/206Pb",
    "Pb_R76m": "measured 207Pb/206Pb", "Pb_R85m": "measured 208Pb/205Pb",
    "Pb_R65t": "tracer 206Pb/205Pb", "Pb_R45t": "tracer 204Pb/205Pb",
    "Pb_R76t": "tracer 207Pb/206Pb", "Pb_R85t": "tracer 208Pb/205Pb",
    "U_R85m": "measured 238U/235U", "U_R35m": "measured 233U/235U",
    "U_R85t": "tracer 238U/235U", "U_R35t": "tracer 233U/235U",
    "R64b": "blank 206Pb/204Pb", "R76b": "blank 207Pb/206Pb", "R86b": "blank 208Pb/206Pb",
    "R64c": "initial 206Pb/204Pb", "R76c": "initial 207Pb/206Pb", "FPb": "FPb",
}


@dataclass
class FractionResult:
    """Outcome for one fraction: status, reason, the grain when reduced."""
    fraction_id: str
    status: str
    reason: str = ""
    hint: str = ""
    grain: object = None
    quality: list = field(default_factory=list)
    """Readable reasons of failed linked-error checks (import check), may be empty."""
    substitutions: list = field(default_factory=list)
    """Diagnostic-mode messages from grain.uncertainty_assumptions."""

    @property
    def reduced(self):
        return self.status in (REDUCED, DIAGNOSTIC)

    @property
    def status_text(self):
        return {REDUCED: "Reduced", DIAGNOSTIC: "Reduced, diagnostic",
                NOT_REDUCED: "Not reduced"}[self.status]


@dataclass
class ReductionRun:
    """All fractions of one run, in table order."""
    results: list
    strict: bool
    revision: int
    settings: dict
    th_kind: str | None = None

    @property
    def grains(self):
        return [r.grain for r in self.results if r.reduced]

    def result(self, fraction_id):
        for r in self.results:
            if r.fraction_id == fraction_id:
                return r
        return None

    def counts(self):
        out = {REDUCED: 0, DIAGNOSTIC: 0, NOT_REDUCED: 0}
        for r in self.results:
            out[r.status] += 1
        return out


def readable_names(text):
    """Replace engine input names (Pb_R65m, R64b, ...) in a message by readable ones."""
    return re.sub(r"\b(Pb_R\d\d[mt]|U_R\d\d[mt]|R\d\d[bc]|FPb)\b",
                  lambda m: _VARIABLES.get(m.group(1), m.group(1)), text)


def readable_reason(exc):
    """A short, readable reason for a failed `load_grains` call."""
    if isinstance(exc, DataQualityError):
        failed = [c["identity"] for c in exc.checks if not c["passed"]]
        return ("Impossible covariance in the measured errors: the linked-error check failed for "
                + "; ".join(failed) + ".")
    text = str(exc)
    match = re.search(r"impossible covariance for (\w+), (\w+)", text)
    if match:
        a, b = (_VARIABLES.get(n, n) for n in match.groups())
        tracer = " (tracer calibration uncertainties)" if "tracer" in a and "tracer" in b else ""
        return (f"Impossible covariance between {a} and {b}{tracer}: the derived covariance "
                "exceeds the product of their uncertainties.")
    return text


def _is_covariance_failure(exc):
    return isinstance(exc, DataQualityError) or "impossible covariance" in str(exc)


@dataclass
class ReductionJob:
    """A snapshot of one run; `run()` touches nothing outside it."""
    order: list
    data: object
    columns: dict
    overrides: dict
    args: tuple
    kwargs: dict
    excluded: dict
    quality: dict
    revision: int
    settings: dict
    th_kind: str | None

    def run(self, progress=None):
        """Reduce each fraction in its own `load_grains` call; returns a ReductionRun."""
        strict = self.kwargs["strict_covariance"]
        reduced = {}
        ids = [str(f) for f in self.data["Fraction ID"]]
        for index, fid in enumerate(ids):
            if progress is not None:
                progress(f"{fid} ({index + 1} of {len(ids)})")
            row = self.data.iloc[[index]].reset_index(drop=True)
            quality = self.quality.get(fid, [])
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    grain = UPbR.load_grains(row, *self.args, **self.columns,
                                             covariance_overrides=self.overrides.get(fid) or None,
                                             **self.kwargs)[0]
            except Exception as exc:  # noqa: BLE001 - every failure is reported per fraction
                hint = DIAGNOSTIC_HINT if strict and _is_covariance_failure(exc) else ""
                reduced[fid] = FractionResult(fid, NOT_REDUCED, readable_reason(exc), hint,
                                              quality=quality)
                continue
            substitutions = [readable_names(n) for n in getattr(grain, "uncertainty_assumptions", [])
                             if "diagnostic approximation" in n]
            substituted = not strict and (substitutions or grain.data_quality_passed is False)
            if not strict and grain.data_quality_passed is False and not substitutions:
                substitutions = ["The linked-error check failed; the measured errors were used "
                                 "as given (diagnostic mode)."]
            reduced[fid] = FractionResult(fid, DIAGNOSTIC if substituted else REDUCED, grain=grain,
                                          quality=quality, substitutions=substitutions)
        results = []
        for fid in self.order:
            if fid in reduced:
                results.append(reduced[fid])
            else:
                results.append(FractionResult(fid, NOT_REDUCED, self.excluded.get(fid, ""),
                                              quality=self.quality.get(fid, [])))
        return ReductionRun(results, strict, self.revision, self.settings, self.th_kind)


def exclusion_reason(table, fid):
    """Why a fraction is not passed to `load_grains` (blocking issues or missing oxide)."""
    issues = table.issues(fid)
    blocking = [i.message for i in issues if i.kind in BLOCKING]
    if blocking:
        return " ".join(blocking)
    oxide = [i.message for i in issues if i.kind == "missing_oxide"]
    if oxide:
        return ("Not reduced until the U oxide value is entered or 'no oxide correction applies' "
                "is confirmed. " + " ".join(oxide))
    return "Not reducible."


def prepare(table, settings, strict, quality=None, revision=0):
    """Snapshot a run on the calling thread. Raises SettingsError for invalid settings."""
    settings = copy.deepcopy(settings)
    settings.strict_covariance = bool(strict)
    args, kwargs = settings.load_grains_arguments()
    data, columns = table.load_grains_frame(require_oxide=True)
    if table.database_spikes_enabled and "Spike Solution" in data.columns:
        kwargs["spike_from"] = "Spike Solution"
    ids = [str(f) for f in data["Fraction ID"]]
    overrides = {fid: dict(table.covariance_overrides(fid)) for fid in ids}
    order = table.fraction_ids
    excluded = {fid: exclusion_reason(table, fid) for fid in order if fid not in ids}
    return ReductionJob(order=order, data=data.copy(deep=True), columns=dict(columns),
                        overrides=overrides, args=copy.deepcopy(args), kwargs=dict(kwargs),
                        excluded=excluded, quality=dict(quality or {}), revision=revision,
                        settings=settings.to_dict(), th_kind=settings.th_correction.kind)
