"""Replayable, Qt-free project documents. Results are never serialized.

The embedded CSV is the fractions/1 contract at round-trip precision. Source
hashes describe the original imports, not subsequent edits of that CSV.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from pathlib import Path
import tempfile

from IDTIMS_UPbRPy.fractions import read_fractions, write_fractions
from IDTIMS_UPbRPy.settings import ReductionSettings
from idtims_app import __version__

FORMAT_NAME = "ID-TIMS reduction project"
VERSION = 1
ORIGIN_FORMAT = "idtims database link"


def database_origin(session):
    """Build the reserved v1 origin object from the current embedded CSV."""
    if session.table is None or "Fraction UID" not in session.table.frame.columns:
        return None
    fractions, servers = {}, set()
    columns = {"fraction_uid": "Fraction UID", "chemistry_batch_uid": "Chemistry Batch UID",
               "spike_solution": "Spike Solution", "spike_version_uid": "Spike Version UID",
               "database_read_at": "Database Read At"}
    for fid in session.table.fraction_ids:
        row = session.table._row(fid)
        if not row.get("Fraction UID"):
            continue
        if row.get("Database Server"):
            servers.add(row["Database Server"])
        entry = {k: row.get(c) for k, c in columns.items()}
        entry["spike_confirmed_at"] = (session.table.database_spike_confirmations[fid]["spike_confirmed_at"]
                                        if session.table.database_spike_confirmed(fid) else None)
        fractions[fid] = entry
    if len(servers) > 1:
        raise ValueError("A project cannot link fractions from more than one Database Server.")
    return {"format": ORIGIN_FORMAT, "format_version": 1, "server": next(iter(servers), None),
            "fractions": fractions} if fractions else None


def engine_fingerprint(root=None):
    """SHA-256 of engine source paths + bytes, shared by source and frozen apps.

    Frozen builds carry the source digest generated before PyInstaller runs.
    An explicit root supports source-copy tests.
    """
    import IDTIMS_UPbRPy as package

    if root is None and getattr(sys, "frozen", False):
        bundled = Path(__file__).with_name("engine_source_fingerprint.txt")
        try:
            value = bundled.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise RuntimeError(f"Frozen app is missing the bundled engine source fingerprint: {bundled}") from exc
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise RuntimeError(f"Invalid bundled engine source fingerprint: {bundled}")
        return value
    digest = hashlib.sha256()
    root = Path(root) if root is not None else Path(package.__file__).parent
    paths = sorted(root.rglob("*.py"), key=lambda p: p.relative_to(root).as_posix())
    if not paths:
        raise ValueError(f"No engine Python sources in {root}.")
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0"
                      + path.read_bytes())
    return digest.hexdigest()


def frozen_code_fingerprint():
    """Hash raw PYZ bytes for the frozen-code stability check only.

    Never marshal loaded code objects: their serialization can change after
    imports. Source runs have no PYZ and report None.
    """
    import IDTIMS_UPbRPy as package

    loader = package.__spec__.loader
    archive = getattr(loader, "_pyz_archive", None)
    if archive is None:
        return None
    names = sorted(n for n in archive.toc
                   if n == package.__name__ or n.startswith(package.__name__ + "."))
    if not names:
        raise ValueError("The frozen engine has no PYZ entries.")
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode("utf-8") + b"\0" + archive.extract(name, raw=True))
    return digest.hexdigest()


def scientific_state(session):
    buffer = io.StringIO()
    if session.table is not None:
        write_fractions(session.table, buffer)
    return {
        "fractions_csv": buffer.getvalue(),
        "no_oxide_confirmed": sorted(session.table.no_oxide_confirmed) if session.table else [],
        "settings": session.settings.to_dict(),
        "covariance_mode": "strict" if session.strict_covariance else "diagnostic",
        # Store decisions even before reduction, including failed fractions.
        "include": [f for f in session.table.fraction_ids if session.is_included(f)]
                   if session.table else [],
        "review": {"date_kind": session.review_kind, "concordia_mode": session.review_diagram,
                   "th_corrected": session.review_th_ratios},
        "origin": database_origin(session),
    }


def scientific_fingerprint(value):
    state = scientific_state(value) if not isinstance(value, dict) else {
        k: value[k] for k in ("fractions_csv", "no_oxide_confirmed", "settings",
                             "covariance_mode", "include", "review")}
    if isinstance(value, dict):
        state["origin"] = value.get("origin")
    return hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def document(session):
    from IDTIMS_UPbRPy import __version__ as engine_version
    return {"format": FORMAT_NAME, "version": VERSION, **scientific_state(session),
            "sources": list(session.source_records), "app_version": __version__,
            "engine_version": engine_version, "engine_fingerprint": engine_fingerprint()}


def validate(data):
    """Reject unsupported formats and malformed decisions before installation."""
    if not isinstance(data, dict) or data.get("format") != FORMAT_NAME:
        raise ValueError(f"This file is not an {FORMAT_NAME}.")
    if type(data.get("version")) is not int or data["version"] != VERSION:
        raise ValueError(f"Unsupported project version {data.get('version')!r}; this app supports version 1.")
    if not isinstance(data.get("fractions_csv"), str):
        raise ValueError("Project embedded fraction CSV is missing or invalid.")
    if not isinstance(data.get("settings"), dict):
        raise ValueError("Project reduction settings are missing or invalid.")
    ReductionSettings.from_dict(data["settings"])
    if data.get("covariance_mode") not in ("strict", "diagnostic"):
        raise ValueError("Project covariance mode must be strict or diagnostic.")
    for key in ("include", "no_oxide_confirmed"):
        if not isinstance(data.get(key), list) or not all(isinstance(v, str) for v in data[key]):
            raise ValueError(f"Project {key} must be a list of fraction IDs.")
    review = data.get("review")
    if not isinstance(review, dict) or review.get("concordia_mode") not in ("wetherill", "tw"):
        raise ValueError("Project concordia mode must be wetherill or tw.")
    from IDTIMS_UPbRPy.dates import DATE_KINDS
    if review.get("date_kind") is not None and review["date_kind"] not in DATE_KINDS:
        raise ValueError("Project weighted-mean date kind is invalid.")
    if review.get("th_corrected") is not None and type(review["th_corrected"]) is not bool:
        raise ValueError("Project Th toggle must be true, false or null.")
    if not isinstance(data.get("sources", []), list):
        raise ValueError("Project sources must be a list.")
    for source in data.get("sources", []):
        if (not isinstance(source, dict) or not isinstance(source.get("name"), str)
                or not isinstance(source.get("sha256"), str) or len(source["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in source["sha256"])):
            raise ValueError("Each project source needs a file name and SHA-256 digest.")
    if data.get("origin") is not None and not isinstance(data["origin"], dict):
        raise ValueError("Project origin must be an object or null.")
    origin = data.get("origin")
    if origin is not None:
        if origin.get("format") != ORIGIN_FORMAT:
            raise ValueError("Unsupported project origin format; this app reads only idtims database links.")
        if type(origin.get("format_version")) is not int or origin["format_version"] != 1:
            raise ValueError("Unsupported project origin format_version; this app supports version 1.")
        if not isinstance(origin.get("fractions"), dict) or origin.get("server") is not None \
                and not isinstance(origin["server"], str):
            raise ValueError("Project database origin needs a fractions object and a server string or null.")
        from datetime import datetime
        for fid, entry in origin["fractions"].items():
            if not isinstance(entry, dict) or not isinstance(fid, str):
                raise ValueError("Project database origin fractions must contain objects keyed by fraction ID.")
            for key in ("fraction_uid", "chemistry_batch_uid", "spike_solution", "spike_version_uid",
                        "database_read_at", "spike_confirmed_at"):
                if entry.get(key) is not None and not isinstance(entry[key], str):
                    raise ValueError(f"Project database origin {key} must be text or null.")
            stamp = entry.get("spike_confirmed_at")
            if stamp is not None:
                try:
                    if datetime.fromisoformat(stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp).utcoffset() is None:
                        raise ValueError()
                except ValueError:
                    raise ValueError("Project database spike confirmation must be ISO 8601 with an offset.") from None
    return data


def read(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid project JSON at line {exc.lineno}: {exc.msg}") from exc
    return validate(data)


def write(data, path):
    """Atomic replacement, with cleanup even if serialization or replace fails."""
    validate(data)
    target = Path(path).expanduser()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=f".{target.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target.resolve()


def restore(data):
    """Create a new session from inputs and freshly recompute all reducible rows."""
    from idtims_app.services import Session

    validate(data)
    session = Session()
    if data["fractions_csv"]:
        session.table = read_fractions(io.StringIO(data["fractions_csv"]))
        session._ensure_columns()
        ids = set(session.table.fraction_ids)
        for key in ("include", "no_oxide_confirmed"):
            if not set(data[key]) <= ids:
                raise ValueError(f"Project {key} names unknown fractions.")
        session.table.no_oxide_confirmed = set(data["no_oxide_confirmed"])
        session.excluded_fractions = ids - set(data["include"])
    session.settings = ReductionSettings.from_dict(data["settings"])
    if session.table is not None:
        session.table.enable_database_spikes(session.settings.spike_version)
        origin = data.get("origin")
        if origin is not None:
            for fid, entry in origin["fractions"].items():
                if fid not in session.table.fraction_ids:
                    continue
                row = session.table._row(fid)
                if (entry.get("fraction_uid") == row.get("Fraction UID")
                        and origin.get("server") == row.get("Database Server")
                        and entry.get("spike_solution") == row.get("Spike Solution")
                        and entry.get("spike_version_uid") == row.get("Spike Version UID")
                        and entry.get("spike_confirmed_at")):
                    session.table.database_spike_confirmations[fid] = dict(entry)
    session.strict_covariance = data["covariance_mode"] == "strict"
    session.review_kind = data["review"]["date_kind"]
    session.review_diagram = data["review"]["concordia_mode"]
    session.review_th_ratios = data["review"]["th_corrected"]
    session.source_records = list(data.get("sources", []))
    session.sources = [r["name"] for r in session.source_records]
    session.origin = data.get("origin")
    if session.table is not None and session.ready_ids() and not session.settings.problems():
        session.reduce()
    session.engine_note = ("Results were recomputed with a different engine version (code fingerprint changed)."
                           if data.get("engine_fingerprint") != engine_fingerprint() else "")
    session.mark_project_saved()
    return session
