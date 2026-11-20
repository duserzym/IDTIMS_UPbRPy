"""Versioned tracer records, with private overlays and legacy CSV compatibility."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache
import os

import pandas as pd

from . import _spike_registry_check as checker

BUNDLED_OVERLAY = Path(__file__).with_suffix('')
LEGACY_COLUMNS = ('Pb205', 'U235', '202Pb/205Pb', '206Pb/205Pb', '207Pb/205Pb',
                  '204Pb/205Pb', '208Pb/205Pb', '207Pb/206Pb', '204Pb/206Pb',
                  '238U/235U', '233U/235U', '238U/233U', '235U/205Pb')


@dataclass(frozen=True)
class Measurement:
    value: float
    unit: str = 'ratio'
    uncertainty: float | None = None
    uncertainty_type: str | None = None
    # Original TOML number spellings preserve pandas' decimal conversion behavior.
    value_text: str = field(default='', repr=False)
    uncertainty_text: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Subfraction:
    id: str
    name: str
    notes: str = ''
    visibility: str = 'public'


@dataclass(frozen=True)
class Version:
    spike_id: str
    subfraction: str
    version: str
    status: str
    visibility: str
    source: str
    citation: dict
    locator: str
    concentrations: dict[str, Measurement]
    ratios: dict[str, Measurement]
    notes: str = ''
    calibrated: str | None = None
    supersedes: str | None = None
    legacy: tuple[tuple[str, str], ...] = ()

    @property
    def key(self):
        return f'{self.spike_id}/{self.subfraction}/{self.version}'


@dataclass
class Spike:
    id: str
    name: str
    aliases: list[str]
    spike_type: str
    isotopes: list[str]
    description: str
    visibility: str
    subfractions: dict[str, Subfraction] = field(default_factory=dict)
    versions: list[Version] = field(default_factory=list)


@dataclass
class Registry:
    spikes: dict[str, Spike]

    def by_key(self, key):
        """Return exactly spike/subfraction/version; never apply legacy aliases."""
        candidates = [v for s in self.spikes.values() for v in s.versions if v.key == key]
        if len(candidates) != 1:
            raise ValueError(f"Unknown or ambiguous spike registry key: {key}")
        return candidates[0]

    @property
    def names(self):
        return {name for spike in self.spikes.values()
                for name in (spike.id, spike.name, *spike.aliases,
                             *(name for v in spike.versions for name, _ in v.legacy))}

    def resolve(self, name, version=None, subfraction=None):
        spikes = [s for s in self.spikes.values()
                  if name in (s.id, s.name, *s.aliases) or
                  any(n == name for v in s.versions for n, _ in v.legacy)]
        if len(spikes) != 1:
            raise ValueError(f'Unknown or ambiguous spike: {name}')
        spike = spikes[0]
        candidates = [v for v in spike.versions
                      if subfraction is None or v.subfraction == subfraction]
        # Preserve SPIKES defaults and exact legacy (name, version) mappings.
        legacy_version = version if version is not None else ('v3' if name == 'ET2535' else 'v1')
        legacy = [v for v in candidates if (name, legacy_version) in v.legacy]
        if legacy:
            return legacy[0]
        if version is not None:
            candidates = [v for v in candidates if v.version == version]
        else:
            candidates = [v for v in candidates if v.status == 'current']
        if len(candidates) != 1:
            choices = ', '.join(v.key for v in candidates) or 'none'
            raise ValueError(f'Unknown or ambiguous spike/version: {name} {version}; candidates: {choices}. Specify subfraction and version.')
        return candidates[0]


def find_public_registry():
    """Find a manifest directory, in documented environment/home precedence."""
    candidates = []
    if os.environ.get('UPB_SPIKES_DIR'):
        candidates.append(Path(os.environ['UPB_SPIKES_DIR']).expanduser())
    if os.environ.get('UPB_STANDARDS_DIR'):
        candidates.append(Path(os.environ['UPB_STANDARDS_DIR']).expanduser() / 'spikes')
    candidates.extend((Path.home() / 'UPbRPy/upb-standards/spikes',
                       Path.home() / 'Github/upb-standards/spikes'))
    return next((p for p in candidates if (p / 'registry.toml').is_file()), None)


def load_registry(public=None, overlays=None):
    """Validate and merge discovered public data, bundled private data, and extras.

    Passing public=False explicitly disables public discovery. Extra overlays are
    appended to the bundled overlay and cannot replace any existing version.
    """
    if public is None:
        public = find_public_registry()
    elif public is False:
        public = None
    paths = [BUNDLED_OVERLAY, *(overlays or [])]
    layers = checker.check_registries(public, paths)
    spikes = {}
    for manifest, records, sources in layers:
        paths_by_id = {}
        for filename in checker.read_toml(manifest)['spike_files']:
            path = checker.local_path(manifest, filename)
            raw = checker.read_toml(path, parse_float=str)['spike']
            paths_by_id[raw['id']] = raw
        for s in records:
            sid = s['id']
            spike = spikes.setdefault(sid, Spike(sid, s['name'], [], s['spike_type'],
                                                  [], s['description'], s['visibility']))
            spike.aliases = list(dict.fromkeys([*spike.aliases, *s['aliases']]))
            spike.isotopes = list(dict.fromkeys([*spike.isotopes, *s['isotopes']]))
            for sub in s['subfractions']:
                spike.subfractions.setdefault(sub['id'], Subfraction(**sub, visibility=s['visibility']))
            raw_versions = paths_by_id[sid]['versions']
            for v, raw in zip(s['versions'], raw_versions):
                groups = {}
                for group in ('concentrations', 'ratios'):
                    groups[group] = {
                        label: Measurement(**m, value_text=str(raw[group][label]['value']),
                                           uncertainty_text=str(raw[group][label]['uncertainty']) if 'uncertainty' in m else None)
                        for label, m in v.get(group, {}).items()}
                spike.versions.append(Version(
                    spike_id=sid, subfraction=v['subfraction'], version=v['version'],
                    status=v['status'], visibility=s['visibility'], source=v['source'],
                    citation=dict(sources[v['source']]), locator=v['locator'],
                    notes=v.get('notes', ''), calibrated=v.get('calibrated'),
                    supersedes=v.get('supersedes'),
                    legacy=tuple((x['name'], x['version']) for x in v.get('legacy', [])),
                    **groups))
    return Registry(spikes)


def resolve(name, version=None, subfraction=None):
    return get_registry().resolve(name, version, subfraction)


def to_legacy_frame(version):
    """Return the historical unit/value/uncertainty frame, without deriving ratios.

    Numeric rows remain decimal strings as in pd.read_csv of the bundled CSVs;
    callers use pd.to_numeric. Unknown uncertainty and absent ratios become NaN.
    Absolute and two-sigma source uncertainties are converted only for this view.
    """
    measurements = {**version.concentrations, **version.ratios}
    rename = {'205Pb': 'Pb205', '235U': 'U235'}
    columns = list(LEGACY_COLUMNS)
    columns.extend(rename.get(k, k) for k in measurements if rename.get(k, k) not in columns)
    rows = {}
    reverse = {v: k for k, v in rename.items()}
    for col in columns:
        label = reverse.get(col, col)
        m = measurements.get(label)
        value = m.value_text if m else float('nan')
        uncertainty = float('nan')
        if m and m.uncertainty is not None:
            if m.uncertainty_type == '1sd_rel_pct':
                uncertainty = m.uncertainty_text
            else:
                u = m.uncertainty / (2 if m.uncertainty_type.startswith('2sd') else 1)
                if m.uncertainty_type.endswith('_abs'):
                    if m.value == 0:
                        raise ValueError(f'{version.key}: cannot express absolute uncertainty relative to zero for {label}')
                    u = u / m.value * 100
                uncertainty = str(u)
        rows[col] = ['[mol/g]' if label in version.concentrations or col in ('Pb205', 'U235') else '± 1s [%]', value, uncertainty]
    frame = pd.DataFrame(rows, index=pd.Index(['unit', 'value', 'uncertainty'], name='species'))
    return frame


@lru_cache(maxsize=16)
def _manifest_dependencies(manifest, signature):
    data = checker.read_toml(manifest)
    paths = {manifest, checker.local_path(manifest, data['lock'])}
    paths.update(checker.local_path(manifest, f) for f in data['spike_files'])
    if 'sources' in data:
        paths.add((manifest.parent / data['sources']).resolve())
    return tuple(sorted(paths))


def _signature(path):
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size


def _fingerprint(public):
    paths = set()
    for directory in [BUNDLED_OVERLAY, *([public] if public else [])]:
        manifest = checker.manifest_path(directory)
        paths.update(_manifest_dependencies(manifest, _signature(manifest)))
    return tuple((str(p), *_signature(p)) for p in sorted(paths))


# Reduction calls once per fraction. Revalidate when any manifest, source,
# composition or lock changes, including public discovery/environment changes.
@lru_cache(maxsize=4)
def _cached_registry(public, fingerprint):
    return load_registry(public=public or False)


def get_registry():
    public = find_public_registry()
    return _cached_registry(public, _fingerprint(public))


def known_spike_names():
    from .spikes import SPIKES
    try:
        return set(SPIKES) | get_registry().names
    except (OSError, ValueError, TypeError, KeyError):
        return set(SPIKES)
