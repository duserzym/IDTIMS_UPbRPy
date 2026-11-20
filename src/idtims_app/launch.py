# Copied from UPbRPy Studio: GUI/launch.py (instance_server_name, SingleInstance,
# FileOpenFilter) at Studio commit f8c561f, on 2026-11-14. Changes: the socket
# name comes from branding.SLUG, its override variable is
# IDTIMS_APP_INSTANCE_NAME, and the URL scheme is branding.URL_SCHEME (not yet
# registered anywhere). Studio's --open target parsing and Windows URL
# registration are not copied.
"""Single running instance and macOS file-open events.

A second launch with file paths hands them to the running window over a local
socket and exits; macOS Finder opens arrive as ``QFileOpenEvent``.
"""
from __future__ import annotations

from collections.abc import Callable
import getpass
import hashlib
import json
import os
from pathlib import Path

from PySide6 import QtCore, QtNetwork

from idtims_app import branding


def instance_server_name() -> str:
    """A local-socket name private to this user (a pipe name on Windows).

    ``IDTIMS_APP_INSTANCE_NAME`` overrides it (tests, or a second instance kept
    apart on purpose).
    """
    override = os.environ.get("IDTIMS_APP_INSTANCE_NAME")
    if override:
        return override
    try:
        user = getpass.getuser()
    except Exception:  # pragma: no cover - no user database
        user = str(Path.home())
    digest = hashlib.sha256(f"{user}|{Path.home()}".encode()).hexdigest()[:12]
    return f"{branding.SLUG}-{digest}"


class SingleInstance(QtCore.QObject):
    """Hand ``--open`` values from a second launch to the running app.

    The running instance :meth:`listen`\\ s; a new process first tries
    :meth:`send`, and exits if the running instance acknowledged.
    Messages are one JSON line, ``{"open": "<value>"}``, answered ``ok``.
    """

    received = QtCore.Signal(str)

    def __init__(self, name: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.name = name or instance_server_name()
        self.server: QtNetwork.QLocalServer | None = None

    def send(self, value: str, timeout_ms: int = 2000) -> bool:
        """Deliver ``value`` to a running instance; ``False`` if none answered."""
        socket = QtNetwork.QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(timeout_ms):
            return False
        socket.write((json.dumps({"open": value}) + "\n").encode("utf-8"))
        socket.flush()
        # flush() may already have written everything, in which case
        # waitForBytesWritten() reports False with nothing left to send.
        if socket.bytesToWrite() and not socket.waitForBytesWritten(timeout_ms):
            socket.abort()
            return False
        acknowledged = False
        if socket.waitForReadyRead(timeout_ms):
            acknowledged = bytes(socket.readAll()).strip() == b"ok"
        socket.disconnectFromServer()
        return acknowledged

    def listen(self) -> bool:
        """Become the instance that receives hand-offs.

        Returns ``False`` when another instance already answers under this
        name. A socket file left by a crashed instance (Unix) answers no one,
        so it is removed first. (Qt's ``UserAccessOption`` listen would
        silently replace even a live socket, hence the explicit probe.)
        """
        probe = QtNetwork.QLocalSocket()
        probe.connectToServer(self.name)
        if probe.waitForConnected(300):
            probe.abort()
            return False
        QtNetwork.QLocalServer.removeServer(self.name)
        server = QtNetwork.QLocalServer(self)
        server.setSocketOptions(QtNetwork.QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self.name):
            return False
        server.newConnection.connect(self._accept)
        self.server = server
        return True

    def close(self) -> None:
        if self.server is not None:
            self.server.close()
            self.server = None

    def _accept(self) -> None:
        while self.server is not None and self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            buffer = bytearray()

            def read(socket=socket, buffer=buffer) -> None:
                buffer.extend(bytes(socket.readAll()))
                if b"\n" not in buffer:
                    return
                line = bytes(buffer).split(b"\n", 1)[0]
                try:
                    value = str(json.loads(line.decode("utf-8"))["open"])
                except (ValueError, KeyError, TypeError):
                    socket.write(b"error\n")
                else:
                    socket.write(b"ok\n")
                    self.received.emit(value)
                socket.flush()
                socket.disconnectFromServer()

            socket.readyRead.connect(read)
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                read()


# ------------------------------------------------------------ macOS events
class FileOpenFilter(QtCore.QObject):
    """Route macOS ``QFileOpenEvent``\\ s (links, Finder opens) to a callback."""

    def __init__(self, callback: Callable[[str], None], parent=None) -> None:
        super().__init__(parent)
        self.callback = callback

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if event.type() == QtCore.QEvent.Type.FileOpen:
            url = event.url()
            if url.isValid() and url.scheme().lower() == branding.URL_SCHEME:
                value = url.toString(QtCore.QUrl.ComponentFormattingOption.FullyEncoded)
            else:
                value = event.file() or url.toLocalFile()
            if value:
                self.callback(value)
                return True
        return False
