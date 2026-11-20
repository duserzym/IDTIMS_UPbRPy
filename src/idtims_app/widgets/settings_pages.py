"""Steps 3 to 5: Fractionation, Blanks and common Pb, Th correction.

All three edit the one `ReductionSettings` held by the session. Validation
messages from `problems()` appear in red under the field they concern; a page
is complete when its section has no problems. Each page has a Reset button
for its own section; File > Reset Settings resets them all.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtWidgets

from IDTIMS_UPbRPy.settings import decay_constants
from idtims_app.ui.theme import active_theme, theme_color
from idtims_app.widgets.forms import (SettingsGrid, SettingsPage, card, fit_table_height,
                                      format_number, note_label, read_only_table, table_item)


def _fmt(value, digits=6):
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "–"
    return f"{value:.{digits}g}"


class FractionationPage(SettingsPage):
    """535 Pb fractionation per collector; 2535 FPb per fraction (read-only); U note."""

    key = "fractionation"
    sections = ("fractionation",)

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        frame, layout = card("535 tracers: Pb fractionation per collector",
                             "αPb in %/amu with an absolute 1σ in %/amu, applied to every "
                             "fraction with Spike Type 535 by its collector.")
        grid = SettingsGrid(self, ["Collector", "αPb (%/amu)", "", "± 1σ (%/amu)"])
        grid.add("Faraday (F)",
                 self.number("fractionation", "FPb_Faraday", "Faraday Pb fractionation (%/amu)"),
                 self.number("fractionation", "FPb_Faraday_std",
                             "Faraday Pb fractionation uncertainty (%/amu)"))
        grid.add("Daly (D)",
                 self.number("fractionation", "FPb_Daly", "Daly Pb fractionation (%/amu)"),
                 self.number("fractionation", "FPb_Daly_std",
                             "Daly Pb fractionation uncertainty (%/amu)"))
        layout.addLayout(grid.layout)
        self.usage_535 = note_label()
        layout.addWidget(self.usage_535)
        self.collector_card = frame
        self.content.addWidget(frame)

        frame, layout = card("2535 tracers: FPb from measured and tracer 202Pb/205Pb",
                             "FPb = (1 − R25t/R25m)/3 per amu, computed for each fraction from "
                             "its measured 202Pb/205Pb and the tracer's (utils.calc_FPb_2535). "
                             "Read-only; the 535 values above are not used for these fractions. "
                             "The 1σ treats measured and tracer 202/205 as independent.")
        self.table_2535 = read_only_table(["Fraction", "Measured\n202/205", "± 1σ\n%",
                                           "Tracer\n202/205", "± 1σ\n%", "FPb\n(%/amu)",
                                           "± 1σ\n(%/amu)"])
        layout.addWidget(self.table_2535)
        self.none_2535 = note_label("No fraction uses a 2535 tracer.")
        layout.addWidget(self.none_2535)
        self.derived_card = frame
        self.content.addWidget(frame)

        frame, layout = card("U fractionation")
        layout.addWidget(note_label(
            "αU is not entered: it is computed for each fraction from the measured and tracer "
            "233U/235U during reduction (233U-235U double spike)."))
        self.content.addWidget(frame)
        self.content.addStretch(1)
        self.enable_panels()
        self.refresh()

    def complete_text(self):
        return "Fractionation settings are valid."

    def refresh_extra(self):
        counts = self.session.collector_counts() if self.session.has_table else {"F": 0, "D": 0}
        if counts["F"] or counts["D"]:
            self.usage_535.setText(f"Used by {counts['F']} Faraday and {counts['D']} Daly "
                                   "fractions with a 535 tracer.")
        else:
            self.usage_535.setText("No fraction uses a 535 tracer now; these values are kept "
                                   "for fractions that do.")
        rows = self.session.fpb_2535() if self.session.has_table else []
        table = self.table_2535
        table.setRowCount(len(rows))
        for r, (fid, r25m, r25m_rel, r25t, r25t_rel, fpb, fpb_std, message) in enumerate(rows):
            values = [fid, _fmt(r25m, 8), _fmt(r25m_rel, 4), _fmt(r25t, 8), _fmt(r25t_rel, 4),
                      _fmt(None if fpb is None else fpb * 100, 6),
                      _fmt(None if fpb_std is None else fpb_std * 100, 4)]
            for c, text in enumerate(values):
                tip = message or None
                if c == 5 and fpb is not None:
                    tip = f"FPb = {format_number(fpb * 100)} %/amu"
                item = table_item(text, number=c > 0, tooltip=tip)
                if c in (3, 4):
                    item.setForeground(theme_color(active_theme().muted))
                table.setItem(r, c, item)
            if message:
                table.setItem(r, 5, table_item(message, tooltip=message))
                table.setSpan(r, 5, 1, 2)
        table.resizeColumnsToContents()
        for c in range(table.columnCount()):
            table.setColumnWidth(c, max(table.columnWidth(c), 70))
        table.setVisible(bool(rows))
        self.none_2535.setVisible(not rows)
        fit_table_height(table)
        if hasattr(self, "splitter") and self.work_area.maximised is None:
            project = self.derived_card if rows and not any(counts.values()) else self.collector_card
            if self.splitter.widget(0) is not project:
                self.splitter.insertWidget(0, project)
            self.collector_card.set_reference(project is self.derived_card)
            self.derived_card.set_reference(not rows)


class BlanksPage(SettingsPage):
    """Laboratory Pb and U blank, blank composition and initial common Pb."""

    key = "blanks"
    sections = ("lab_blanks", "common_pb")

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        row = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.Direction.TopToBottom)
        row.setSpacing(10)
        self.cards_row = row

        frame, layout = card("Blank amounts and laboratory composition", "Project totals first; laboratory composition below. Errors are 1σ %.")
        grid = SettingsGrid(self, ["", "Value", "", "± 1σ %"])
        n = self.number
        grid.add("Pb blank (pg)", n("lab_blanks", "Pb_blank_total", "Pb blank (pg)"),
                 n("lab_blanks", "Pb_blank_total_std_rel", "Pb blank uncertainty (%)", width=124))
        grid.add("U blank (pg)", n("lab_blanks", "U_blank_total", "U blank (pg)"),
                 n("lab_blanks", "U_blank_total_std_rel", "U blank uncertainty (%)", width=124))
        composition = QtWidgets.QLabel("Reference · laboratory blank composition")
        composition.setObjectName("SectionTitle")
        grid.layout.addWidget(composition, grid.row, 0, 1, 6)
        grid.row += 1
        for ratio, label in (("R64b", "206Pb/204Pb"), ("R74b", "207Pb/204Pb"),
                             ("R84b", "208Pb/204Pb")):
            grid.add(label, n("lab_blanks", ratio, f"Blank {label}"),
                     n("lab_blanks", ratio + "_std_rel", f"Blank {label} uncertainty (%)",
                       width=124))
        grid.add("ρ 6/4–7/4", n("lab_blanks", "rho_6474_b",
                                "Blank correlation 206/204 vs 207/204"))
        grid.add("ρ 6/4–8/4", n("lab_blanks", "rho_6484_b",
                                "Blank correlation 206/204 vs 208/204"))
        layout.addLayout(grid.layout)
        layout.addStretch(1)
        self.blank_card = frame
        row.addWidget(frame, 1)

        frame, layout = card("Initial common Pb · project")
        self.sk_radio = QtWidgets.QRadioButton("Stacey-Kramers (1975) at an age")
        self.explicit_radio = QtWidgets.QRadioButton("Explicit ratios")
        self.model_group = QtWidgets.QButtonGroup(self)
        radios = QtWidgets.QHBoxLayout()
        radios.setSpacing(16)
        for button in (self.explicit_radio, self.sk_radio):
            self.model_group.addButton(button)
            radios.addWidget(button)
        radios.addStretch(1)
        layout.addLayout(radios)
        self.sk_radio.toggled.connect(self._model_toggled)
        grid = SettingsGrid(self, ["", "Value", "", "± 1σ %"])
        self.age_field = n("common_pb", "age_Ga", "Stacey-Kramers age (Ga)")
        grid.add("Age (Ga)", self.age_field)
        self.ratio_fields = {}
        self.sk_labels = {}
        for ratio, label in (("R64c", "206Pb/204Pb"), ("R74c", "207Pb/204Pb"),
                             ("R84c", "208Pb/204Pb")):
            field = n("common_pb", ratio, f"Initial Pb {label}", width=132)
            shown = QtWidgets.QLabel()
            shown.setFixedWidth(field.width())
            shown.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight
                               | QtCore.Qt.AlignmentFlag.AlignVCenter)
            shown.setToolTip(f"{label} from Stacey-Kramers (1975) at the age above")
            holder = QtWidgets.QStackedWidget()
            holder.setFixedWidth(field.width())
            holder.addWidget(field)
            holder.addWidget(shown)
            self.ratio_fields[ratio] = (field, holder)
            self.sk_labels[ratio] = shown
            grid.add(label, field,
                     n("common_pb", ratio + "_std_rel", f"Initial Pb {label} uncertainty (%)",
                       width=124), value_widget=holder)
        grid.add("ρ 6/4–7/4", n("common_pb", "rho_6474_c",
                                "Initial Pb correlation 206/204 vs 207/204"))
        grid.add("ρ 6/4–8/4", n("common_pb", "rho_6484_c",
                                "Initial Pb correlation 206/204 vs 208/204"))
        layout.addLayout(grid.layout)
        self.model_note = note_label()
        layout.addWidget(self.model_note)
        layout.addStretch(1)
        self.common_card = frame
        row.addWidget(frame, 1)
        self.content.addLayout(row)

        self.content.addWidget(note_label(
            "Common Pb up to the blank amount is assigned to blank, the rest to initial Pb. "
            "After reduction, Review shows the rule used for each fraction (all blank, or blank "
            "plus initial)."))
        self.content.addStretch(1)
        self.enable_panels()
        self.splitter.insertWidget(0, self.common_card)
        for field in self.fields:
            if field.section == "lab_blanks" and field.name not in {
                    "Pb_blank_total", "Pb_blank_total_std_rel", "U_blank_total", "U_blank_total_std_rel"}:
                field.setProperty("referenceValue", True)
        self.refresh()

    def _model_toggled(self, sk):
        model = "stacey_kramers" if sk else "explicit"
        if self.session.settings.common_pb.model != model:
            self.session.settings.common_pb.model = model
            self.session.settings_edited()
            self.refresh()
            self.changed.emit()

    def complete_text(self):
        return "Blank and initial Pb settings are valid."

    def refresh_extra(self):
        common = self.session.settings.common_pb
        sk = common.model == "stacey_kramers"
        for button, on in ((self.sk_radio, sk), (self.explicit_radio, common.model == "explicit")):
            button.blockSignals(True)
            button.setChecked(on)
            button.blockSignals(False)
        self.age_field.setEnabled(sk)
        ratios = None
        if sk:
            try:
                ratios = common.ratios() if common.age_Ga is not None else None
            except (TypeError, ValueError):
                ratios = None
        for index, ratio in enumerate(("R64c", "R74c", "R84c")):
            field, holder = self.ratio_fields[ratio]
            holder.setCurrentIndex(1 if sk else 0)
            self.sk_labels[ratio].setText(f"{ratios[index]:.4f}" if ratios else "–")
            if ratios:
                self.sk_labels[ratio].setToolTip(f"{format_number(ratios[index])} from "
                                                 f"Stacey-Kramers at {common.age_Ga} Ga")
        if sk:
            self.model_note.setText("Ratios from utils.SK75 at the age above; the 1σ % and ρ "
                                    "are yours.")
        else:
            self.model_note.setText("Enter the initial Pb ratios, their 1σ % and ρ.")


class ThPage(SettingsPage):
    """230Th disequilibrium correction and the decay constants in use."""

    key = "thorium"
    sections = ("th_correction",)

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        frame, layout = card("230Th disequilibrium correction",
                             "Applies to the Th-corrected 206Pb/238U and 207Pb/206Pb dates.")
        self.kind_buttons = {}
        self.kind_group = QtWidgets.QButtonGroup(self)
        for kind, text in ((None, "None"),
                           ("D", "D(Th/U): Th/U partitioning between mineral and melt"),
                           ("magma", "Th/U of the magma (Th/U of the fraction from 208Pb*)")):
            button = QtWidgets.QRadioButton(text)
            self.kind_group.addButton(button)
            self.kind_buttons[kind] = button
            button.toggled.connect(lambda on, k=kind: on and self._kind_chosen(k))
            layout.addWidget(button)
        grid = SettingsGrid(self, ["", "Value", "", "± 1σ (abs.)"])
        self.d_fields = (self.number("th_correction", "D_Th_U", "D(Th/U)"),
                         self.number("th_correction", "D_Th_U_std", "D(Th/U) uncertainty",
                                     width=124))
        grid.add("D(Th/U)", *self.d_fields)
        self.magma_fields = (self.number("th_correction", "Th_U_magma", "Th/U of the magma"),
                             self.number("th_correction", "Th_U_magma_std",
                                         "Th/U of the magma uncertainty", width=124))
        grid.add("Th/U magma", *self.magma_fields)
        layout.addLayout(grid.layout)
        self.kind_note = note_label()
        layout.addWidget(self.kind_note)
        self.content.addWidget(frame)

        frame, layout = card("Reference · decay constants (read-only)")
        self.reference_card = frame
        frame.set_reference(True)
        self.constants = read_only_table(["Constant", "Value (1/yr)", "± 1σ (1/yr)"])
        rows = [("λ238", "lambda_238", "lambda_238_std"), ("λ235", "lambda_235", "lambda_235_std"),
                ("λ232", "lambda_232", "lambda_232_std"), ("λ230", "lambda_230", None)]
        values = decay_constants()
        self.constants.setRowCount(len(rows))
        for r, (label, name, std) in enumerate(rows):
            self.constants.setItem(r, 0, table_item(label))
            self.constants.setItem(r, 1, table_item(f"{values[name]:.7g}", number=True,
                                                    tooltip=format_number(values[name])))
            self.constants.setItem(r, 2, table_item(f"{values[std]:.7g}" if std else "–",
                                                    number=True,
                                                    tooltip=format_number(values[std]) if std
                                                    else "No uncertainty is held for λ230."))
        self.constants.resizeColumnsToContents()
        for c in range(3):
            self.constants.setColumnWidth(c, max(self.constants.columnWidth(c) + 16, 90))
        fit_table_height(self.constants)
        self.constants.setFixedWidth(sum(self.constants.columnWidth(c) for c in range(3))
                                     + 2 * self.constants.frameWidth() + 2)
        layout.addWidget(self.constants)
        layout.addWidget(note_label("These are the engine defaults (IDTIMS_UPbRPy.constants). "
                                    "They are shown, never changed; settings files do not "
                                    "carry decay constants."))
        self.content.addWidget(frame)
        self.content.addStretch(1)
        self.enable_panels()
        self.refresh()

    def _kind_chosen(self, kind):
        th = self.session.settings.th_correction
        if th.kind != kind:
            th.kind = kind
            self.session.settings_edited()
            self.refresh()
            self.changed.emit()

    def complete_text(self):
        return "Th correction settings are valid."

    def refresh_extra(self):
        kind = self.session.settings.th_correction.kind
        for value, button in self.kind_buttons.items():
            button.blockSignals(True)
            button.setChecked(value == kind)
            button.blockSignals(False)
        for field in self.d_fields:
            field.setEnabled(kind == "D")
        for field in self.magma_fields:
            field.setEnabled(kind in ("D", "magma"))
        self.kind_note.setText({
            None: "No correction: the Th-corrected dates equal the uncorrected ones.",
            "D": "D(Th/U) ± absolute 1σ is required; Th/U of the magma ± is optional.",
            "magma": "Th/U of the magma ± absolute 1σ is required; the fraction's Th/U comes "
                     "from its radiogenic 208Pb.",
        }.get(kind, ""))
