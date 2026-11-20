"""Qt-free state of one reduction document: fractions, settings and step progress.

`Session` owns the `FractionTable` being edited, the `ReductionSettings`, the
file names it came from, which workflow steps are complete, the project's
covariance mode (strict by default) and the last reduction (`reduction`, a
`reduction.ReductionRun`). Windows and widgets call it and redraw; nothing
here imports Qt, so the logic is tested without a display. `revision` grows
with every change to the table, the settings or the mode; a reduction made at
an older revision is out of date and no longer completes the Reduce step.

Opening more files merges them with the current table by Fraction ID (the
current table is passed to `read_fractions` first, as an in-memory contract
CSV), so a conflict between an edited cell and a file is reported like a
conflict between two files.
"""
from __future__ import annotations

import io
import json
import math
import os
import hashlib
import uuid
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from IDTIMS_UPbRPy.fractions import (CONTRACT, ERROR, IDENTITY_COLUMNS, MEAN, NUMERIC_COLUMNS,
                                     CHEMISTRY_COLUMNS,
                                     OXIDE, OXIDE_FORMULA, MEAN_STATISTIC_COLUMNS,
                                     PB_OPTIONAL_RATIOS, PB_RATIOS, PB_RATIOS_2535,
                                     RHO_PREFIX, U_RATIOS, FractionFileError, FractionTable,
                                     read_fractions, write_fractions)
from IDTIMS_UPbRPy.quality import check_measurement_quality, check_ratio_errors
from IDTIMS_UPbRPy.settings import ReductionSettings
from IDTIMS_UPbRPy.spikes import SPIKES
from IDTIMS_UPbRPy.UPbR import load_spike_data
from IDTIMS_UPbRPy.tracer import complete_tracer, TracerCompositionError
from IDTIMS_UPbRPy.utils import calc_FPb_2535

from idtims_app import reduction as reduction_module
from idtims_app.steps import STEPS

TRACER_VERSIONS = sorted({v for versions in SPIKES.values() for v in versions})
TRACER_SETUP_COLUMNS = ["Sample Weight (mg)", "Spike Weight (g)", "Spike", "Spike Type",
                        "Collector"]

IDENTITY_SHOWN = IDENTITY_COLUMNS[1:IDENTITY_COLUMNS.index("Fraction UID")]
SETUP_SHOWN = ["Sample Weight (mg)", "Spike Weight (g)", "Spike Type", "Spike", "Collector",
               "Pb Collector Detail", "Pb Method", "U Method"]
PROVENANCE_SHOWN = [OXIDE, OXIDE_FORMULA, *MEAN_STATISTIC_COLUMNS]
RATIOS_SHOWN = [r + s for r in PB_RATIOS + PB_RATIOS_2535 + U_RATIOS for s in (MEAN, ERROR)]
OPTIONAL_RATIO_COLUMNS = [r + s for r in PB_OPTIONAL_RATIOS for s in (MEAN, ERROR)]
NEEDS_CONFIRMATION = {"unconfirmed_spike_type", "unconfirmed_database_spike", "missing_oxide"}

# Linked-error identities checked on import, in contract names:
# (x, u, v, relationship, label, (x, u, v) short names). The v ratio may be
# given in either orientation; the relative error is the same to first order.
_TRIPLETS = (
    ("207Pb/205Pb", "206Pb/205Pb", ("207Pb/206Pb", "206Pb/207Pb"), "product",
     "207/205 = (206/205)*(207/206)"),
    ("204Pb/205Pb", "206Pb/205Pb", ("204Pb/206Pb", "206Pb/204Pb"), "product",
     "204/205 = (206/205)*(204/206)"),
    ("238U/233U", "238U/235U", ("233U/235U",), "quotient",
     "238/233 = (238/235)/(233/235)"),
)


def is_numeric_column(column):
    """True for columns holding numbers (ratios, weights, oxide, correlations)."""
    return column in NUMERIC_COLUMNS or (column.startswith(RHO_PREFIX) and "|" in column)


def is_ratio_column(column):
    """True for measured-ratio and correlation columns (editable in manual mode only)."""
    return (column in RATIOS_SHOWN or column in OPTIONAL_RATIO_COLUMNS
            or (column.startswith(RHO_PREFIX) and "|" in column))


