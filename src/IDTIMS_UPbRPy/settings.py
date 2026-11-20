"""Reduction settings as one JSON round-trippable object.

`ReductionSettings` holds everything `load_grains` takes besides the fraction
table: the Pb fractionation factors for 535 tracers, lab blanks, initial
common Pb, the Th correction, the tracer version and the covariance mode.
`load_grains_arguments()` turns it into the four dictionaries and keyword
arguments `load_grains` accepts today, unchanged.

Units are those of `load_grains`: fractionation in %/amu with an absolute
1σ in %/amu, blank masses in pg, every `_std_rel` a 1σ percentage, and
`D_Th_U_std` and `Th_U_magma_std` absolute 1σ. Decay constants are read from
`IDTIMS_UPbRPy.constants` and are only shown here, never changed.
Th_U_magma is the atomic Th/U of the melt relative to total U, as in the BSU sheets.

Example::

    settings = ReductionSettings.from_dicts(F, B, C, T, strict_covariance=False)
    args, kwargs = settings.load_grains_arguments()
    grains = load_grains(data, *args, **kwargs)
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields
from types import MappingProxyType

from . import constants
from .utils import SK75

FORMAT = "idtims-reduction-settings"
VERSION = 1

__all__ = ["FORMAT", "VERSION", "SettingsError", "Fractionation", "LabBlanks", "CommonPb",
           "ThCorrection", "ReductionSettings", "decay_constants"]

_DECAY_NAMES = ("lambda_238", "lambda_238_std", "lambda_235", "lambda_235_std",
                "lambda_232", "lambda_232_std", "lambda_230")


class SettingsError(ValueError):
    """Settings are invalid; the message lists every problem, one per line."""


def decay_constants():
    """Decay constants in use (1/year, std 1σ), read-only, from `constants`."""
    return MappingProxyType({name: getattr(constants, name) for name in _DECAY_NAMES})


def _number(value):
    """True for a real, non-boolean number."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check(problems, label, value, *, positive=False, nonnegative=False, rho=False,
           optional=False):
    """Append a readable message to `problems` when `value` breaks a rule."""
    if value is None:
        if not optional:
            problems.append(f"{label} is missing.")
        return
    if not _number(value) or not math.isfinite(value):
        problems.append(f"{label} must be a finite number (got {value!r}).")
    elif positive and value <= 0:
        problems.append(f"{label} must be greater than zero (got {value!r}).")
    elif nonnegative and value < 0:
        problems.append(f"{label} cannot be negative (got {value!r}).")
    elif rho and abs(value) > 1:
        problems.append(f"{label} must lie between -1 and 1 (got {value!r}).")


def _from_mapping(cls, data, section):
    """Build a dataclass from a dict, rejecting keys it does not know."""
    if not isinstance(data, dict):
        raise SettingsError(f"Settings section '{section}' must be an object.")
    known = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise SettingsError(f"Settings section '{section}' has unknown entries: "
                            + ", ".join(unknown) + ".")
    return cls(**data)


@dataclass
class Fractionation:
    """Pb fractionation per collector for 535 tracers, %/amu with absolute 1σ."""
    FPb_Faraday: float = 0.1
    FPb_Faraday_std: float = 0.02
    FPb_Daly: float = 0.18
    FPb_Daly_std: float = 0.03

    def problems(self):
        out = []
        _check(out, "Faraday Pb fractionation (%/amu)", self.FPb_Faraday)
        _check(out, "Faraday Pb fractionation uncertainty (%/amu)", self.FPb_Faraday_std,
               nonnegative=True)
        _check(out, "Daly Pb fractionation (%/amu)", self.FPb_Daly)
        _check(out, "Daly Pb fractionation uncertainty (%/amu)", self.FPb_Daly_std,
               nonnegative=True)
        return out

    def as_dict(self):
        return asdict(self)


@dataclass
class LabBlanks:
    """Total procedural Pb and U blank (pg ± 1σ %) and Pb blank composition."""
    Pb_blank_total: float = 0.0
    Pb_blank_total_std_rel: float = 0.0
    U_blank_total: float = 0.0
    U_blank_total_std_rel: float = 0.0
    R64b: float = 18.0
    R64b_std_rel: float = 0.0
    R74b: float = 15.5
    R74b_std_rel: float = 0.0
    R84b: float = 37.5
    R84b_std_rel: float = 0.0
    rho_6474_b: float = 0.0
    rho_6484_b: float = 0.0

    def problems(self):
        out = []
        _check(out, "Pb blank (pg)", self.Pb_blank_total, nonnegative=True)
        _check(out, "Pb blank uncertainty (%)", self.Pb_blank_total_std_rel, nonnegative=True)
        _check(out, "U blank (pg)", self.U_blank_total, nonnegative=True)
        _check(out, "U blank uncertainty (%)", self.U_blank_total_std_rel, nonnegative=True)
        for ratio, label in (("R64b", "206Pb/204Pb"), ("R74b", "207Pb/204Pb"),
                             ("R84b", "208Pb/204Pb")):
            _check(out, f"Blank {label}", getattr(self, ratio), positive=True)
            _check(out, f"Blank {label} uncertainty (%)", getattr(self, ratio + "_std_rel"),
                   nonnegative=True)
        _check(out, "Blank correlation 206/204 vs 207/204", self.rho_6474_b, rho=True)
        _check(out, "Blank correlation 206/204 vs 208/204", self.rho_6484_b, rho=True)
        return out

    def as_dict(self):
        return asdict(self)


