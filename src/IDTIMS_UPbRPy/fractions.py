"""Read and write fraction files: contract `idtims-fractions/1` and legacy CSVs.

The contract text is `docs/contract-idtims-fractions-v1.md`. A file with a
`Contract` column is read as the contract; a file without one is read as a
legacy IDTIMS_UPbRPy/Tripoli CSV, whose `Grain ID` becomes `Fraction ID`.

`read_fractions(*sources)` merges one or more files by `Fraction ID` into a
`FractionTable`. The table keeps a pandas DataFrame in contract column names
(unknown columns kept as text), lists per-fraction issues for a GUI, maps the
reducible fractions to `load_grains`, and turns measured `rho <A>|<B>`
columns into `covariance_overrides`. `write_fractions` writes the contract
CSV at full precision.

Example::

    table = read_fractions("pb.fractions.csv", "u.fractions.csv")
    data, columns = table.load_grains_frame()
    grains = load_grains(data, *args, **kwargs, **columns)
"""
from __future__ import annotations

import csv
import io
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .spike_registry import known_spike_names

CONTRACT = "idtims-fractions/1"
CONTRACT_MAJOR = 1

__all__ = ["CONTRACT", "FractionFileError", "FractionIssue", "FractionTable",
           "read_fractions", "write_fractions", "IDENTITY_COLUMNS", "SETUP_COLUMNS",
           "PB_RATIOS", "PB_RATIOS_2535", "U_RATIOS", "PROVENANCE_COLUMNS",
           "SUPPORTED_CORRELATION_RATIOS", "SOURCE_LIST_COLUMNS", "CHEMISTRY_COLUMNS",
           "CHEMISTRY_NUMERIC_COLUMNS", "split_source_list"]

IDENTITY_COLUMNS = ["Contract", "Fraction ID", "Sample", "Beaker", "Source Mount",
                    "Source Grain", "Source Spot", "Aliquot", "Fraction UID", "Database Server",
                    "Database Read At", "Source Grain UID", "Source Spot UID",
                    "Source Fragment Note", "Capsule Set", "Chemistry Batch UID"]
SOURCE_LIST_COLUMNS = ["Source Mount", "Source Grain", "Source Spot", "Source Grain UID",
                       "Source Spot UID", "Source Fragment Note"]
CHEMISTRY_NUMERIC_COLUMNS = ["Annealing Temperature (°C)", "Annealing Duration (h)",
                             "Chemical Abrasion Temperature (°C)", "Chemical Abrasion Duration (h)"]
CHEMISTRY_COLUMNS = ["Annealing", "Chemical Abrasion", *CHEMISTRY_NUMERIC_COLUMNS,
                     "Chemistry Steps", "Spike Solution", "Spike Version UID"]
SETUP_COLUMNS = ["Sample Weight (mg)", "Spike Weight (g)", "Spike Type", "Spike", "Collector",
                 "Pb Collector Detail", "Pb Method", "U Method"]
PB_RATIOS = ["206Pb/204Pb", "206Pb/207Pb", "206Pb/205Pb", "207Pb/205Pb", "204Pb/205Pb",
             "208Pb/205Pb"]
PB_RATIOS_2535 = ["202Pb/205Pb"]
PB_OPTIONAL_RATIOS = ["204Pb/206Pb", "207Pb/206Pb"]
U_RATIOS = ["238U/235U", "233U/235U", "238U/233U"]
OXIDE = "U Oxide 18O/16O"
OXIDE_FORMULA = "U Oxide Formula"
OXIDE_FORMULAS = ("isobar_233_18O", "tripoli_java_00dc941", "instrument")
MEAN_STATISTICS = ("arithmetic", "geometric")
MEAN_STATISTIC_COLUMNS = ["Pb Mean Statistic", "U Mean Statistic"]
CYCLE_SELECTIONS = ("shared", "per_ratio")
CYCLE_SELECTION_COLUMNS = ["Pb Cycle Selection", "U Cycle Selection"]
PROVENANCE_COLUMNS = ["Pb Raw File", "U Raw File", "Pb Raw SHA256", "U Raw SHA256",
                      "Pb Run Start", "U Run Start", "Instrument", "Pb Cycles Used",
                      "Pb Cycles Total", "U Cycles Used", "U Cycles Total", "Filter Rule",
                      OXIDE, OXIDE_FORMULA, *MEAN_STATISTIC_COLUMNS, *CYCLE_SELECTION_COLUMNS,
                      "Raw App", "Raw App Session", "Raw App Session SHA256",
                      "Exported At", "Notes"]

