"""Fraction files: contract and legacy reading, merging, writing and mapping."""
import io
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np

from IDTIMS_UPbRPy import load_grains
from IDTIMS_UPbRPy.fractions import (CONTRACT, FractionFileError, read_fractions,
                                     write_fractions)
from snapshot_support import B, C, EXAMPLE, F, ROOT, VARIANTS, reduce_variants

DATA = ROOT / "tests" / "data"
PB_ONLY = DATA / "synthetic_pb_only.fractions.csv"
U_ONLY = DATA / "synthetic_u_only.fractions.csv"
COMPARED = ["t68", "t76", "t68_std", "t76_std", "R68r", "R75r", "R76r"]


def stream(text, name=None):
    """An in-memory file; with `name`, a bytes stream whose name errors can cite."""
    if not name:
        return io.StringIO(text)
    s = io.BytesIO(text.encode("utf-8"))
    s.name = name
    return s


class TempFiles:
    """A temporary directory removed when the test ends."""
    def __init__(self, test):
        directory = tempfile.TemporaryDirectory()
        test.addCleanup(directory.cleanup)
        self.dir = directory

    def write(self, name, text):
        path = Path(self.dir.name) / name
        path.write_text(text, encoding="utf-8")
        return path


class LegacyTests(unittest.TestCase):
    def test_legacy_read(self):
        table = read_fractions(EXAMPLE)
        self.assertEqual(table.source_kinds, {str(EXAMPLE): "legacy"})
        self.assertEqual(table.fraction_ids[:3], ["z1", "z2", "z3"])
        self.assertEqual(len(table.fraction_ids), 12)
        self.assertEqual(table.frame.loc[0, "206Pb/204Pb Mean"], 833.333333333)
        self.assertEqual(set(table.frame["Contract"]), {CONTRACT})
        kinds = {i.kind for i in table.issues()}
        self.assertEqual(kinds, {"missing_oxide", "cycle_selection_note"})

    def test_legacy_reduces_exactly_like_snapshot(self):
        expected = reduce_variants()
        data, columns = read_fractions(EXAMPLE).load_grains_frame()
        self.assertEqual(columns["id"], "Fraction ID")
        for key, th in VARIANTS.items():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                grains = load_grains(data, F, B, C, th, strict_covariance=False, **columns)
            self.assertEqual(sorted(str(g.id) for g in grains), sorted(expected[key]))
            for g in grains:
                for name in COMPARED:
                    with self.subTest(variant=key, grain=g.id, attr=name):
                        self.assertEqual(float(getattr(g, name)), expected[key][str(g.id)][name])

    def test_legacy_without_grain_id(self):
        with self.assertRaisesRegex(FractionFileError, "no 'Grain ID' column"):
            read_fractions(stream("Fraction ID,Sample\nz1,A\n"))


