"""Recoverable whole-document sidecars; no results and no Qt dependencies."""
import hashlib
import os
from pathlib import Path

from idtims_app import branding, project


def directory():
    override = os.environ.get("IDTIMS_AUTOSAVE_DIR")
    return Path(override).expanduser() if override else Path.home() / branding.SLUG / "autosave"


def path_for(session):
    if session.project_path:
        path = Path(session.project_path).expanduser().resolve()
        digest = hashlib.sha1(str(path).encode()).hexdigest()[:10]
        name = f"{path.stem}-{digest}"
    else:
        name = f"untitled-{session.autosave_id}"
    return directory() / (name + branding.PROJECT_EXTENSION)


def save(session):
    path = path_for(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    project.write(project.document(session), path)
    return path


def candidate(session):
    """Offer only a newer sidecar whose scientific inputs differ from disk."""
    path = path_for(session)
    if not path.exists() or not session.project_path:
        return None
    if path.stat().st_mtime_ns <= Path(session.project_path).stat().st_mtime_ns:
        return None
    data = project.read(path)
    if project.scientific_fingerprint(data) == session.scientific_project_fingerprint():
        return None
    return data