ALL_RATIOS = PB_RATIOS + PB_RATIOS_2535 + PB_OPTIONAL_RATIOS + U_RATIOS
MEAN, ERROR = " Mean", " % Standard Error"
RATIO_COLUMNS = [r + s for r in ALL_RATIOS for s in (MEAN, ERROR)]
NUMERIC_COLUMNS = set(["Sample Weight (mg)", "Spike Weight (g)", OXIDE]
                      + RATIO_COLUMNS + CHEMISTRY_NUMERIC_COLUMNS)
REQUIRED_SETUP = ["Sample Weight (mg)", "Spike Weight (g)", "Spike Type", "Spike", "Collector"]
RHO_PREFIX = "rho "

# Contract ratio -> (engine variable, sign). A sign of -1 marks the reciprocal
# (Tripoli's 206/204 and 206/207 vs the engine's 204/206 and 207/206); to
# first order the relative error is unchanged and the correlation flips sign.
SUPPORTED_CORRELATION_RATIOS = {
    "206Pb/205Pb": ("Pb_R65m", 1), "208Pb/205Pb": ("Pb_R85m", 1),
    "204Pb/206Pb": ("Pb_R46m", 1), "206Pb/204Pb": ("Pb_R46m", -1),
    "207Pb/206Pb": ("Pb_R76m", 1), "206Pb/207Pb": ("Pb_R76m", -1),
    "238U/235U": ("U_R85m", 1), "233U/235U": ("U_R35m", 1),
}
# Engine variable -> (column used directly, reciprocal column used otherwise).
_ENGINE_SOURCE = {
    "Pb_R65m": ("206Pb/205Pb", None), "Pb_R85m": ("208Pb/205Pb", None),
    "Pb_R46m": ("204Pb/206Pb", "206Pb/204Pb"), "Pb_R76m": ("207Pb/206Pb", "206Pb/207Pb"),
    "U_R85m": ("238U/235U", None), "U_R35m": ("233U/235U", None),
}
_LOAD_GRAINS_COLUMNS = dict(
    id="Fraction ID", sample_weight="Sample Weight (mg)", spike_weight="Spike Weight (g)",
    spike_type="Spike Type", spike_name="Spike", collector="Collector",
    Pb_R45m="204Pb/205Pb Mean", Pb_R45m_std_rel="204Pb/205Pb % Standard Error",
    Pb_R46m="204Pb/206Pb Mean", Pb_R46m_std_rel="204Pb/206Pb % Standard Error",
    Pb_R64m="206Pb/204Pb Mean", Pb_R64m_std_rel="206Pb/204Pb % Standard Error",
    Pb_R65m="206Pb/205Pb Mean", Pb_R65m_std_rel="206Pb/205Pb % Standard Error",
    Pb_R67m="206Pb/207Pb Mean", Pb_R67m_std_rel="206Pb/207Pb % Standard Error",
    Pb_R75m="207Pb/205Pb Mean", Pb_R75m_std_rel="207Pb/205Pb % Standard Error",
    Pb_R76m="207Pb/206Pb Mean", Pb_R76m_std_rel="207Pb/206Pb % Standard Error",
    Pb_R85m="208Pb/205Pb Mean", Pb_R85m_std_rel="208Pb/205Pb % Standard Error",
    U_R85m="238U/235U Mean", U_R85m_std_rel="238U/235U % Standard Error",
    U_R35m="233U/235U Mean", U_R35m_std_rel="233U/235U % Standard Error",
    U_R83m="238U/233U Mean", U_R83m_std_rel="238U/233U % Standard Error")

# Issue kinds that keep a fraction out of `load_grains_frame`.
BLOCKING = {"missing_block", "incomplete_block", "missing_setup", "invalid_value",
            "unconfirmed_spike_type", "unconfirmed_database_spike", "database_spike"}


class FractionFileError(ValueError):
    """A fraction file cannot be read or merged; the message says where and why."""


@dataclass(frozen=True)
class FractionIssue:
    """One problem with one fraction, for a GUI to list.

    kind: 'missing_block', 'incomplete_block', 'missing_setup', 'invalid_value',
    'unconfirmed_spike_type', 'missing_oxide', 'oxide_formula', 'oxide_formula_note'
    (informational), 'mean_statistic_note' (informational), 'cycle_selection_note' (informational)
    'source_list_count' (informational), 'unconfirmed_database_spike', 'database_spike'
    or 'unsupported_correlation'. Database tracer issues require app opt-in.
    """
    fraction_id: str
    kind: str
    message: str
    columns: tuple = ()

    @property
    def blocking(self):
        """True when the fraction cannot be passed to `load_grains` yet."""
        return self.kind in BLOCKING