@dataclass
class CommonPb:
    """Initial common Pb: explicit ratios, or Stacey-Kramers (1975) at an age.

    `model` is 'explicit' (use R64c, R74c, R84c) or 'stacey_kramers' (ratios
    from `utils.SK75(age_Ga)`; R64c/R74c/R84c are then ignored). Relative
    errors (1σ %) and correlations are always supplied by the user.
    """
    model: str = "explicit"
    R64c: float | None = None
    R74c: float | None = None
    R84c: float | None = None
    age_Ga: float | None = None
    R64c_std_rel: float = 0.0
    R74c_std_rel: float = 0.0
    R84c_std_rel: float = 0.0
    rho_6474_c: float = 0.0
    rho_6484_c: float = 0.0

    def ratios(self):
        """(206/204, 207/204, 208/204) of the initial Pb in use."""
        if self.model == "stacey_kramers":
            return tuple(float(r) for r in SK75(self.age_Ga))
        return self.R64c, self.R74c, self.R84c

    def problems(self):
        out = []
        if self.model == "explicit":
            for ratio, label in (("R64c", "206Pb/204Pb"), ("R74c", "207Pb/204Pb"),
                                 ("R84c", "208Pb/204Pb")):
                _check(out, f"Initial Pb {label}", getattr(self, ratio), positive=True)
        elif self.model == "stacey_kramers":
            _check(out, "Stacey-Kramers age (Ga)", self.age_Ga, nonnegative=True)
            if _number(self.age_Ga) and self.age_Ga > 4.57:
                out.append(f"Stacey-Kramers age must be at most 4.57 Ga (got {self.age_Ga!r}).")
        else:
            out.append(f"Initial Pb model must be 'explicit' or 'stacey_kramers' "
                       f"(got {self.model!r}).")
        for ratio, label in (("R64c", "206Pb/204Pb"), ("R74c", "207Pb/204Pb"),
                             ("R84c", "208Pb/204Pb")):
            _check(out, f"Initial Pb {label} uncertainty (%)", getattr(self, ratio + "_std_rel"),
                   nonnegative=True)
        _check(out, "Initial Pb correlation 206/204 vs 207/204", self.rho_6474_c, rho=True)
        _check(out, "Initial Pb correlation 206/204 vs 208/204", self.rho_6484_c, rho=True)
        return out

    def as_dict(self):
        """The `Pbc` dictionary `load_grains` takes."""
        r64, r74, r84 = self.ratios()
        return dict(R64c=r64, R64c_std_rel=self.R64c_std_rel,
                    R74c=r74, R74c_std_rel=self.R74c_std_rel,
                    R84c=r84, R84c_std_rel=self.R84c_std_rel,
                    rho_6474_c=self.rho_6474_c, rho_6484_c=self.rho_6484_c)


@dataclass
class ThCorrection:
    """230Th disequilibrium correction.

    `kind` is None (no correction), 'D' (D_Th_U ± absolute, optional
    Th_U_magma ±) or 'magma' (Th_U_magma ± absolute, with Th/U of the
    fraction from 208Pb*).
    Th_U_magma is the atomic Th/U of the melt relative to total U, as in the BSU sheets.
    """
    kind: str | None = None
    D_Th_U: float | None = None
    D_Th_U_std: float | None = None
    Th_U_magma: float | None = None
    Th_U_magma_std: float | None = None

    def problems(self):
        out = []
        if self.kind is None:
            return out
        if self.kind == "D":
            _check(out, "D(Th/U)", self.D_Th_U, positive=True)
            _check(out, "D(Th/U) uncertainty", self.D_Th_U_std, nonnegative=True)
            _check(out, "Th/U of the magma", self.Th_U_magma, positive=True, optional=True)
            _check(out, "Th/U of the magma uncertainty", self.Th_U_magma_std, nonnegative=True,
                   optional=True)
        elif self.kind == "magma":
            _check(out, "Th/U of the magma", self.Th_U_magma, positive=True)
            _check(out, "Th/U of the magma uncertainty", self.Th_U_magma_std, nonnegative=True)
        else:
            out.append(f"Th correction must be none, 'D' or 'magma' (got {self.kind!r}).")
        return out

    def as_dict(self):
        """The `Th_corrections` dictionary `load_grains` takes, or None."""
        if self.kind is None:
            return None
        names = ("D_Th_U", "D_Th_U_std", "Th_U_magma", "Th_U_magma_std") if self.kind == "D" \
            else ("Th_U_magma", "Th_U_magma_std")
        out = {"Th230_correction_type": self.kind}
        out.update({n: getattr(self, n) for n in names if getattr(self, n) is not None})
        return out