class ContractTests(unittest.TestCase):
    def test_merge_pb_and_u_only(self):
        pb, u = read_fractions(PB_ONLY), read_fractions(U_ONLY)
        self.assertEqual({i.kind for i in pb.issues()},
                         {"missing_block", "unsupported_correlation", "cycle_selection_note"})
        self.assertEqual(pb.reducible_ids(), [])
        self.assertIn("missing_setup", {i.kind for i in u.issues()})
        table = read_fractions(PB_ONLY, U_ONLY)
        self.assertEqual(table.fraction_ids, ["z1", "z2"])
        self.assertEqual(table.reducible_ids(require_oxide=True), ["z1", "z2"])
        self.assertEqual(table.frame.loc[0, "U Oxide 18O/16O"], 0.00206)
        self.assertEqual(table.frame.loc[0, "Pb Cycles Used"], "120")
        # The merged pair reduces like the legacy rows.
        data, columns = table.load_grains_frame()
        legacy, legacy_columns = read_fractions(EXAMPLE).load_grains_frame()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            a = load_grains(data, F, B, C, None, strict_covariance=False, **columns)
            b = load_grains(legacy.iloc[:2], F, B, C, None, strict_covariance=False,
                            **legacy_columns)
        self.assertEqual([g.t68 for g in a], [g.t68 for g in b])

    def test_conflict_names_fraction_column_and_files(self):
        files = TempFiles(self)
        other = files.write("other.fractions.csv",
                            f"Contract,Fraction ID,Sample\n{CONTRACT},z1,SYN-2\n")
        with self.assertRaises(FractionFileError) as caught:
            read_fractions(U_ONLY, other)
        message = str(caught.exception)
        for part in ("'z1'", "'Sample'", "synthetic_u_only.fractions.csv", "other.fractions.csv",
                     "'SYN-1'", "'SYN-2'"):
            self.assertIn(part, message)

    def test_equal_numbers_merge(self):
        files = TempFiles(self)
        a = files.write("a.csv", f"Contract,Fraction ID,Spike Weight (g)\n{CONTRACT},z1,0.0152\n")
        b = files.write("b.csv",
                        f"Contract,Fraction ID,Spike Weight (g)\n{CONTRACT},z1,1.52e-2\n")
        self.assertEqual(read_fractions(a, b).frame.loc[0, "Spike Weight (g)"], 0.0152)

    def test_duplicate_in_one_file(self):
        text = f"Contract,Fraction ID\n{CONTRACT},z1\n{CONTRACT},z1\n"
        with self.assertRaisesRegex(FractionFileError, "'z1' appears more than once"):
            read_fractions(stream(text, "dup.csv"))

    def test_unknown_version(self):
        with self.assertRaisesRegex(FractionFileError, "idtims-fractions/2.*Update"):
            read_fractions(stream("Contract,Fraction ID\nidtims-fractions/2,z1\n"))
        with self.assertRaisesRegex(FractionFileError, "unknown contract"):
            read_fractions(stream("Contract,Fraction ID\nsomething/1,z1\n"))
        with self.assertRaisesRegex(FractionFileError, "'Contract' is empty"):
            read_fractions(stream("Contract,Fraction ID\n,z1\n"))

    def test_bom_tolerated(self):
        text = "﻿" + PB_ONLY.read_text(encoding="utf-8")
        table = read_fractions(io.BytesIO(text.encode("utf-8")))
        self.assertEqual(table.fraction_ids, ["z1", "z2"])
        self.assertIn("Contract", table.frame.columns)

    def test_not_a_number(self):
        text = f"Contract,Fraction ID,206Pb/205Pb Mean\n{CONTRACT},z1,abc\n"
        with self.assertRaisesRegex(FractionFileError, "z1.*206Pb/205Pb Mean.*not a number"):
            read_fractions(stream(text))

    def test_2535_inferred_needs_confirmation(self):
        text = (f"Contract,Fraction ID,202Pb/205Pb Mean,202Pb/205Pb % Standard Error\n"
                f"{CONTRACT},z1,0.5,0.01\n")
        table = read_fractions(stream(text))
        self.assertEqual(table.inferred_spike_types, {"z1": "2535"})
        self.assertNotIn("Spike Type", table.frame.columns)
        self.assertIn("unconfirmed_spike_type", {i.kind for i in table.issues("z1")})
        self.assertEqual(table.reducible_ids(), [])
        out = io.StringIO()
        write_fractions(table, out)
        self.assertNotIn("2535", out.getvalue())  # not decided silently
        table.confirm_spike_type("z1")
        self.assertEqual(table.frame.loc[0, "Spike Type"], "2535")
        self.assertNotIn("unconfirmed_spike_type", {i.kind for i in table.issues("z1")})
        self.assertNotIn("Collector", [c for i in table.issues("z1") for c in i.columns])