def _rho_ratios(column):
    """('A', 'B') for a `rho A|B` column, else None."""
    if not column.startswith(RHO_PREFIX) or "|" not in column:
        return None
    a, _, b = column[len(RHO_PREFIX):].partition("|")
    return a, b


def _is_numeric_column(column):
    return column in NUMERIC_COLUMNS or _rho_ratios(column) is not None


def _empty(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


def split_source_list(value):
    """Split a per-source cell, preserving empty entries (including the last)."""
    return [] if _empty(value) or value == "" else [s.strip() for s in str(value).split(";")]


def _database_time(value, fraction_id, files):
    try:
        stamp = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if stamp.utcoffset() is None:
            raise ValueError("missing offset")
        return stamp
    except (ValueError, TypeError):
        raise FractionFileError(f"Fraction {fraction_id!r} in {files}: Database Read At "
                                f"must be ISO 8601 with an offset (got {value!r}).") from None


def _read_text(source, index=1):
    """(text, name) of a path or file-like object; a UTF-8 BOM is dropped."""
    if hasattr(source, "read"):
        raw = source.read()
        name = str(getattr(source, "name", None) or f"<input {index}>")
    else:
        name = os.fspath(source)
        with open(name, "rb") as stream:
            raw = stream.read()
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise FractionFileError(f"{name}: the file is not UTF-8 text ({exc}).") from None
    return raw.lstrip("﻿"), name


def _parse_number(text, name, fraction_id, column):
    try:
        value = float(text)
    except ValueError:
        raise FractionFileError(f"{name}: fraction {fraction_id!r}, column {column!r}: "
                                f"{text!r} is not a number.") from None
    if column.startswith(RHO_PREFIX) and math.isfinite(value) and abs(value) > 1:
        raise FractionFileError(f"{name}: fraction {fraction_id!r}, column {column!r}: "
                                f"a correlation must lie between -1 and 1 (got {text}).")
    return value


def _normalise_spike_type(text):
    """'535' or '2535' for numeric spellings such as '535.0'; otherwise unchanged."""
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number in (535, 2535) else text


def _read_one(source, index=1):
    """Read one file into (records by Fraction ID in order, column order, name, kind)."""
    text, name = _read_text(source, index)
    rows = list(csv.reader(io.StringIO(text, newline="")))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        raise FractionFileError(f"{name}: the file is empty.")
    header = rows[0]
    if len(set(header)) != len(header):
        dup = sorted({c for c in header if header.count(c) > 1})
        raise FractionFileError(f"{name}: repeated column names: {', '.join(dup)}.")
    if "Contract" in header:
        kind = "contract"
    else:
        kind = "legacy"
        if "Grain ID" not in header:
            raise FractionFileError(
                f"{name}: no 'Contract' column, so it was read as a legacy CSV, but it has no "
                "'Grain ID' column. Contract files need a 'Contract' column with "
                f"'{CONTRACT}' on every row.")
        if "Fraction ID" in header:
            raise FractionFileError(f"{name}: legacy CSV has both 'Grain ID' and "
                                    "'Fraction ID'; keep one.")
        header = ["Fraction ID" if c == "Grain ID" else c for c in header]
    if "Fraction ID" not in header:
        raise FractionFileError(f"{name}: the required column 'Fraction ID' is missing.")
    records = {}
    for number, row in enumerate(rows[1:], start=2):
        if len(row) > len(header):
            raise FractionFileError(f"{name}, line {number}: more cells than columns.")
        # A final empty source is encoded by a trailing '; '. Keep that text,
        # rather than trimming away part of the list's delimiter.
        cells = {c: (v if c in SOURCE_LIST_COLUMNS and ";" in v else v.strip())
                 for c, v in zip(header, row) if v.strip() != ""}
        fraction_id = cells.get("Fraction ID")
        if fraction_id is None:
            raise FractionFileError(f"{name}, line {number}: 'Fraction ID' is empty.")
        if kind == "contract":
            _check_contract(cells.get("Contract"), name, number)
            cells.pop("Contract")
        if fraction_id in records:
            raise FractionFileError(f"{name}: fraction {fraction_id!r} appears more than once; "
                                    "'Fraction ID' must be unique within one file.")
        values = {}
        for column, value in cells.items():
            if _is_numeric_column(column):
                values[column] = _parse_number(value, name, fraction_id, column)
            elif column == "Spike Type":
                values[column] = _normalise_spike_type(value)
            else:
                values[column] = value
        records[fraction_id] = values
    columns = [c for c in header if c != "Contract"]
    return records, columns, name, kind


def _check_contract(value, name, line):
    if value is None:
        raise FractionFileError(f"{name}, line {line}: 'Contract' is empty; every row needs "
                                f"'{CONTRACT}'.")
    match = re.fullmatch(r"idtims-fractions/(\d+)(?:\.\d+)*", value)
    if match is None:
        raise FractionFileError(f"{name}, line {line}: unknown contract {value!r}; expected "
                                f"'{CONTRACT}'.")
    if int(match.group(1)) != CONTRACT_MAJOR:
        raise FractionFileError(
            f"{name}: written for contract {value!r}, but this version of IDTIMS_UPbRPy reads "
            f"only '{CONTRACT}'. Update IDTIMS_UPbRPy to read it.")


def read_fractions(*sources):
    """Read contract or legacy CSVs (paths or file-like objects) into a `FractionTable`.

    Rows sharing a `Fraction ID` are merged across files; a conflicting
    non-empty value raises `FractionFileError` naming the fraction, the column
    and both files. Database Read At keeps the latest offset-aware ISO timestamp;
    mixed Database Server values are refused across the entire merged table.
    """
    if not sources:
        raise FractionFileError("No fraction file given.")
    merged, origin, columns, names, kinds = {}, {}, [], [], {}
    for index, source in enumerate(sources, start=1):
        records, file_columns, name, kind = _read_one(source, index)
        names.append(name)
        kinds[name] = kind
        for column in file_columns:
            if column not in columns:
                columns.append(column)
        for fraction_id, values in records.items():
            if "Database Read At" in values:
                _database_time(values["Database Read At"], fraction_id, name)
            target = merged.setdefault(fraction_id, {})
            for column, value in values.items():
                if column in target and target[column] != value:
                    if column == "Database Read At":
                        files = f"{origin[fraction_id, column]} and {name}"
                        if _database_time(value, fraction_id, files) > _database_time(target[column], fraction_id, files):
                            target[column] = value
                            origin[fraction_id, column] = name
                        continue
                    raise FractionFileError(
                        f"Fraction {fraction_id!r}, column {column!r}: "
                        f"{origin[fraction_id, column]} gives {target[column]!r} but "
                        f"{name} gives {value!r}.")
                if column not in target:
                    target[column] = value
                    origin[fraction_id, column] = name
    servers = {v["Database Server"] for v in merged.values() if v.get("Database Server")}
    if len(servers) > 1:
        raise FractionFileError("More than one Database Server across " + ", ".join(names)
                                + ": " + ", ".join(sorted(servers)) + ".")
    frame = pd.DataFrame([dict(values, **{"Fraction ID": fid}) for fid, values in merged.items()],
                         columns=columns)
    for column in frame.columns:
        if _is_numeric_column(column):
            frame[column] = pd.to_numeric(frame[column]).astype(float)
        else:
            frame[column] = frame[column].astype(object).where(frame[column].notna(), None)
    frame.insert(0, "Contract", CONTRACT)
    table = FractionTable(frame.reset_index(drop=True), sources=names, source_kinds=kinds)
    for fid in table.fraction_ids:
        row = table._row(fid)
        if _empty(row.get("Spike Type")) and not _empty(row.get("202Pb/205Pb Mean")):
            table.inferred_spike_types[fid] = "2535"
    return table


@dataclass(eq=False)
class FractionTable:
    """Fractions in contract column names plus what still needs the user.

    `frame` holds one row per fraction: numbers as float (NaN when missing),
    text as str (None when missing). `inferred_spike_types` maps fractions
    whose `Spike Type` was inferred (from `202Pb/205Pb`) to the inferred value;
    the cell stays empty until `confirm_spike_type` is called.
    """
    frame: pd.DataFrame
    sources: list = field(default_factory=list)
    source_kinds: dict = field(default_factory=dict)
    inferred_spike_types: dict = field(default_factory=dict)
    no_oxide_confirmed: set = field(default_factory=set)
    database_spikes_enabled: bool = False
    database_spike_version: str | None = None
    database_spike_confirmations: dict = field(default_factory=dict)

    def enable_database_spikes(self, version=None):
        """App opt-in: preselect exact local keys and require individual confirmation."""
        from .spike_registry import get_registry
        self.database_spikes_enabled = True
        self.database_spike_version = version
        if "Spike Solution" not in self.frame.columns:
            return
        for fid in self.fraction_ids:
            row = self._row(fid)
            key = row.get("Spike Solution")
            if _empty(key) or not key or not _empty(row.get("Spike")):
                continue
            try:
                selected = get_registry().by_key(key)
            except (ValueError, OSError, KeyError, TypeError):
                continue
            self._set(fid, "Spike", selected.spike_id)

    def database_spike_confirmed(self, fid):
        confirmation = self.database_spike_confirmations.get(fid, {})
        if not confirmation.get("spike_confirmed_at"):
            return False
        row = self._row(fid)
        return bool(confirmation.get("spike_confirmed_at") and row.get("Spike Solution")
                    and confirmation.get("spike_solution") == row.get("Spike Solution")
                    and confirmation.get("spike_version_uid") == row.get("Spike Version UID"))

    def database_spike_issues(self, fid, row=None):
        from .spike_registry import get_registry, to_legacy_frame
        from .tracer import complete_tracer
        if not self.database_spikes_enabled or "Spike Solution" not in self.frame.columns:
            return []
        row = self._row(fid) if row is None else row
        key = row.get("Spike Solution")
        if not self.database_spikes_enabled or _empty(key) or not key:
            return []
        columns = ("Spike Solution", "Spike", "Spike Version UID")
        try:
            registry = get_registry()
            selected = registry.by_key(key)
        except (ValueError, OSError, KeyError, TypeError):
            message = f"Database spike {key} is not in this app's spike registry; choose a tracer."
        else:
            spike = registry.spikes[selected.spike_id]
            try:
                frame = to_legacy_frame(selected).loc[["value", "uncertainty"]].apply(pd.to_numeric, errors="coerce")
                complete_tracer(frame, key, key=key)
            except ValueError as error:
                return [FractionIssue(fid, "database_spike", str(error), columns)]
            names = {spike.id, spike.name, *spike.aliases,
                     *(n for v in spike.versions for n, _ in v.legacy)}
            if row.get("Spike") not in names:
                message = f"Database spike {key} disagrees with Spike {row.get('Spike')!r}; choose a tracer."
            elif row.get("Spike Type") and str(row["Spike Type"]) != spike.spike_type:
                message = f"Database spike {key} needs Spike Type {spike.spike_type}; choose a tracer."
            elif self.database_spike_confirmed(fid):
                return []
            elif self.database_spike_version not in (None, selected.version):
                message = (f"Database spike {key} contradicts project tracer version "
                           f"{self.database_spike_version}; choose Default per tracer or {selected.version}, then confirm.")
            else:
                return [FractionIssue(fid, "unconfirmed_database_spike",
                        f"Confirm database spike {key} ({selected.source}, {selected.status}); "
                        "the confirmed key overrides the project tracer version for this fraction.", columns)]
        return [FractionIssue(fid, "database_spike", message, columns)]

    def confirm_database_spike(self, fid):
        issues = self.database_spike_issues(fid)
        if not issues or any(i.kind != "unconfirmed_database_spike" for i in issues):
            raise ValueError(f"{fid}: database spike is not awaiting confirmation.")
        row = self._row(fid)
        self.database_spike_confirmations[fid] = {
            "spike_solution": row["Spike Solution"], "spike_version_uid": row.get("Spike Version UID"),
            "spike_confirmed_at": datetime.now(timezone.utc).isoformat()}

    @property
    def fraction_ids(self):
        return [str(f) for f in self.frame["Fraction ID"]]

    def _row(self, fraction_id):
        rows = self.frame.index[self.frame["Fraction ID"] == fraction_id]
        if len(rows) != 1:
            raise KeyError(f"Unknown fraction {fraction_id!r}")
        return self.frame.loc[rows[0]].to_dict()

    def _set(self, fraction_id, column, value):
        if column not in self.frame.columns:
            self.frame[column] = np.nan if _is_numeric_column(column) else None
            if not _is_numeric_column(column):
                self.frame[column] = self.frame[column].astype(object)
        self.frame.loc[self.frame["Fraction ID"] == fraction_id, column] = value

    def confirm_spike_type(self, fraction_id, spike_type=None):
        """Accept the inferred spike type (or set another) for one fraction."""
        value = spike_type if spike_type is not None else self.inferred_spike_types[fraction_id]
        self._set(fraction_id, "Spike Type", _normalise_spike_type(str(value)))
        self.inferred_spike_types.pop(fraction_id, None)

    def confirm_no_oxide_correction(self, fraction_id):
        """Record that the user confirmed no oxide correction applies to the U block."""
        self._row(fraction_id)
        self.no_oxide_confirmed.add(fraction_id)

    def mean_statistic(self, fraction_id, block):
        """The block's declared statistic; missing means legacy arithmetic statistics.

        Invalid declarations are blocking issues and cannot be interpreted here.
        """
        if block not in ("Pb", "U"):
            raise ValueError("Mean statistic block must be Pb or U.")
        column = f"{block} Mean Statistic"
        value = self._row(fraction_id).get(column)
        if _empty(value) or value == "":
            return "arithmetic"
        if value not in MEAN_STATISTICS:
            raise ValueError(f"{fraction_id}: {column} must be arithmetic or geometric (got {value}).")
        return value

    # -- issues ------------------------------------------------------------
    def issues(self, fraction_id=None):
        """`FractionIssue`s for one fraction, or for all fractions in order."""
        ids = [fraction_id] if fraction_id is not None else self.fraction_ids
        out = []
        for fid in ids:
            out.extend(self._issues(fid))
        return out

    def _issues(self, fid):
        row = self._row(fid)
        has = lambda c: not _empty(row.get(c))
        out = []
        counts = {c: len(split_source_list(row.get(c))) for c in SOURCE_LIST_COLUMNS
                  if not _empty(row.get(c)) and row.get(c) != ""}
        if len(set(counts.values())) > 1:
            out.append(FractionIssue(fid, "source_list_count",
                       f"{fid}: per-source list counts differ: "
                       + ", ".join(f"{c} = {n}" for c, n in counts.items()) + ".", tuple(counts)))
        out.extend(self.database_spike_issues(fid, row))
        spike_type = row.get("Spike Type")
        if fid in self.inferred_spike_types:
            out.append(FractionIssue(fid, "unconfirmed_spike_type",
                       f"{fid}: Spike Type is empty but 202Pb/205Pb is present, so 2535 is "
                       "assumed. Please confirm the spike type.", ("Spike Type",)))
            spike_type = self.inferred_spike_types[fid]
        pb = PB_RATIOS + (PB_RATIOS_2535 if spike_type == "2535" else [])
        for block, ratios in (("Pb", pb), ("U", U_RATIOS)):
            statistic_column = f"{block} Mean Statistic"
            statistic = row.get(statistic_column)
            if has(statistic_column) and statistic != "" and statistic not in MEAN_STATISTICS:
                out.append(FractionIssue(fid, "invalid_value",
                           f"{fid}: {statistic_column} must be arithmetic or geometric "
                           f"(got {statistic}).", (statistic_column,)))
            elif statistic == "geometric":
                out.append(FractionIssue(fid, "mean_statistic_note",
                           f"{fid}: {block} ratios are geometric means with geometric % standard "
                           "errors (Java Tripoli); legacy Tripoli and existing BSU sheets use "
                           "arithmetic statistics.", (statistic_column,)))
            cols = [r + s for r in ratios for s in (MEAN, ERROR)]
            missing = tuple(c for c in cols if not has(c))
            selection_column = f"{block} Cycle Selection"
            selection = row.get(selection_column) if has(selection_column) else ""
            if len(missing) < len(cols):
                if selection not in ("",) + CYCLE_SELECTIONS:
                    out.append(FractionIssue(fid, "invalid_value",
                               f"{fid}: {selection_column} must be shared or per_ratio "
                               f"(got {selection}).", (selection_column,)))
                elif selection != "shared":
                    how = ("each ratio had its own accepted-cycle mask" if selection == "per_ratio"
                           else "the accepted-cycle selection is not recorded")
                    out.append(FractionIssue(fid, "cycle_selection_note",
                               f"{fid}: {block} {how}. Ratios sharing 205Pb or the 267 beam are "
                               "correlated, so per-ratio masks can make the exported errors and "
                               "correlations inconsistent; a shared mask avoids this.",
                               (selection_column,)))
            if len(missing) == len(cols):
                out.append(FractionIssue(fid, "missing_block",
                           f"{fid}: no {block} measurement yet.", missing))
            elif missing:
                out.append(FractionIssue(fid, "incomplete_block",
                           f"{fid}: the {block} block lacks " + ", ".join(missing) + ".",
                           missing))
            elif block == "U" and not has(OXIDE) and fid not in self.no_oxide_confirmed:
                out.append(FractionIssue(fid, "missing_oxide",
                           f"{fid}: {OXIDE} is empty. Enter the value used for the oxide "
                           "correction, or confirm that none applies.", (OXIDE,)))
            elif block == "U" and has(OXIDE) and (not has(OXIDE_FORMULA)
                                                  or row[OXIDE_FORMULA] not in OXIDE_FORMULAS):
                got = row[OXIDE_FORMULA] if has(OXIDE_FORMULA) else "nothing"
                out.append(FractionIssue(fid, "oxide_formula",
                           f"{fid}: {OXIDE_FORMULA} must be one of " + ", ".join(OXIDE_FORMULAS)
                           + f" when {OXIDE} is filled (got {got}).", (OXIDE_FORMULA,)))
            elif block == "U" and has(OXIDE) and row[OXIDE_FORMULA] == "tripoli_java_00dc941":
                out.append(FractionIssue(fid, "oxide_formula_note",
                           f"{fid}: U ratios were oxide-corrected with the Java Tripoli form "
                           "(tripoli_java_00dc941), a comparison option. Its 238/235 correction "
                           "uses r270/267 instead of r265/267 and grows with the sample-to-spike "
                           "ratio; the default form is isobar_233_18O.", (OXIDE_FORMULA,)))
            elif block == "U" and has(OXIDE) and row[OXIDE_FORMULA] == "instrument":
                out.append(FractionIssue(fid, "oxide_formula_note",
                           f"{fid}: U ratios arrived already oxide-corrected in the raw file "
                           f"(18O/16O = {row[OXIDE]} from the function names); the writer did not "
                           "recompute them and the formula is not recorded.",
                           (OXIDE_FORMULA,)))
        required = [c for c in REQUIRED_SETUP if not (c == "Spike Type" and fid in
                                                      self.inferred_spike_types)]
        if spike_type == "2535":
            required.remove("Collector")
        missing = tuple(c for c in required if not has(c))
        if missing:
            out.append(FractionIssue(fid, "missing_setup",
                       f"{fid}: please enter " + ", ".join(missing) + ".", missing))
        if has("Spike Type") and row["Spike Type"] not in ("535", "2535"):
            out.append(FractionIssue(fid, "invalid_value",
                       f"{fid}: Spike Type must be 535 or 2535 (got {row['Spike Type']!r}).",
                       ("Spike Type",)))
        if has("Collector") and row["Collector"] not in ("F", "D"):
            out.append(FractionIssue(fid, "invalid_value",
                       f"{fid}: Collector must be F (Faraday) or D (Daly) "
                       f"(got {row['Collector']!r}).", ("Collector",)))
        if has("Spike") and row["Spike"] not in known_spike_names():
            out.append(FractionIssue(fid, "invalid_value",
                       f"{fid}: unknown tracer {row['Spike']!r}; known tracers are "
                       + ", ".join(sorted(known_spike_names())) + ".", ("Spike",)))
        _, unsupported = self._correlations(fid)
        out.extend(FractionIssue(fid, "unsupported_correlation", message, (column,))
                   for column, message in unsupported)
        return out

    def reducible_ids(self, require_oxide=False):
        """Fractions with both blocks, all setup fields and no blocking issue."""
        out = []
        for fid in self.fraction_ids:
            kinds = {i.kind for i in self._issues(fid)}
            if kinds & BLOCKING or (require_oxide and kinds & {"missing_oxide", "oxide_formula"}):
                continue
            out.append(fid)
        return out

    # -- load_grains -------------------------------------------------------
    def load_grains_frame(self, require_oxide=False):
        """(DataFrame, column keyword arguments) for `load_grains`, reducible fractions only.

        Pass the dict as ``load_grains(data, ..., **columns)``. With
        `require_oxide=True`, fractions whose U block lacks `U Oxide 18O/16O`
        (and was not confirmed) are left out, as the contract asks of the app.
        """
        ids = self.reducible_ids(require_oxide=require_oxide)
        data = self.frame[self.frame["Fraction ID"].isin(ids)].reset_index(drop=True).copy()
        data["Spike Type"] = data["Spike Type"].astype(int)
        for direct, reciprocal in (("204Pb/206Pb", "206Pb/204Pb"),
                                   ("207Pb/206Pb", "206Pb/207Pb")):
            mean, error = direct + MEAN, direct + ERROR
            if mean not in data.columns and error not in data.columns:
                continue
            if mean not in data.columns or error not in data.columns \
                    or data[[mean, error]].isna().all().all():
                data = data.drop(columns=[c for c in (mean, error) if c in data.columns])
                continue
            # Fill rows lacking the optional orientation exactly as load_grains would.
            gap = data[mean].isna() | data[error].isna()
            data.loc[gap, mean] = 1 / data.loc[gap, reciprocal + MEAN]
            data.loc[gap, error] = data.loc[gap, reciprocal + ERROR]
        columns = dict(_LOAD_GRAINS_COLUMNS)
        if "202Pb/205Pb" + MEAN in data.columns:
            # 2535 rows read measured 202/205; 535 rows ignore these columns.
            columns.update(Pb_R25m="202Pb/205Pb" + MEAN, Pb_R25m_std_rel="202Pb/205Pb" + ERROR)
        return data, columns

    # -- correlations ------------------------------------------------------
    def _engine_value(self, row, variable):
        """(value, absolute 1σ) of an engine measured variable, as load_grains forms it."""
        direct, reciprocal = _ENGINE_SOURCE[variable]
        if not _empty(row.get(direct + MEAN)) and not _empty(row.get(direct + ERROR)):
            value, rel = row[direct + MEAN], row[direct + ERROR]
        else:
            value, rel = 1 / row[reciprocal + MEAN], row[reciprocal + ERROR]
        return value, value * rel / 100

    def _correlations(self, fid):
        row = self._row(fid)
        found, unsupported, seen = {}, [], {}
        for column in self.frame.columns:
            pair = _rho_ratios(column)
            if pair is None or _empty(row.get(column)):
                continue
            a, b = pair
            unknown = [r for r in (a, b) if r not in ALL_RATIOS]
            if unknown:
                unsupported.append((column, f"{fid}: {column!r} names unknown ratio "
                                    + ", ".join(repr(u) for u in unknown) + "; it is ignored."))
                continue
            if a not in SUPPORTED_CORRELATION_RATIOS or b not in SUPPORTED_CORRELATION_RATIOS:
                other = [r for r in (a, b) if r not in SUPPORTED_CORRELATION_RATIOS]
                unsupported.append((column, f"{fid}: {column!r} is not used. The engine holds "
                                    + ", ".join(other) + " only through derived ratios, so this "
                                    "correlation cannot be applied without a model; the "
                                    "engine's documented assumption is kept."))
                continue
            (va, sa), (vb, sb) = SUPPORTED_CORRELATION_RATIOS[a], SUPPORTED_CORRELATION_RATIOS[b]
            if va == vb:
                unsupported.append((column, f"{fid}: {column!r} relates two orientations of "
                                    "the same ratio; it is ignored."))
                continue
            if va[:2] != vb[:2]:
                unsupported.append((column, f"{fid}: {column!r} pairs a Pb and a U ratio, which "
                                    "are not measured in the same cycles; it is ignored."))
                continue
            needed = [r + s for r in (a, b) for s in (MEAN, ERROR)]
            if any(_empty(row.get(c)) for c in needed):
                unsupported.append((column, f"{fid}: {column!r} cannot be used because its "
                                    "ratios are missing."))
                continue
            key = tuple(sorted((va, vb)))
            if key in seen:
                unsupported.append((column, f"{fid}: {column!r} and {seen[key]!r} describe the "
                                    "same engine pair; neither is used."))
                found.pop(key, None)
                continue
            seen[key] = column
            (_, std_a), (_, std_b) = self._engine_value(row, va), self._engine_value(row, vb)
            found[key] = sa * sb * row[column] * std_a * std_b
        return found, unsupported

    def covariance_overrides(self, fraction_id):
        """Absolute input covariances from the fraction's `rho` columns, for `load_grains`.

        Keys are engine variable pairs such as ('Pb_R46m', 'Pb_R65m'); values
        are rho times the two absolute 1σ errors, using the same values and
        orientation load_grains uses. Unsupported columns are skipped and
        reported by `issues()` as 'unsupported_correlation'. An override
        replaces the covariance the engine would otherwise derive.
        """
        return self._correlations(fraction_id)[0]


def _cell(value):
    if _empty(value):
        return ""
    if isinstance(value, (float, np.floating)):
        return repr(float(value))
    if isinstance(value, (np.integer,)):
        return str(int(value))
    return str(value)


def _column_order(columns):
    known = IDENTITY_COLUMNS + SETUP_COLUMNS + CHEMISTRY_COLUMNS + RATIO_COLUMNS
    rho = [c for c in columns if _rho_ratios(c) is not None]
    first = [c for c in known if c in columns] + rho
    first += [c for c in PROVENANCE_COLUMNS if c in columns]
    return first + [c for c in columns if c not in first]


def write_fractions(table, path_or_buffer):
    """Write `table` as a contract CSV: UTF-8, full precision, `Contract` on every row."""
    frame = table.frame if isinstance(table, FractionTable) else table
    columns = _column_order(list(frame.columns))
    if "Contract" not in columns:
        columns.insert(0, "Contract")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for _, row in frame.iterrows():
        writer.writerow([CONTRACT if c == "Contract" else _cell(row.get(c)) for c in columns])
    text = buffer.getvalue()
    if hasattr(path_or_buffer, "write"):
        if isinstance(path_or_buffer, (io.RawIOBase, io.BufferedIOBase)):
            path_or_buffer.write(text.encode("utf-8"))
        else:
            path_or_buffer.write(text)
    else:
        with open(path_or_buffer, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
