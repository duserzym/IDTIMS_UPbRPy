"""App identity, public update key, TLS transport and bundled lab release notes."""
from pathlib import Path

from idtims_app import branding
from idtims_app.labupdate.config import UpdateConfig
from idtims_app.labupdate.tls import urlopen

PUBLIC_KEY = 'dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IDcxQTk4OTVBQkJEOEExOUIKUldTYm9kaTdXb21wY1ZhOVlSUzRoSTlQNE5lVHNmTVJBN2JGMEcycFBCYkVXVEgzTDhHN1VrbjgK'
REPO = "duserzym/IDTIMS_UPbRPy"


def release_notes(version: str) -> str | None:
    """Read the packaged notes, or the root copy in a source checkout."""
    if not version or Path(version).name != version or "\\" in version:
        return None
    name = f"{version.removeprefix('v')}.md"
    package = Path(__file__).resolve().parent
    for folder in (package / "release-notes", package.parents[1] / "release-notes"):
        try:
            return (folder / name).read_text(encoding="utf-8").strip() or None
        except OSError:
            pass
    return None


def update_config() -> UpdateConfig:
    return UpdateConfig(branding.DISPLAY_NAME, REPO, PUBLIC_KEY,
                        settings_org=branding.ORGANISATION, settings_app=branding.SLUG,
                        opener=urlopen, release_notes=release_notes)
