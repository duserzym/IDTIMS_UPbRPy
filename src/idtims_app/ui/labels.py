# Copied from UPbRPy Studio: GUI/widgets.py (ElidedLabel and scrolling_page)
# at Studio commit f8c561f, on 2026-11-14. Changes: extracted into their own
# module. Bodies unchanged.
"""An eliding label and a scrolling page wrapper shared by the app's pages."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class ElidedLabel(QtWidgets.QLabel):
    """A one-line label that shortens its text with "…" instead of forcing
    its parent wider; the full text is the tooltip while it is shortened.

    Small screens (a 14-inch laptop) cannot give every header label its
    natural width, and a plain ``QLabel`` would either widen the window or
    be cut off mid-character.
    """

    def __init__(self, text: str = "", parent: QtWidgets.QWidget | None = None, *,
                 elide_mode=QtCore.Qt.TextElideMode.ElideRight) -> None:
        super().__init__(parent)
        self._elide_mode = elide_mode
        self._full_text = ""
        self._own_tooltip = ""
        self.setWordWrap(False)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        self._full_text = str(text)
        self._elide()

    def text(self) -> str:  # noqa: D401 - Qt API
        return self._full_text

    def setToolTip(self, tooltip: str) -> None:  # noqa: N802 - Qt API
        self._own_tooltip = tooltip
        super().setToolTip(tooltip)

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802 - Qt API
        metrics = self.fontMetrics()
        margins = self.contentsMargins()
        return QtCore.QSize(
            metrics.horizontalAdvance(self._full_text) + margins.left() + margins.right() + 2,
            super().sizeHint().height(),
        )

    def minimumSizeHint(self) -> QtCore.QSize:  # noqa: N802 - Qt API
        metrics = self.fontMetrics()
        return QtCore.QSize(
            metrics.horizontalAdvance("…") + 4,
            super().minimumSizeHint().height(),
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802 - Qt API
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.Type.FontChange, QtCore.QEvent.Type.StyleChange):
            self._elide()

    def _elide(self) -> None:
        margins = self.contentsMargins()
        width = max(0, self.width() - margins.left() - margins.right())
        shown = self.fontMetrics().elidedText(
            self._full_text, self._elide_mode, width
        )
        super().setText(shown)
        elided = shown != self._full_text
        super().setToolTip(self._full_text if elided and not self._own_tooltip else self._own_tooltip)


def scrolling_page(page: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
    """Put a tab page in a frameless scroll area: it fills the tab when
    there is room and scrolls instead of imposing its minimum size."""
    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll.setWidget(page)
    return scroll