def _empty(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


def _normalise_spike_type(text):
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number in (535, 2535) else text


@dataclass
class QualityFailure:
    """One failed linked-error check of one fraction, with a readable reason."""
    fraction_id: str
    identity: str
    reason: str
    columns: tuple


@dataclass
class OpenResult:
    """Outcome of opening files: `error` is a message for the page, or None."""
    error: str | None = None
    added: list = field(default_factory=list)
    merged: list = field(default_factory=list)


@dataclass
class PasteResult:
    """Outcome of a paste: cells changed, rows added and messages for the page."""
    changed: int = 0
    added_rows: int = 0
    errors: list = field(default_factory=list)


class Session:
    """One document: the fraction table, the settings and the workflow progress."""

    def __init__(self):
        self.table: FractionTable | None = None
        self.settings = ReductionSettings()
        self.sources: list[str] = []
        self.source_records = []
        self.project_path = None
        self.origin = None
        self.engine_note = ""
        self.autosave_id = uuid.uuid4().hex
        self._saved_project_fingerprint = None
        self.export_saved_revision = None
        self.ratios_editable = False
        self.manual = False
        self.dirty = False
        self.saved_path: str | None = None
        self.revision = 0
        self._quality_cache = None
        # Covariance mode is a per-project choice, strict by default; it is
        # held here (not taken from settings files) and saved with the project.
        self.strict_covariance = True
        self.settings_path: str | None = None
        self.reduction = None
        # Review (step 7): fractions switched off, kept across re-reductions for
        # fractions still present; the weighted-mean date kind and the concordia
        # view. Switching fractions does not change `revision`: it changes no
        # reduced number.
        self.excluded_fractions: set[str] = set()
        self.review_kind: str | None = None
        self.review_diagram = "wetherill"
        self.review_th_ratios: bool | None = None

    # -- opening and creating ----------------------------------------------
    @property
    def has_table(self):
        return self.table is not None

    def open_files(self, paths):
        """Read contract or legacy CSVs and merge them into the current table.

        Content decides how each file is read. On any read or merge error the
        current table is left unchanged and the message is returned.
        """
        paths = [os.fspath(p) for p in paths]
        if not paths:
            return OpenResult(error="No file given.")
        inputs = []
        previous = self.table
        if previous is not None:
            frame = self._without_empty_rows(previous.frame)
            if len(frame):
                buffer = io.StringIO()
                write_fractions(frame, buffer)
                buffer.seek(0)
                buffer.name = "the current table"
                inputs.append(buffer)
        try:
            table = read_fractions(*inputs, *paths)
        except FractionFileError as exc:
            return OpenResult(error=str(exc))
        except OSError as exc:
            return OpenResult(error=f"{exc.filename or paths[0]}: {exc.strerror or exc}")
        records = [{"name": Path(p).name, "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}
                   for p in paths]
        for record in records:
            if record not in self.source_records:
                self.source_records.append(record)
        old_ids = set(previous.fraction_ids) if previous is not None else set()
        if previous is not None:
            table.no_oxide_confirmed = {f for f in previous.no_oxide_confirmed
                                        if f in table.fraction_ids}
            table.database_spike_confirmations = dict(previous.database_spike_confirmations)
        else:
            self.ratios_editable = False
            self.manual = False
        self.table = table
        self._ensure_columns()
        for path in paths:
            name = os.path.basename(path)
            if name not in self.sources:
                self.sources.append(name)
        added = [f for f in table.fraction_ids if f not in old_ids]
        merged = [f for f in table.fraction_ids if f in old_ids]
        self._changed(dirty=previous is not None)
        return OpenResult(added=added, merged=merged)

    def new_table(self, rows=5):
        """Start an empty table with the contract columns, for typing and pasting."""
        columns = ["Contract"] + IDENTITY_SHOWN + SETUP_SHOWN + PROVENANCE_SHOWN + RATIOS_SHOWN
        frame = pd.DataFrame({c: pd.Series(dtype=float if is_numeric_column(c) else object)
                              for c in columns})
        self.table = FractionTable(frame)
        self.sources = []
        self.source_records = []
        self.ratios_editable = True
        self.manual = True
        self.saved_path = None
        self.add_rows(rows)
        self._changed(dirty=False)

    def _ensure_columns(self):
        """Add every shown contract column the frame lacks, empty."""
        frame = self.table.frame
        for column in IDENTITY_SHOWN + SETUP_SHOWN + PROVENANCE_SHOWN + RATIOS_SHOWN:
            if column not in frame.columns:
                if is_numeric_column(column):
                    frame[column] = np.nan
                else:
                    frame[column] = pd.Series([None] * len(frame), index=frame.index,
                                              dtype=object)
        self.table.enable_database_spikes(self.settings.spike_version)

    @staticmethod
    def _without_empty_rows(frame):
        """Rows that carry something besides their Fraction ID."""
        data = frame.drop(columns=[c for c in ("Contract", "Fraction ID") if c in frame.columns])
        keep = data.notna().any(axis=1) if len(data.columns) else pd.Series(False, frame.index)
        return frame[keep].reset_index(drop=True)

    # -- columns and cells ---------------------------------------------------
    def display_columns(self):
        """Columns shown in Import; provenance follows ID to fit at 1280 px."""
        if self.table is None:
            return []
        frame = self.table.frame
        shown = (IDENTITY_SHOWN[:1] + PROVENANCE_SHOWN + IDENTITY_SHOWN[1:]
                 + SETUP_SHOWN + RATIOS_SHOWN)
        shown += [c for c in OPTIONAL_RATIO_COLUMNS if c in frame.columns]
        shown += [c for c in frame.columns if c.startswith(RHO_PREFIX) and "|" in c]
        shown += [c for c in IDENTITY_COLUMNS + CHEMISTRY_COLUMNS if c in frame.columns and c not in shown
                  and c != "Contract"]
        return shown

    def is_editable(self, column):
        """Identity and setup cells are always editable; ratios only in manual mode."""
        if is_ratio_column(column):
            return self.ratios_editable
        return column in IDENTITY_SHOWN or column in SETUP_SHOWN or column in PROVENANCE_SHOWN

    @property
    def row_count(self):
        return 0 if self.table is None else len(self.table.frame)

    def fraction_id(self, row):
        return str(self.table.frame["Fraction ID"].iat[row])

    def row_of(self, fraction_id):
        ids = self.table.fraction_ids
        return ids.index(fraction_id) if fraction_id in ids else -1

    def value(self, row, column):
        """The stored value (float, str or None/NaN) of one cell."""
        frame = self.table.frame
        if column not in frame.columns:
            return None
        return frame[column].iat[row]

    def display_text(self, row, column):
        """Cell text: numbers at full precision (shortest round-trip), empty when missing."""
        value = self.value(row, column)
        if _empty(value):
            return ""
        if isinstance(value, (float, np.floating)):
            return repr(float(value))
        return str(value)

    def set_value(self, row, column, text):
        """Set one cell from text; returns an error message, or None when accepted."""
        text = "" if text is None else str(text).strip()
        table = self.table
        frame = table.frame
        fid = self.fraction_id(row)
        if column == "Fraction ID":
            if not text:
                return "Fraction ID cannot be empty."
            if text == fid:
                return None
            if text in table.fraction_ids:
                return f"Fraction ID {text!r} is already used by another row."
            frame.iat[row, frame.columns.get_loc("Fraction ID")] = text
            if fid in table.inferred_spike_types:
                table.inferred_spike_types[text] = table.inferred_spike_types.pop(fid)
            if fid in table.no_oxide_confirmed:
                table.no_oxide_confirmed.discard(fid)
                table.no_oxide_confirmed.add(text)
            if fid in table.database_spike_confirmations:
                table.database_spike_confirmations[text] = table.database_spike_confirmations.pop(fid)
            self._changed()
            return None
        if column not in frame.columns:
            frame[column] = np.nan if is_numeric_column(column) else None
            if not is_numeric_column(column):
                frame[column] = frame[column].astype(object)
        if is_numeric_column(column):
            if text == "":
                value = np.nan
            else:
                try:
                    value = float(text)
                except ValueError:
                    return f"{fid}, {column}: {text!r} is not a number."
                if not math.isfinite(value):
                    return f"{fid}, {column}: {text!r} is not a finite number."
                if column.startswith(RHO_PREFIX) and abs(value) > 1:
                    return f"{fid}, {column}: a correlation must lie between -1 and 1."
        elif column == "Spike Type":
            if text and fid in table.inferred_spike_types:
                table.confirm_spike_type(fid, text)
                self._changed()
                return None
            value = _normalise_spike_type(text) if text else None
        else:
            value = text or None
        if column in ("Spike Solution", "Spike Version UID", "Spike", "Spike Type",
                      "Fraction UID", "Database Server") \
                and frame.iat[row, frame.columns.get_loc(column)] != value:
            table.database_spike_confirmations.pop(fid, None)
        frame.iat[row, frame.columns.get_loc(column)] = value
        self._changed()
        return None

    def add_rows(self, count=1, ids=None):
        """Append empty rows with unused ids f1, f2, ... (or the given ids)."""
        frame = self.table.frame
        used = set(self.table.fraction_ids)
        new_ids = []
        number = 1
        for index in range(count):
            if ids is not None and index < len(ids):
                new_ids.append(ids[index])
                used.add(ids[index])
                continue
            while f"f{number}" in used:
                number += 1
            new_ids.append(f"f{number}")
            used.add(f"f{number}")
        rows = pd.DataFrame({c: pd.Series([np.nan if is_numeric_column(c) else None] * count,
                                          dtype=float if is_numeric_column(c) else object)
                             for c in frame.columns})
        rows["Contract"] = CONTRACT
        rows["Fraction ID"] = new_ids
        self.table.frame = pd.concat([frame, rows], ignore_index=True) if len(frame) else rows
        for column in self.table.frame.columns:
            if not is_numeric_column(column):
                self.table.frame[column] = self.table.frame[column].astype(object)
        self._changed()
        return new_ids

    def delete_rows(self, rows):
        """Remove rows by position."""
        rows = sorted(set(rows))
        if not rows:
            return
        table = self.table
        ids = [self.fraction_id(r) for r in rows]
        table.frame = table.frame.drop(index=table.frame.index[rows]).reset_index(drop=True)
        for fid in ids:
            table.inferred_spike_types.pop(fid, None)
            table.no_oxide_confirmed.discard(fid)
            table.database_spike_confirmations.pop(fid, None)
        self._changed()

    def _row_is_empty(self, row):
        frame = self.table.frame
        return all(_empty(frame[c].iat[row]) for c in frame.columns
                   if c not in ("Contract", "Fraction ID"))

    def paste(self, row, column_index, text):
        """Paste a tab-separated block starting at a cell.

        A first line naming at least two contract columns is a header: values
        then go to the named columns, and rows whose Fraction ID exists are
        filled in place (new ids take the next empty row, then new rows).
        Without a header, the block fills cells from (row, column_index).
        Rows are added when the block runs past the last row.
        """
        result = PasteResult()
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            return result
        cells = [line.split("\t") for line in lines]
        columns = self.display_columns()
        aliases = {"Grain ID": "Fraction ID"}
        first = [aliases.get(c.strip(), c.strip()) for c in cells[0]]
        header = sum(1 for c in first if c in columns) >= 2
        if header:
            targets = [c if c in columns else None for c in first]
            cells = cells[1:]
            unknown = [c for c, t in zip(first, targets) if t is None and c]
            if unknown:
                result.errors.append("Columns not in the table were skipped: "
                                     + ", ".join(unknown) + ".")
        else:
            width = max(len(line) for line in cells)
            targets = [columns[column_index + j] if column_index + j < len(columns) else None
                       for j in range(width)]
            if None in targets:
                result.errors.append("Cells past the last column were ignored.")
        id_position = targets.index("Fraction ID") if header and "Fraction ID" in targets else None
        rows, claimed = [], set()
        next_row = max(row, 0)
        for line in cells:
            fid = line[id_position].strip() if id_position is not None and \
                id_position < len(line) else ""
            if fid and fid in self.table.fraction_ids:
                rows.append(self.row_of(fid))
                claimed.add(rows[-1])
                continue
            # A new id never overwrites another fraction: take the next empty row.
            while next_row < self.row_count and (next_row in claimed or (
                    fid and not self._row_is_empty(next_row))):
                next_row += 1
            if next_row >= self.row_count:
                self.add_rows(1)
                result.added_rows += 1
            rows.append(next_row)
            claimed.add(next_row)
            next_row += 1
        refused = set()
        for target_row, line in zip(rows, cells):
            for j, raw in enumerate(line):
                column = targets[j] if j < len(targets) else None
                if column is None:
                    continue
                if not self.is_editable(column):
                    if column not in refused:
                        refused.add(column)
                        result.errors.append(f"{column} is read-only here; turn on "
                                             "'Edit ratios' to paste measured ratios.")
                    continue
                if column != "Fraction ID" and raw.strip() == "" and header:
                    continue
                error = self.set_value(target_row, column, raw)
                if error:
                    result.errors.append(error)
                else:
                    result.changed += 1
        return result

    # -- issues and the linked-error check ---------------------------------
    def issues(self, fraction_id=None):
        """`FractionIssue`s from the table, for one fraction or all."""
        if self.table is None:
            return []
        self.table.database_spike_version = self.settings.spike_version
        return self.table.issues(fraction_id)

    def quality_failures(self, fraction_id=None):
        """Failed linked-error checks, for one fraction or all (in table order)."""
        failures = self._quality()
        if fraction_id is not None:
            return failures.get(fraction_id, [])
        return [f for fid in self.table.fraction_ids for f in failures.get(fid, [])]

    def _quality(self):
        if self._quality_cache is not None:
            return self._quality_cache
        result = {}
        if self.table is not None:
            frame = self.table.frame
            complete_rows, partial_rows = [], []
            for row in range(len(frame)):
                values = self._triplet_errors(row)
                if all(v is not None for v in values):
                    complete_rows.append((row, values))
                else:
                    partial_rows.append((row, values))
            if complete_rows:
                self._check_complete(complete_rows, result)
            for row, values in partial_rows:
                fid = self.fraction_id(row)
                for (x, u, v, kind, label), errors in zip(_TRIPLETS, values):
                    if errors is None:
                        continue
                    check = self._safe_check(errors, kind, fid, label)
                    self._record(result, fid, check, errors)
        self._quality_cache = result
        return result

    def _triplet_errors(self, row):
        """Per triplet: ((x, u, v) error columns, (x, u, v) errors) or None if incomplete."""
        out = []
        for x, u, v_options, _kind, _label in _TRIPLETS:
            v = None
            for option in v_options:
                if self._finite(row, option + ERROR):
                    v = option
                    break
            names = (x + ERROR, u + ERROR, v + ERROR if v else None)
            if v is None or not all(self._finite(row, c) for c in names[:2]):
                out.append(None)
            else:
                out.append((names, tuple(float(self.value(row, c)) for c in names)))
        return out

    def _finite(self, row, column):
        value = self.value(row, column) if column in self.table.frame.columns else None
        return isinstance(value, (float, np.floating)) and math.isfinite(value)

    def _check_complete(self, rows, result):
        """Run `check_measurement_quality` on fractions with all three identities."""
        records = []
        for row, values in rows:
            (pb7, pb4, u) = values
            records.append({
                "Fraction ID": self.fraction_id(row),
                "207Pb/205Pb % Standard Error": pb7[1][0],
                "206Pb/205Pb % Standard Error": pb7[1][1],
                "206Pb/207Pb % Standard Error": pb7[1][2],
                "204Pb/205Pb % Standard Error": pb4[1][0],
                "206Pb/204Pb % Standard Error": pb4[1][2],
                "238U/233U % Standard Error": u[1][0],
                "238U/235U % Standard Error": u[1][1],
                "233U/235U % Standard Error": u[1][2],
            })
        try:
            checks = check_measurement_quality(pd.DataFrame(records),
                                               columns={"id": "Fraction ID"})
        except ValueError:
            # A negative or malformed error somewhere: check row by row instead.
            for row, values in rows:
                fid = self.fraction_id(row)
                for (_x, _u, _v, kind, label), errors in zip(_TRIPLETS, values):
                    self._record(result, fid, self._safe_check(errors, kind, fid, label), errors)
            return
        by_fraction = {fid: values for (row, values), fid in
                       zip(rows, [r["Fraction ID"] for r in records])}
        labels = [t[4] for t in _TRIPLETS]
        for check in checks.to_dict("records"):
            fid = str(check["grain"])
            errors = by_fraction[fid][labels.index(check["identity"])]
            self._record(result, fid, check, errors)

    @staticmethod
    def _safe_check(errors, kind, fid, label):
        try:
            return check_ratio_errors(*errors[1], relationship=kind, grain=fid, identity=label)
        except ValueError as exc:
            return {"passed": False, "identity": label, "invalid": str(exc)}

    @staticmethod
    def _record(result, fid, check, errors):
        if check.get("passed"):
            return
        columns, values = errors
        names = [c.replace(ERROR, "") for c in columns]
        label = check["identity"]
        if "invalid" in check:
            reason = f"{label}: {check['invalid']}"
        else:
            rho = check.get("implied_correlation")
            implied = "undefined" if rho is None or (isinstance(rho, float) and math.isnan(rho)) \
                else f"{rho:.4g}"
            reason = (f"{label}: reported errors (1σ %) {names[0]} {values[0]:.6g}, "
                      f"{names[1]} {values[1]:.6g}, {names[2]} {values[2]:.6g}. "
                      f"The {names[0]} error must lie between "
                      f"{check['x_error_lower_pct']:.6g} and {check['x_error_upper_pct']:.6g} % "
                      f"for these to be consistent (implied correlation {implied}).")
        result.setdefault(fid, []).append(QualityFailure(fid, label, reason, tuple(columns)))

    # -- confirmations -------------------------------------------------------
    def confirm_spike_type(self, fraction_id):
        self.table.confirm_spike_type(fraction_id)
        self._changed()

    def confirm_no_oxide(self, fraction_id):
        self.table.confirm_no_oxide_correction(fraction_id)
        self._changed()

    def confirm_database_spike(self, fraction_id):
        self.table.database_spike_version = self.settings.spike_version
        self.table.confirm_database_spike(fraction_id)
        self._changed()

    def confirm_all(self, kind):
        """Accept every open issue of a supported confirmation kind."""
        for issue in self.issues():
            if issue.kind == kind == "unconfirmed_spike_type":
                self.table.confirm_spike_type(issue.fraction_id)
            elif issue.kind == kind == "missing_oxide":
                self.table.confirm_no_oxide_correction(issue.fraction_id)
            elif issue.kind == kind == "unconfirmed_database_spike":
                self.table.confirm_database_spike(issue.fraction_id)
        self._changed()

    # -- progress ------------------------------------------------------------
    def ready_ids(self):
        """Fractions with both blocks, all setup fields and no blocking issue."""
        if self.table is not None:
            self.table.database_spike_version = self.settings.spike_version
        return [] if self.table is None else self.table.reducible_ids()

    def summary(self):
        """Counts for the page header."""
        if self.table is None:
            return dict(fractions=0, ready=0, quality=0, confirm=0, blocking=0)
        issues = self.issues()
        return dict(
            fractions=self.row_count,
            ready=len(self.ready_ids()),
            quality=len({f.fraction_id for f in self.quality_failures()}),
            confirm=len({i.fraction_id for i in issues if i.kind in NEEDS_CONFIRMATION}),
            blocking=len({i.fraction_id for i in issues if i.blocking}))

    def summary_text(self):
        """Shared fraction counts for Issues, status and Review.

        Only a current run supplies reduction counts. Reason groups count
        fractions, even when a fraction has several issues in the same group.
        """
        if not self.has_table:
            return "No fractions loaded"
        text = f"{self.row_count} fractions"
        if not self.reduction_current:
            counts = self.summary()
            parts = []
            for key, label in (("ready", "ready"),
                               ("quality", "failing the linked-error check"),
                               ("confirm", "to confirm")):
                if counts[key]:
                    parts.append(f"{counts[key]} {label}")
            return text + (": " + ", ".join(parts) if parts else "")

        results = self.reduction.results
        reduced = sum(r.reduced for r in results)
        parts = []
        if reduced:
            parts.append(f"{reduced} reduced")
        if self.row_count - reduced:
            parts.append(f"{self.row_count - reduced} not reduced")
        groups = {}
        issue_labels = {
            "missing_block": "with missing or incomplete blocks",
            "incomplete_block": "with missing or incomplete blocks",
            "missing_setup": "with missing setup",
            "invalid_value": "with invalid inputs",
            "unconfirmed_spike_type": "awaiting tracer confirmation",
            "unconfirmed_database_spike": "awaiting database tracer confirmation",
            "database_spike": "with database tracer conflicts",
            "missing_oxide": "awaiting oxide information",
            "oxide_formula": "awaiting oxide information",
        }
        for result in results:
            if result.status == reduction_module.DIAGNOSTIC:
                labels = {"with diagnostic substitution"}
            elif result.reduced:
                continue
            else:
                labels = {issue_labels[i.kind] for i in self.issues(result.fraction_id)
                          if i.kind in issue_labels}
                if not labels:
                    if "linked-error check failed" in result.reason:
                        labels = {"failing the linked-error check"}
                    elif "covariance" in result.reason.lower():
                        labels = {"failing the covariance check"}
                    else:
                        labels = {"with reduction errors"}
            for label in labels:
                groups.setdefault(label, set()).add(result.fraction_id)
        text += (": " + ", ".join(parts) if parts else "")
        if groups:
            text += " (" + ", ".join(f"{len(groups[label])} {label}"
                                     for label in sorted(groups)) + ")"
        return text

    def step_complete(self, index):
        """Whether workflow step `index` (0-based) is complete.

        Import: at least one fraction ready. Tracer: that, and every tracer in
        use has the project-wide table version. Fractionation, Blanks and Th:
        their settings sections have no problems. Reduce: a reduction of the
        current table and settings reduced at least one fraction. Review: that,
        and at least one reduced fraction is switched on. Export completes
        after a table or project has been saved at the current revision.
        """
        if index == 0:
            # Database tracer decisions belong to Tracer, which must be reachable
            # even when every otherwise complete fraction awaits confirmation.
            return self.table is not None and any(
                not any(i.blocking and i.kind not in {"database_spike", "unconfirmed_database_spike"}
                        for i in self.issues(fid)) for fid in self.table.fraction_ids)
        if index == 1:
            return bool(self.ready_ids()) and not self.tracer_problems()
        if index in (2, 3, 4):
            return not self.section_problems(STEPS[index].key)
        if index == 5:
            return self.reduction_current and any(r.reduced for r in self.reduction.results)
        if index == 6:
            return self.reduction_current and bool(self.included_ids())
        if index == 7:
            return self.export_saved_revision == self.revision
        return False

    def unlocked(self, index):
        """A step is available once every earlier step is complete."""
        return all(self.step_complete(i) for i in range(index))

    @property
    def step_count(self):
        return len(STEPS)

    # -- saving --------------------------------------------------------------
    def scientific_project_fingerprint(self):
        from idtims_app.project import scientific_fingerprint
        return scientific_fingerprint(self)

    def has_unsaved_changes(self):
        return self.has_table and self.scientific_project_fingerprint() != self._saved_project_fingerprint

    def mark_project_saved(self):
        self._saved_project_fingerprint = self.scientific_project_fingerprint()

    def save_project(self, path):
        from idtims_app import autosave, branding, project
        old_sidecar = autosave.path_for(self)
        target = Path(path).expanduser()
        if target.suffix.lower() != branding.PROJECT_EXTENSION:
            target = target.with_suffix(branding.PROJECT_EXTENSION)
        written = project.write(project.document(self), target)
        self.project_path = str(written)
        self.mark_project_saved()
        self.export_saved_revision = self.revision
        self.dirty = False
        old_sidecar.unlink(missing_ok=True)
        autosave.path_for(self).unlink(missing_ok=True)
        return written

    def save(self, path):
        """Write the table as a contract CSV."""
        write_fractions(self.table, path)
        self.saved_path = os.fspath(path)
        self.dirty = False

    def _changed(self, dirty=True):
        if self.table is not None:
            self.table.enable_database_spikes(self.settings.spike_version)
        self.revision += 1
        self._quality_cache = None
        if dirty:
            self.dirty = True

    # -- tracer and weights --------------------------------------------------
    def tracer_version(self, name):
        """The tracer table version `load_grains` will use for tracer `name`."""
        if self.settings.spike_version is not None:
            return self.settings.spike_version
        return "v3" if name == "ET2535" else "v1"

    def tracer_file(self, name):
        """Source file name of the tracer table in use, or None when it does not exist."""
        return SPIKES.get(name, {}).get(self.tracer_version(name))

    def tracers_in_use(self):
        """Known tracer names entered in the table, in first-use order."""
        if self.table is None or "Spike" not in self.table.frame.columns:
            return []
        out = []
        for value in self.table.frame["Spike"]:
            if isinstance(value, str) and value in SPIKES and value not in out:
                out.append(value)
        return out

    def tracer_problems(self):
        """Readable problems with the project-wide tracer version for ready fractions."""
        if self.table is None:
            return []
        ready = set(self.ready_ids())
        used = []
        for fid, name in zip(self.table.fraction_ids, self.table.frame["Spike"]):
            if self.table.database_spike_confirmed(fid):
                continue
            if fid in ready and name in SPIKES and name not in used:
                used.append(name)
        out = []
        for name in used:
            if self.tracer_file(name) is None:
                out.append(f"Tracer {name} has no table version {self.tracer_version(name)!r}; "
                           "it has " + ", ".join(sorted(SPIKES[name])) + ". Choose another "
                           "version or 'Default per tracer'.")
        return out

    def tracer_table(self, name, spike_key=None, with_derivations=False, *, with_sources=False):
        """Completed rows; optionally include notes and quantity -> (kind, note)."""
        frame = load_spike_data(name, self.tracer_version(name), spike_key=spike_key)
        numeric = frame.loc[["value", "uncertainty"]].apply(pd.to_numeric, errors="coerce")
        numeric, notes, sources = complete_tracer(
            numeric, spike_key or f"{name} {self.tracer_version(name)}",
            key=spike_key, with_sources=True)
        rows = []
        for column in numeric.columns:
            unit = frame.at["unit", column] if "unit" in frame.index and column in frame.columns else ""
            value = numeric.at["value", column]
            error = numeric.at["uncertainty", column]
            rows.append((column, "" if _empty(unit) else str(unit), float(value),
                         float(error)))
        if with_sources:
            return rows, notes, sources
        return (rows, notes) if with_derivations else rows

    def set_many(self, rows, column, text):
        """Set one column of several rows to the same text; returns error messages."""
        errors = []
        for row in rows:
            error = self.set_value(row, column, text)
            if error:
                errors.append(error)
        return errors

    def fill_down(self, rows, column):
        """Copy the first row's value of `column` to the other rows; returns errors."""
        rows = sorted(set(rows))
        if len(rows) < 2:
            return []
        return self.set_many(rows[1:], column, self.display_text(rows[0], column))

    # -- fractionation -------------------------------------------------------
    def spike_type(self, row):
        """'535', '2535' (entered or inferred) or None."""
        fid = self.fraction_id(row)
        if fid in self.table.inferred_spike_types:
            return self.table.inferred_spike_types[fid]
        value = self.value(row, "Spike Type")
        return None if _empty(value) else str(value)

    def collector_counts(self):
        """{'F': n, 'D': n} for fractions with Spike Type 535."""
        out = {"F": 0, "D": 0}
        if self.table is None:
            return out
        for row in range(self.row_count):
            if self.spike_type(row) == "535" and self.value(row, "Collector") in out:
                out[self.value(row, "Collector")] += 1
        return out

    def fpb_2535(self):
        """Per 2535 fraction: (fid, R25m, R25m 1σ %, R25t, R25t 1σ %, FPb, FPb 1σ, message).

        FPb and its 1σ are per amu (not %), from `utils.calc_FPb_2535` with the
        same inputs `load_grains` uses; missing inputs give None and a message.
        """
        out = []
        if self.table is None:
            return out
        for row in range(self.row_count):
            if self.spike_type(row) != "2535":
                continue
            fid = self.fraction_id(row)
            r25m = self.value(row, "202Pb/205Pb" + MEAN)
            r25m_rel = self.value(row, "202Pb/205Pb" + ERROR)
            name = self.value(row, "Spike")
            r25t = r25t_rel = None
            message = ""
            key = self.value(row, "Spike Solution")
            database_issues = self.table.database_spike_issues(fid)
            if key and any(i.kind == "database_spike" for i in database_issues):
                message = " ".join(i.message for i in database_issues)
            elif name not in SPIKES and not key:
                message = "Enter the tracer (Spike) to compute FPb."
            elif self.tracer_file(name) is None and not key:
                message = f"Tracer {name} has no version {self.tracer_version(name)!r}."
            else:
                try:
                    table = {q: (v, e) for q, _u, v, e in self.tracer_table(name, spike_key=key)}
                except TracerCompositionError as error:
                    message = str(error)
                else:
                    r25t, r25t_rel = table.get("202Pb/205Pb", (math.nan, math.nan))
                    if not (math.isfinite(r25t) and r25t > 0 and math.isfinite(r25t_rel)):
                        message = f"Tracer {name} has no 202Pb/205Pb; 2535 needs a 202-205 double spike."
                        r25t = r25t_rel = None
            if not message and (_empty(r25m) or _empty(r25m_rel) or r25m <= 0 or r25m_rel < 0):
                message = "Measured 202Pb/205Pb is missing."
            fpb = fpb_std = None
            if not message:
                fpb, fpb_std = calc_FPb_2535(r25m, r25m * r25m_rel / 100, r25t,
                                             r25t * r25t_rel / 100)
                fpb, fpb_std = float(fpb), float(fpb_std)
            out.append((fid, None if _empty(r25m) else float(r25m),
                        None if _empty(r25m_rel) else float(r25m_rel), r25t, r25t_rel,
                        fpb, fpb_std, message))
        return out

    # -- reduction settings --------------------------------------------------
    def section_problems(self, key):
        """Settings problems for one step: 'fractionation', 'blanks' or 'thorium'."""
        s = self.settings
        if key == "fractionation":
            return s.fractionation.problems()
        if key == "blanks":
            return s.lab_blanks.problems() + s.common_pb.problems()
        if key == "thorium":
            return s.th_correction.problems()
        return []

    def settings_edited(self):
        """Call after changing `settings` in place; earlier results become out of date."""
        self.revision += 1

    def reset_settings(self, section=None):
        """Restore `ReductionSettings()` defaults: all, or one dataclass section by name."""
        defaults = ReductionSettings()
        if section is None:
            self.settings = defaults
        else:
            setattr(self.settings, section, getattr(defaults, section))
        self.settings_edited()

    def settings_dict(self):
        """`settings.to_dict()` with the project's covariance mode."""
        data = self.settings.to_dict()
        data["strict_covariance"] = self.strict_covariance
        return data

    def save_settings(self, path):
        """Write the settings as JSON (format idtims-reduction-settings)."""
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(self.settings_dict(), stream, indent=2)
            stream.write("\n")
        self.settings_path = os.fspath(path)

    def load_settings(self, path):
        """Read a settings JSON. Returns (error, note); on error nothing changes.

        The file's covariance mode is not applied: the project's mode stays as
        it is, and `note` says so when the file asks for the other mode.
        """
        try:
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
            settings = ReductionSettings.from_dict(data)
        except OSError as exc:
            return f"{path}: {exc.strerror or exc}", None
        except ValueError as exc:  # JSON errors and SettingsError
            return f"{os.path.basename(path)}: {exc}", None
        except TypeError as exc:
            return f"{os.path.basename(path)}: {exc}", None
        note = None
        if settings.strict_covariance != self.strict_covariance:
            wanted = "strict" if settings.strict_covariance else "diagnostic"
            kept = "strict" if self.strict_covariance else "diagnostic"
            note = (f"{os.path.basename(path)} was saved in {wanted} covariance mode. The "
                    f"project's mode stays {kept}; change it on the Reduce step if you mean to.")
        settings.strict_covariance = self.strict_covariance
        self.settings = settings
        self.settings_path = os.fspath(path)
        self.settings_edited()
        return None, note

    # -- reduction -----------------------------------------------------------
    def set_strict_covariance(self, strict):
        strict = bool(strict)
        if strict != self.strict_covariance:
            self.strict_covariance = strict
            self.settings.strict_covariance = strict
            self.revision += 1

    @property
    def reduction_current(self):
        """True when the stored reduction used the current table, settings and mode."""
        return self.reduction is not None and self.reduction.revision == self.revision

    def can_reduce(self):
        """(ok, message): whether Reduce can run now."""
        if self.table is None or not self.ready_ids():
            return False, "No fraction is ready to reduce."
        problems = self.settings.problems() + self.tracer_problems()
        if problems:
            return False, problems[0]
        return True, ""

    def prepare_reduction(self):
        """Snapshot a run (GUI thread); `job.run()` may then go to a worker thread."""
        if self.table is not None:
            self.table.enable_database_spikes(self.settings.spike_version)
        quality = {}
        for failure in self.quality_failures():
            quality.setdefault(failure.fraction_id, []).append(failure.reason)
        return reduction_module.prepare(self.table, self.settings, self.strict_covariance,
                                        quality=quality, revision=self.revision)

    def apply_reduction(self, run):
        """Store a finished run for Review (it may be out of date if edits came in meanwhile).

        Fractions switched off stay off when they are still in the run.
        """
        self.reduction = run
        present = {r.fraction_id for r in run.results}
        self.excluded_fractions &= present

    # -- review ----------------------------------------------------------------
    @property
    def th_correction_applied(self):
        return self.reduction is not None and self.reduction.th_kind is not None

    def is_included(self, fraction_id):
        return str(fraction_id) not in self.excluded_fractions

    def set_included(self, fraction_id, included):
        """Switch one fraction on or off; returns whether anything changed."""
        fid = str(fraction_id)
        if included == (fid not in self.excluded_fractions):
            return False
        if included:
            self.excluded_fractions.discard(fid)
        else:
            self.excluded_fractions.add(fid)
        return True

    def toggle_included(self, fraction_id):
        self.set_included(fraction_id, not self.is_included(fraction_id))

    def included_ids(self):
        """Reduced fractions of the last run that are switched on, in table order."""
        if self.reduction is None:
            return []
        return [r.fraction_id for r in self.reduction.results
                if r.reduced and r.fraction_id not in self.excluded_fractions]

    def review_date_kind(self):
        """The weighted-mean date: the chosen one, else Th-corrected 206/238 with a Th
        correction, else 206/238 (UX rule 9)."""
        from idtims_app.review import date_kinds, default_kind

        th = self.th_correction_applied
        if self.review_kind in date_kinds(th):
            return self.review_kind
        return default_kind(th)

    def review_th_shown(self):
        """Whether the concordia shows Th-corrected ratios (default: when a Th correction is set)."""
        if not self.th_correction_applied:
            return False
        return True if self.review_th_ratios is None else bool(self.review_th_ratios)

    def fraction_identifiers(self):
        """Publication identifiers/chemistry and Review link metadata, in CSV units."""
        from idtims_app.review import IDENTIFIERS
        from IDTIMS_UPbRPy.export import IDENTIFIER_COLUMNS

        if self.table is None:
            return {}
        frame = self.table.frame
        columns = [c for c in dict.fromkeys([*IDENTIFIERS, *(c for c, _ in IDENTIFIER_COLUMNS),
                                            "Database Read At", "Database Server", "Fraction UID"])
                   if c in frame.columns]
        out = {}
        for row in range(len(frame)):
            values = {}
            for column in columns:
                value = frame[column].iat[row]
                if not _empty(value) and str(value).strip():
                    values[column] = float(value) if column in NUMERIC_COLUMNS else str(value).strip()
            if values.get("Fraction UID"):
                values["Database link"] = "Linked to database"
            out[str(frame["Fraction ID"].iat[row])] = values
        return out

    def reduce(self):
        """Prepare, run and store a reduction on this thread; returns the ReductionRun."""
        run = self.prepare_reduction().run()
        self.apply_reduction(run)
        return run

    def export_full_table(self, path):
        """Write `export.full_table` of the reduced grains with 17 significant digits."""
        from IDTIMS_UPbRPy.export import full_table, write_csv

        write_csv(full_table(self.reduction.grains), path)
