"""One Qt control process per user session, with window activation."""

from pathlib import Path
from time import monotonic, sleep

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstanceError(RuntimeError):
    """A second process could not safely find or create the primary instance."""


class SingleInstanceGuard(QObject):
    """Hold a process lock; use a local socket only to show the open window."""

    activation_requested = Signal()

    def __init__(self, socket_path: Path) -> None:
        super().__init__()
        if not socket_path.is_absolute():
            raise ValueError("single-instance socket path must be absolute")
        self._socket_path = socket_path
        self._lock = QLockFile(str(socket_path) + ".lock")
        self._server = QLocalServer(self)
        # The socket lives in the user's private runtime directory. Qt's
        # UserAccessOption can unlink an existing socket before binding on
        # Linux, which would let a second process replace the live server.
        self._server.newConnection.connect(self._accept_activation)
        self._primary = False

    def start(self) -> bool:
        """Return True for the primary, or activate it and return False."""
        if self._lock.tryLock(0):
            # Only the lock owner may remove a socket left by a crashed process.
            QLocalServer.removeServer(str(self._socket_path))
            if not self._server.listen(str(self._socket_path)):
                self._lock.unlock()
                raise SingleInstanceError("Could not start the KYRIN control socket")
            self._primary = True
            return True

        deadline = monotonic() + 2
        while monotonic() < deadline:
            client = QLocalSocket()
            client.connectToServer(str(self._socket_path))
            if client.waitForConnected(200):
                client.write(b"show\n")
                if not client.waitForBytesWritten(500):
                    raise SingleInstanceError(
                        "Could not activate the open KYRIN window"
                    )
                client.disconnectFromServer()
                return False
            sleep(0.05)
        raise SingleInstanceError("Could not contact the open KYRIN window")

    def _accept_activation(self) -> None:
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            if client is not None:
                client.close()
                client.deleteLater()
                self.activation_requested.emit()

    def close(self) -> None:
        if self._primary:
            self._server.close()
            self._lock.unlock()
            self._primary = False
