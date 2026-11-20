"""ReductionSettings: JSON round trips, validation and identical reductions."""
import json
import math
import unittest
import warnings

import pandas as pd

from IDTIMS_UPbRPy import constants, load_grains, utils
from IDTIMS_UPbRPy.settings import (CommonPb, ReductionSettings, SettingsError, ThCorrection,
                                    decay_constants)
from snapshot_support import B, C, EXAMPLE, F, VARIANTS, grain_numbers


def same_numbers(a, b):
    """Exact equality of two grain_numbers dicts, NaN equal to NaN."""
    if a.keys() != b.keys():
        return False
    for key in a:
        x, y = a[key], b[key]
        if isinstance(x, list):
            if json.dumps(x) != json.dumps(y):
                return False
        elif not (x == y or (math.isnan(x) and math.isnan(y))):
            return False
    return True


class RoundTripTests(unittest.TestCase):
    def test_default_round_trip(self):
        settings = ReductionSettings()
        text = json.dumps(settings.to_dict())
        self.assertEqual(ReductionSettings.from_dict(json.loads(text)), settings)

    def test_legacy_dicts_round_trip(self):
        for th in VARIANTS.values():
            settings = ReductionSettings.from_dicts(F, B, C, th, spike_version="v1",
                                                    strict_covariance=False)
            back = ReductionSettings.from_dict(json.loads(json.dumps(settings.to_dict())))
            self.assertEqual(back, settings)
            (f, b, c, t), kwargs = back.load_grains_arguments()
            self.assertEqual((f, b, c, t), (F, B, C, th))
            self.assertEqual(kwargs, dict(spike_version="v1", strict_covariance=False))

    def test_stacey_kramers_round_trip(self):
        settings = ReductionSettings(common_pb=CommonPb(model="stacey_kramers", age_Ga=0.6,
                                                        R64c_std_rel=1.0, R74c_std_rel=0.5,
                                                        R84c_std_rel=1.0, rho_6474_c=0.9))
        back = ReductionSettings.from_dict(json.loads(json.dumps(settings.to_dict())))
        self.assertEqual(back, settings)
        (_, _, pbc, _), _ = back.load_grains_arguments()
        self.assertEqual((pbc["R64c"], pbc["R74c"], pbc["R84c"]),
                         tuple(float(r) for r in utils.SK75(0.6)))
        self.assertEqual(pbc["R74c_std_rel"], 0.5)

    def test_unknown_major_version_rejected(self):
        data = ReductionSettings().to_dict()
        data["version"] = 2
        with self.assertRaisesRegex(SettingsError, "version 2 is not supported"):
            ReductionSettings.from_dict(data)
        data["version"] = "1.3"
        ReductionSettings.from_dict(data)

    def test_wrong_format_and_unknown_keys(self):
        with self.assertRaisesRegex(SettingsError, "not an ID-TIMS reduction settings"):
            ReductionSettings.from_dict({"format": "other", "version": 1})
        data = ReductionSettings().to_dict()
        data["lab_blanks"]["Pb_blank"] = 1
        with self.assertRaisesRegex(SettingsError, "unknown entries: Pb_blank"):
            ReductionSettings.from_dict(data)
        # The demo notebook's Th dict carries a_Th230_U238 = 1.0 (ignored by load_grains).
        demo = ReductionSettings.from_dicts(F, B, C, dict(VARIANTS["th_D"], a_Th230_U238=1.0))
        self.assertEqual(demo.th_correction.kind, "D")
        with self.assertRaisesRegex(SettingsError, "a_Th230_U238"):
            ReductionSettings.from_dicts(F, B, C, dict(VARIANTS["th_D"], a_Th230_U238=0.8))


class ValidationTests(unittest.TestCase):
    def test_messages_are_readable(self):
        settings = ReductionSettings.from_dicts(F, dict(B, Pb_blank_total=-1, rho_6474_b=1.5), C)
        settings.th_correction = ThCorrection(kind="magma")
        problems = settings.problems()
        self.assertIn("Pb blank (pg) cannot be negative (got -1).", problems)
        self.assertIn("Blank correlation 206/204 vs 207/204 must lie between -1 and 1 (got 1.5).",
                      problems)
        self.assertIn("Th/U of the magma is missing.", problems)
        with self.assertRaises(SettingsError) as caught:
            settings.load_grains_arguments()
        self.assertEqual(str(caught.exception).count("\n"), len(problems) - 1)

    def test_th_kinds(self):
        self.assertIsNone(ThCorrection().as_dict())
        self.assertIn("must be none, 'D' or 'magma'", ThCorrection(kind="x").problems()[0])
        sk = CommonPb(model="stacey_kramers", age_Ga=5.0)
        self.assertTrue(any("at most 4.57 Ga" in p for p in sk.problems()))

    def test_decay_constants_read_only(self):
        shown = ReductionSettings().decay_constants
        self.assertEqual(shown["lambda_238"], constants.lambda_238)
        self.assertEqual(decay_constants()["lambda_230"], constants.lambda_230)
        with self.assertRaises(TypeError):
            shown["lambda_238"] = 1.0


class ReductionIdentityTests(unittest.TestCase):
    def test_settings_reduce_identically(self):
        data = pd.read_csv(EXAMPLE)
        for key, th in VARIANTS.items():
            settings = ReductionSettings.from_dicts(F, B, C, th, strict_covariance=False)
            settings = ReductionSettings.from_dict(json.loads(json.dumps(settings.to_dict())))
            args, kwargs = settings.load_grains_arguments()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                expected = load_grains(data, F, B, C, th, strict_covariance=False)
                actual = load_grains(data, *args, **kwargs)
            for e, a in zip(expected, actual):
                with self.subTest(variant=key, grain=e.id):
                    self.assertTrue(same_numbers(grain_numbers(e), grain_numbers(a)))


if __name__ == "__main__":
    unittest.main()