@dataclass
class ReductionSettings:
    """All reduction settings besides the fraction table."""
    fractionation: Fractionation = field(default_factory=Fractionation)
    lab_blanks: LabBlanks = field(default_factory=LabBlanks)
    common_pb: CommonPb = field(default_factory=CommonPb)
    th_correction: ThCorrection = field(default_factory=ThCorrection)
    spike_version: str | None = None
    strict_covariance: bool = True

    @property
    def decay_constants(self):
        """Decay constants in use, read-only (see module `decay_constants`)."""
        return decay_constants()

    def problems(self):
        """Every problem as a readable sentence; empty when the settings are valid."""
        out = (self.fractionation.problems() + self.lab_blanks.problems()
               + self.common_pb.problems() + self.th_correction.problems())
        if self.spike_version is not None and (not isinstance(self.spike_version, str)
                                               or not self.spike_version.strip()):
            out.append(f"Tracer version must be empty or a name such as 'v3' "
                       f"(got {self.spike_version!r}).")
        if not isinstance(self.strict_covariance, bool):
            out.append("Strict covariance must be true or false.")
        return out

    def validate(self):
        """Raise `SettingsError` listing every problem, if there are any."""
        problems = self.problems()
        if problems:
            raise SettingsError("\n".join(problems))

    def load_grains_arguments(self):
        """Return `((fractionation_factors, lab_blanks, Pbc, Th_corrections), kwargs)`.

        Use as ``load_grains(data, *args, **kwargs)``; kwargs holds
        `spike_version` and `strict_covariance`.
        """
        self.validate()
        args = (self.fractionation.as_dict(), self.lab_blanks.as_dict(),
                self.common_pb.as_dict(), self.th_correction.as_dict())
        return args, dict(spike_version=self.spike_version,
                          strict_covariance=self.strict_covariance)

    @classmethod
    def from_dicts(cls, fractionation_factors, lab_blanks, Pbc, Th_corrections=None, *,
                   spike_version=None, strict_covariance=True):
        """Build settings from the four notebook dictionaries `load_grains` takes."""
        th = dict(Th_corrections or {})
        kind = th.pop("Th230_correction_type", None)
        # The demo notebook passes a_Th230_U238 = 1.0, which load_grains
        # ignores. Accept that value; reject others, which the engine cannot honour.
        activity = th.pop("a_Th230_U238", 1.0)
        if not (_number(activity) and activity == 1.0):
            raise SettingsError("Th correction: a_Th230_U238 other than 1.0 is not supported "
                                f"by the engine (got {activity!r}).")
        return cls(
            fractionation=_from_mapping(Fractionation, dict(fractionation_factors),
                                        "fractionation"),
            lab_blanks=_from_mapping(LabBlanks, dict(lab_blanks), "lab_blanks"),
            common_pb=_from_mapping(CommonPb, dict(Pbc, model="explicit"), "common Pb"),
            th_correction=_from_mapping(ThCorrection, dict(th, kind=kind), "Th correction"),
            spike_version=spike_version, strict_covariance=strict_covariance)

    def to_dict(self):
        """Plain JSON-ready dict with `format` and `version` keys."""
        return {"format": FORMAT, "version": VERSION,
                "fractionation": asdict(self.fractionation),
                "lab_blanks": asdict(self.lab_blanks),
                "common_pb": asdict(self.common_pb),
                "th_correction": asdict(self.th_correction),
                "spike_version": self.spike_version,
                "strict_covariance": self.strict_covariance}

    @classmethod
    def from_dict(cls, data):
        """Inverse of `to_dict`; rejects other formats and unknown major versions."""
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise SettingsError("This is not an ID-TIMS reduction settings file "
                                f"(expected format '{FORMAT}').")
        version = data.get("version")
        major = str(version).split(".")[0] if version is not None else ""
        if major != str(VERSION):
            raise SettingsError(f"Settings version {version!r} is not supported; this version "
                                f"of IDTIMS_UPbRPy reads version {VERSION}. "
                                "Update IDTIMS_UPbRPy to open it.")
        known = {"format", "version", "fractionation", "lab_blanks", "common_pb",
                 "th_correction", "spike_version", "strict_covariance"}
        unknown = sorted(set(data) - known)
        if unknown:
            raise SettingsError("Settings have unknown entries: " + ", ".join(unknown) + ".")
        return cls(
            fractionation=_from_mapping(Fractionation, data.get("fractionation", {}),
                                        "fractionation"),
            lab_blanks=_from_mapping(LabBlanks, data.get("lab_blanks", {}), "lab_blanks"),
            common_pb=_from_mapping(CommonPb, data.get("common_pb", {}), "common_pb"),
            th_correction=_from_mapping(ThCorrection, data.get("th_correction", {}),
                                        "th_correction"),
            spike_version=data.get("spike_version"),
            strict_covariance=data.get("strict_covariance", True))
