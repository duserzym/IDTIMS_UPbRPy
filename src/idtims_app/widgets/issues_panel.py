"""Inspector panel listing, per fraction, what still needs the user.

For each fraction it shows `FractionTable.issues()` and the failed
linked-error checks (identity, reported errors, allowed interval). Inferred
2535 spike types get a confirm button per fraction; a missing U oxide value
gets a "no oxide correction applies" button. When several fractions need the
same confirmation, one button confirms them all.
Repeated informational explanations share a compact Notes section below the
fraction cards; complete explanations remain available in tooltips.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from idtims_app.ui.theme import active_theme


class _FractionButton(QtWidgets.QToolButton):
    """Keep long fraction identities inside the issue card, with a full tooltip."""

    def __init__(self, fid):
        super().__init__()
        self.fraction_id = fid
        self.setAccessibleName(fid)
        self.setMinimumWidth(36)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setText(self.fontMetrics().elidedText(
            self.fraction_id, QtCore.Qt.TextElideMode.ElideRight, max(0, self.width() - 12)))


class IssuesPanel(QtWidgets.QWidget):
    """Per-fraction issue cards with confirm controls."""

    confirmSpikeType = QtCore.Signal(str)
    confirmNoOxide = QtCore.Signal(str)
    confirmAll = QtCore.Signal(str)
    fractionClicked = QtCore.Signal(str)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._cards = {}
        self._selected = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 10, 12)
        layout.setSpacing(6)
        self.title = QtWidgets.QLabel("Issues")
        self.title.setObjectName("WorkflowContextTitle")
        layout.addWidget(self.title)
        self.summary = QtWidgets.QLabel()
        self.summary.setObjectName("SecondaryText")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.bulk = QtWidgets.QVBoxLayout()
        self.bulk.setSpacing(4)
        layout.addLayout(self.bulk)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QtWidgets.QWidget()
        self.cards_layout = QtWidgets.QVBoxLayout(self.body)
        self.cards_layout.setContentsMargins(0, 0, 4, 0)
        self.cards_layout.setSpacing(8)
        self.scroll.setWidget(self.body)
        layout.addWidget(self.scroll, 1)
        self.rebuild()

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                IssuesPanel._clear(item.layout())

    def rebuild(self):
        """Redraw every card from the session."""
        self._clear(self.bulk)
        self._clear(self.cards_layout)
        self._cards = {}
        session = self.session
        self.summary.setText(session.summary_text())
        if not session.has_table or session.row_count == 0:
            self.cards_layout.addStretch(1)
            return
        issues = session.issues()
        individual, groups = self._group_notes(issues)
        by_fraction = {}
        for issue in individual:
            by_fraction.setdefault(issue.fraction_id, []).append(issue)
        failures = {}
        for failure in session.quality_failures():
            failures.setdefault(failure.fraction_id, []).append(failure)
        affected = {issue.fraction_id for issue in issues} | failures.keys()
        clean = [f for f in session.table.fraction_ids if f not in affected]
        for kind, text in (("unconfirmed_spike_type", "Confirm 2535 for all ({n})"),
                           ("missing_oxide", "No oxide correction, all ({n})")):
            n = len({i.fraction_id for i in issues if i.kind == kind})
            if n > 1:
                button = QtWidgets.QPushButton(text.format(n=n))
                button.setObjectName(f"ConfirmAll_{kind}")
                button.setToolTip("Confirm this for every fraction listed below. "
                                  "Only confirm what is true for all of them.")
                button.clicked.connect(lambda _c=False, k=kind: self.confirmAll.emit(k))
                self.bulk.addWidget(button)
        # Put failures and blocking issues ahead of fraction-specific notes.
        ordered = sorted(session.table.fraction_ids, key=lambda fid: not (
            fid in failures or any(issue.blocking for issue in by_fraction.get(fid, []))))
        for fid in ordered:
            if fid in by_fraction or fid in failures:
                card = self._card(fid, by_fraction.get(fid, []), failures.get(fid, []))
                self._cards[fid] = card
                self.cards_layout.addWidget(card)
        if clean:
            note = QtWidgets.QLabel(f"No issues: {', '.join(clean)}.")
            note.setObjectName("SecondaryText")
            note.setWordWrap(True)
            self.cards_layout.addWidget(note)
        if groups:
            section = QtWidgets.QFrame()
            section.setObjectName("GroupedNotes")
            notes_layout = QtWidgets.QVBoxLayout(section)
            notes_layout.setContentsMargins(10, 4, 10, 4)
            notes_layout.setSpacing(6)
            heading = QtWidgets.QLabel("Notes")
            heading.setObjectName("WorkflowContextTitle")
            notes_layout.addWidget(heading)
            for group in groups:
                notes_layout.addWidget(self._note_group(group))
            self.cards_layout.addWidget(section)
        self.cards_layout.addStretch(1)
        if self._selected in self._cards:
            self.select(self._selected)

    @staticmethod
    def _message(issue):
        return issue.message.removeprefix(f"{issue.fraction_id}: ")

    @classmethod
    def _group_notes(cls, issues):
        """Group exact informational repeats, keeping actionable controls local.

        Pb/U cycle explanations can share a line only when their explanation
        and affected fractions match. Different values/messages stay separate.
        """
        individual, candidates = [], {}
        for issue in issues:
            if issue.blocking or issue.kind in {"missing_oxide", "oxide_formula"}:
                individual.append(issue)
            else:
                candidates.setdefault((issue.kind, cls._message(issue)), []).append(issue)
        groups = {}
        for (kind, message), repeats in candidates.items():
            ids = frozenset(issue.fraction_id for issue in repeats)
            if len(ids) < 2:
                individual.extend(repeats)
                continue
            if kind == "cycle_selection_note" and message.startswith(("Pb ", "U ")):
                message = message.split(" ", 1)[1]
            groups.setdefault((kind, message, ids), []).extend(repeats)
        return individual, list(groups.values())

    @classmethod
    def note_count(cls, issues):
        individual, groups = cls._group_notes(issues)
        return sum(not issue.blocking for issue in individual) + len(groups)

    def _note_group(self, group):
        messages = list(dict.fromkeys(self._message(issue) for issue in group))
        affected = {issue.fraction_id for issue in group}
        ids = [fid for fid in self.session.table.fraction_ids
               if fid in affected]
        message = messages[0]
        if group[0].kind == "cycle_selection_note" and message.startswith(("Pb ", "U ")):
            blocks = " and ".join(block for block in ("Pb", "U")
                                  if any(text.startswith(f"{block} ") for text in messages))
            if "the accepted-cycle selection is not recorded." in message:
                title = f"Cycle selection not recorded ({blocks})"
            else:
                title = f"{message.split('. ', 1)[0].split(' ', 1)[1].capitalize()} ({blocks})"
        else:
            title = message.split(". ", 1)[0].rstrip(".")
        if len(title) > 100:
            title = title[:97] + "…"
        scope = (f"all {len(ids)} fractions" if len(ids) == self.session.row_count
                 else ", ".join(ids) if len(ids) <= 4 else f"{len(ids)} fractions")
        label = self._line(f"{title}: {scope}", active_theme().muted)
        label.setObjectName("GroupedNote")
        label.setProperty("kind", group[0].kind)
        explanation = "\n\n".join(messages) + "\n\nFractions: " + ", ".join(ids)
        label.setToolTip(explanation)
        label.setAccessibleDescription(explanation)
        return label

    def _card(self, fid, issues, failures):
        theme = active_theme()
        card = QtWidgets.QFrame()
        card.setObjectName("IssueCard")
        card.setProperty("fraction", fid)
        border = theme.danger if failures or any(issue.blocking for issue in issues) else theme.input_border
        card.setStyleSheet(
            f"QFrame#IssueCard {{ background: {theme.glass_strong}; border: 1px solid {border}; "
            f"border-radius: 12px; }} QFrame#IssueCard[selected=\"true\"] {{ border: 2px solid "
            f"{theme.accent}; }}")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        head = QtWidgets.QHBoxLayout()
        name = _FractionButton(fid)
        name.setText(fid)
        name.setProperty("modeToggle", True)
        name.setStyleSheet("font-weight: 700; font-size: 12px;")
        name.setToolTip(f"Select {fid} in the table")
        name.clicked.connect(lambda _c=False, f=fid: self.fractionClicked.emit(f))
        head.addWidget(name, 1)
        if failures:
            pill = QtWidgets.QLabel("Linked-error check failed")
            pill.setStyleSheet(f"color: {theme.danger}; font-size: 10px; font-weight: 600;")
            pill.setWordWrap(True)
            pill.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Preferred)
            head.addWidget(pill, 1)
        layout.addLayout(head)
        for failure in failures:
            layout.addWidget(self._line(failure.reason, theme.danger))
        for issue in issues:
            color = theme.danger if issue.blocking else theme.muted
            text = self._message(issue)
            layout.addWidget(self._line(text, color))
            if issue.kind == "unconfirmed_spike_type":
                button = self._small_button("Confirm 2535")
                button.setObjectName("ConfirmSpikeType")
                button.setToolTip("Accept the inferred spike type 2535 for this fraction")
                button.clicked.connect(lambda _c=False, f=fid: self.confirmSpikeType.emit(f))
                layout.addWidget(button)
            elif issue.kind == "missing_oxide":
                button = self._small_button("No oxide correction applies")
                button.setObjectName("ConfirmNoOxide")
                button.setToolTip("Confirm that the U ratios need no 18O/16O oxide correction, "
                                  "or enter the value in the U oxide column instead")
                button.clicked.connect(lambda _c=False, f=fid: self.confirmNoOxide.emit(f))
                layout.addWidget(button)
        return card

    @staticmethod
    def _small_button(text):
        button = QtWidgets.QPushButton(text)
        button.setStyleSheet("padding: 3px 9px; font-size: 11px;")
        button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum,
                             QtWidgets.QSizePolicy.Policy.Fixed)
        return button

    @staticmethod
    def _line(text, color):
        label = QtWidgets.QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet(f"color: {color}; font-size: 11px;")
        return label

    def select(self, fid):
        """Highlight one fraction's card and scroll it into view."""
        self._selected = fid
        for key, card in self._cards.items():
            card.setProperty("selected", key == fid)
            card.style().unpolish(card)
            card.style().polish(card)
        card = self._cards.get(fid)
        if card is not None:
            self.scroll.ensureWidgetVisible(card, 0, 8)

    def card_for(self, fid):
        return self._cards.get(fid)


__all__ = ["IssuesPanel"]