class WriteTests(unittest.TestCase):
    def test_full_precision_round_trip(self):
        files = TempFiles(self)
        table = read_fractions(PB_ONLY, U_ONLY)
        table.frame.loc[0, "206Pb/205Pb Mean"] = 0.1 + 0.2
        table.frame.loc[1, "206Pb/205Pb Mean"] = 1 / 3
        table.frame.loc[1, "Spike Weight (g)"] = 1.2345678901234567e-17
        path = files.dir.name + "/out.fractions.csv"
        write_fractions(table, path)
        back = read_fractions(path)
        self.assertEqual(list(back.frame.columns), list(read_fractions(path).frame.columns))
        self.assertEqual(set(back.frame.columns), set(table.frame.columns))
        for column in table.frame.columns:
            for i in range(2):
                a, b = table.frame.loc[i, column], back.frame.loc[i, column]
                same = a == b or (a is None and b is None) or (
                    isinstance(a, float) and np.isnan(a) and np.isnan(b))
                self.assertTrue(same, (column, a, b))
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("0.30000000000000004", text)
        self.assertTrue(all(line.startswith(CONTRACT) for line in text.splitlines()[1:]))

    def test_unknown_columns_preserved(self):
        out = io.StringIO()
        write_fractions(read_fractions(PB_ONLY), out)
        back = read_fractions(io.StringIO(out.getvalue()))
        self.assertEqual(list(back.frame["Lab Note"]), ["first", None])
        self.assertEqual(out.getvalue().splitlines()[0].split(",")[-1], "Lab Note")

    def test_legacy_written_as_contract(self):
        out = io.StringIO()
        write_fractions(read_fractions(EXAMPLE), out)
        header = out.getvalue().splitlines()[0]
        self.assertTrue(header.startswith("Contract,Fraction ID,"))
        self.assertNotIn("Grain ID", header)


class CovarianceTests(unittest.TestCase):
    def test_supported_pairs(self):
        table = read_fractions(PB_ONLY, U_ONLY)
        row = table.frame.iloc[0]
        overrides = table.covariance_overrides("z1")
        s65 = row["206Pb/205Pb Mean"] * row["206Pb/205Pb % Standard Error"] / 100
        s46 = (1 / row["206Pb/204Pb Mean"]) * row["206Pb/204Pb % Standard Error"] / 100
        s85 = row["238U/235U Mean"] * row["238U/235U % Standard Error"] / 100
        s35 = row["233U/235U Mean"] * row["233U/235U % Standard Error"] / 100
        self.assertEqual(set(overrides), {("Pb_R46m", "Pb_R65m"), ("U_R35m", "U_R85m")})
        # 206/204 is the reciprocal of the engine's 204/206: the sign flips.
        self.assertAlmostEqual(overrides["Pb_R46m", "Pb_R65m"], -0.25 * s65 * s46, delta=1e-30)
        self.assertAlmostEqual(overrides["U_R35m", "U_R85m"], -0.125 * s85 * s35, delta=1e-30)
        self.assertNotIn(("Pb_R46m", "Pb_R65m"), table.covariance_overrides("z2"))
        unsupported = [i for i in table.issues() if i.kind == "unsupported_correlation"]
        self.assertEqual({i.columns for i in unsupported}, {("rho 206Pb/205Pb|207Pb/205Pb",)})
        self.assertIn("207Pb/205Pb", unsupported[0].message)
        self.assertFalse(unsupported[0].blocking)

    def test_overrides_reach_engine(self):
        table = read_fractions(PB_ONLY, U_ONLY)
        data, columns = table.load_grains_frame()
        overrides = table.covariance_overrides("z1")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            grain = load_grains(data.iloc[:1], F, B, C, None, strict_covariance=False,
                                covariance_overrides=overrides, **columns)[0]
        names = grain.input_covariance_names
        i, j = names.index("U_R85m"), names.index("U_R35m")
        self.assertEqual(grain.input_covariance[i, j], overrides["U_R35m", "U_R85m"])

    def test_unsupported_pairs_listed(self):
        cols = ["206Pb/204Pb", "206Pb/205Pb", "238U/235U", "238U/233U"]
        header = ",".join(f"{c} Mean,{c} % Standard Error" for c in cols)
        values = ",".join("2.0,0.1" for _ in cols)
        rhos = ["rho 206Pb/205Pb|238U/235U", "rho 206Pb/204Pb|204Pb/206Pb",
                "rho 238U/235U|238U/233U", "rho 206Pb/205Pb|999Xx/205Pb"]
        text = (f"Contract,Fraction ID,{header},{','.join(rhos)}\n"
                f"{CONTRACT},z1,{values},0.1,0.2,0.3,0.4\n")
        table = read_fractions(stream(text))
        self.assertEqual(table.covariance_overrides("z1"), {})
        messages = {i.columns[0]: i.message for i in table.issues()
                    if i.kind == "unsupported_correlation"}
        self.assertEqual(set(messages), set(rhos))
        self.assertIn("not measured in the same cycles", messages[rhos[0]])
        self.assertIn("same ratio", messages[rhos[1]])
        self.assertIn("derived ratios", messages[rhos[2]])
        self.assertIn("unknown ratio", messages[rhos[3]])

    def test_rho_out_of_range(self):
        text = f"Contract,Fraction ID,rho 206Pb/205Pb|208Pb/205Pb\n{CONTRACT},z1,1.5\n"
        with self.assertRaisesRegex(FractionFileError, "between -1 and 1"):
            read_fractions(stream(text))


