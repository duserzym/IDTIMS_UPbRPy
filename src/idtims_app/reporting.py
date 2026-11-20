"""App export policy over the unchanged engine's report writers."""
import csv
import math
from itertools import groupby

from IDTIMS_UPbRPy import export
from IDTIMS_UPbRPy.fractions import OXIDE, OXIDE_FORMULA, write_fractions

DIAGNOSTIC_NOTE = ("Diagnostic covariance mode: impossible covariances may have been replaced "
                   "with zero; uncertainties are not certified.")


def ratio_provenance(table, fraction_ids):
    """Group only the exported fractions, retaining values and block distinctions."""
    oxide, statistics, values, blocks = {}, {}, {}, {}
    rows = table.frame.set_index("Fraction ID")
    for fid in fraction_ids:
        row = rows.loc[fid]
        value = row.get(OXIDE)
        missing = value is None or math.isnan(float(value))
        if missing:
            formula = "none confirmed" if fid in table.no_oxide_confirmed else "missing"
        else:
            formula = row.get(OXIDE_FORMULA) or "missing"
            values[fid] = float(value)
        oxide.setdefault(formula, []).append(fid)
        blocks[fid] = {block: table.mean_statistic(fid, block) for block in ("Pb", "U")}
        for statistic in dict.fromkeys(blocks[fid].values()):
            statistics.setdefault(statistic, []).append(fid)
    return dict(oxide=oxide, mean_statistics=statistics, oxide_values=values,
                mean_statistic_blocks=blocks)


def bsu(session, *, th_corrected=None, discordance=False, include_off=False):
    if not session.reduction_current:
        raise ValueError("Reduce the current inputs before exporting results.")
    if th_corrected is None:
        th_corrected = session.th_correction_applied
    grains = [g for g in session.reduction.grains if include_off or session.is_included(g.id)]
    table = export.bsu_table(grains, identifiers=session.fraction_identifiers(),
                             th_corrected_dates=th_corrected,
                             th_corrected_ratios=th_corrected,
                             include_discordance=discordance)
    notes = export.footnotes(session.settings, grains=grains,
                            th_corrected_dates=th_corrected, th_corrected_ratios=th_corrected,
                            **ratio_provenance(session.table, [g.id for g in grains]))
    if not session.reduction.strict:
        notes.insert(10, ("", DIAGNOSTIC_NOTE))
    notes = [(chr(ord("a") + i), text) for i, (_, text) in enumerate(notes)]
    return table, notes


def save(session, path, kind, **options):
    if kind in ("bsu_csv", "bsu_xlsx"):
        table, notes = bsu(session, **options)
        if kind == "bsu_csv":
            export.write_csv(table, path)
            with open(path, "a", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow([])
                writer.writerows([(f"({letter})", text) for letter, text in notes])
        else:
            export.write_xlsx(table, notes, path)
            # Engine writer supplies the exact numbers, three header rows and notes.
            # Merge contiguous group cells here, keeping openpyxl optional to the engine.
            from openpyxl import load_workbook
            book = load_workbook(path)
            sheet = book.active
            groups = export.with_groups(table).columns.get_level_values(0)
            start = 1
            for name, columns in groupby(groups):
                count = len(list(columns))
                if name and count > 1:
                    sheet.merge_cells(start_row=1, end_row=1,
                                      start_column=start, end_column=start + count - 1)
                start += count
            sheet.freeze_panes = "C4"
            book.save(path)
    elif kind == "full":
        if not session.reduction_current:
            raise ValueError("Reduce the current inputs before exporting results.")
        export.write_csv(export.full_table(session.reduction.grains), path)
    elif kind == "fractions":
        write_fractions(session.table, path)
    else:
        raise ValueError(f"Unknown export kind {kind!r}.")
    session.export_saved_revision = session.revision