if __name__ == "__main__":
    unittest.main()


class OxideFormulaTests(unittest.TestCase):
    """Clarification 6: U Oxide Formula is required whenever U Oxide 18O/16O is filled."""

    def test_fixture_formula_is_accepted(self):
        table = read_fractions(PB_ONLY, U_ONLY)
        kinds = {issue.kind for issue in table.issues("z1")}
        self.assertNotIn("oxide_formula", kinds)
        notes = [i for i in table.issues("z1") if i.kind == "oxide_formula_note"]
        self.assertEqual(len(notes), 1)            # instrument-corrected rows carry a note
        self.assertEqual(notes[0].message,
                         "z1: U ratios arrived already oxide-corrected in the raw file "
                         "(18O/16O = 0.00206 from the function names); the writer did not "
                         "recompute them and the formula is not recorded.")
        self.assertFalse(notes[0].blocking)
        self.assertIn("z1", table.reducible_ids(require_oxide=True))

    def test_missing_or_unknown_formula_is_an_issue(self):
        files = TempFiles(self)
        text = U_ONLY.read_text(encoding="utf-8")
        for replacement in ("", "my_formula"):
            path = files.write(f"u_{replacement or 'empty'}.fractions.csv",
                               text.replace(",instrument,", f",{replacement},"))
            table = read_fractions(PB_ONLY, path)
            issues = [i for i in table.issues("z1") if i.kind == "oxide_formula"]
            self.assertEqual(len(issues), 1, replacement)
            self.assertIn("U Oxide Formula", issues[0].message)
            self.assertNotIn("z1", table.reducible_ids(require_oxide=True))
            self.assertIn("z1", table.reducible_ids(require_oxide=False))

    def test_mixed_formulas_for_one_fraction_refuse_to_merge(self):
        files = TempFiles(self)
        text = U_ONLY.read_text(encoding="utf-8")
        other = files.write("u_iso.fractions.csv", text.replace(",instrument,", ",isobar_233_18O,"))
        with self.assertRaisesRegex(FractionFileError, "U Oxide Formula"):
            read_fractions(U_ONLY, other)

    def test_java_tripoli_form_gets_a_visible_note(self):
        files = TempFiles(self)
        text = U_ONLY.read_text(encoding="utf-8")
        path = files.write("u_java.fractions.csv",
                           text.replace(",instrument,", ",tripoli_java_00dc941,"))
        table = read_fractions(PB_ONLY, path)
        notes = [i for i in table.issues("z1") if i.kind == "oxide_formula_note"]
        self.assertEqual(len(notes), 1)
        self.assertFalse(notes[0].blocking)
        self.assertIn("z1", table.reducible_ids(require_oxide=True))

class MeanStatisticTests(unittest.TestCase):
    def test_missing_is_arithmetic(self):
        table = read_fractions(PB_ONLY, U_ONLY)
        for block in ("Pb", "U"):
            self.assertEqual(table.mean_statistic("z1", block), "arithmetic")
        self.assertFalse(any(i.kind == "mean_statistic_note" for i in table.issues()))

    def test_unknown_is_blocking_and_names_allowed_values(self):
        table = read_fractions(PB_ONLY, U_ONLY)
        for block in ("Pb", "U"):
            column = f"{block} Mean Statistic"
            table._set("z1", column, "median")
            issues = [i for i in table.issues("z1") if i.kind == "invalid_value"
                      and column in i.columns]
            self.assertEqual(len(issues), 1)
            self.assertTrue(issues[0].blocking)
            for word in (column, "arithmetic", "geometric"):
                self.assertIn(word, issues[0].message)
            self.assertNotIn("z1", table.reducible_ids())
            with self.assertRaisesRegex(ValueError, column):
                table.mean_statistic("z1", block)

    def test_geometric_notes_and_round_trip(self):
        table = read_fractions(PB_ONLY, U_ONLY)
        for block in ("Pb", "U"):
            table._set("z1", f"{block} Mean Statistic", "geometric")
            self.assertEqual(table.mean_statistic("z1", block), "geometric")
        notes = [i for i in table.issues("z1") if i.kind == "mean_statistic_note"]
        self.assertEqual(len(notes), 2)
        for block, note in zip(("Pb", "U"), notes):
            self.assertFalse(note.blocking)
            self.assertEqual(note.message,
                             f"z1: {block} ratios are geometric means with geometric % standard "
                             "errors (Java Tripoli); legacy Tripoli and existing BSU sheets "
                             "use arithmetic statistics.")
        self.assertIn("z1", table.reducible_ids())
        buffer = io.StringIO()
        write_fractions(table, buffer)
        back = read_fractions(stream(buffer.getvalue()))
        for block in ("Pb", "U"):
            self.assertIn(f"{block} Mean Statistic", back.frame.columns)
            self.assertEqual(back.mean_statistic("z1", block), "geometric")

    def test_different_nonempty_statistics_conflict_on_merge(self):
        for block in ("Pb", "U"):
            column = f"{block} Mean Statistic"
            header = f"Contract,Fraction ID,{column}\n"
            with self.assertRaisesRegex(FractionFileError, column):
                read_fractions(stream(header + f"{CONTRACT},z1,arithmetic\n", "first.csv"),
                               stream(header + f"{CONTRACT},z1,geometric\n", "second.csv"))


class CycleSelectionTests(unittest.TestCase):
    """Clarification 8: Pb/U Cycle Selection (shared, per_ratio, or unknown)."""

    def table_with(self, value):
        files = TempFiles(self)
        text = U_ONLY.read_text(encoding="utf-8").splitlines()
        header = text[0] + ",U Cycle Selection"
        rows = [line + "," + value for line in text[1:]]
        path = files.write("u_sel.fractions.csv", "\n".join([header] + rows) + "\n")
        return read_fractions(PB_ONLY, path)

    def notes(self, table, block):
        return [i for i in table.issues("z1") if i.kind == "cycle_selection_note"
                and i.columns == (f"{block} Cycle Selection",)]

    def test_shared_has_no_note(self):
        self.assertEqual(self.notes(self.table_with("shared"), "U"), [])

    def test_per_ratio_and_missing_get_notes(self):
        per_ratio = self.notes(self.table_with("per_ratio"), "U")
        self.assertEqual(len(per_ratio), 1)
        self.assertIn("own accepted-cycle mask", per_ratio[0].message)
        self.assertFalse(per_ratio[0].blocking)
        unknown = self.notes(read_fractions(PB_ONLY, U_ONLY), "Pb")
        self.assertEqual(len(unknown), 1)
        self.assertIn("not recorded", unknown[0].message)

    def test_unknown_value_blocks(self):
        table = self.table_with("sometimes")
        issues = [i for i in table.issues("z1") if i.kind == "invalid_value"]
        self.assertTrue(any("U Cycle Selection" in i.message for i in issues))
        self.assertNotIn("z1", table.reducible_ids())
