import signal
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from beans_stalk.main import IpcServer
from beans_stalk.ui.main_window import MainWindow


class StalkApp:
    """Application lifecycle manager."""

    def __init__(self):
        self._qt_app: QApplication | None = None
        self._ipc_server: IpcServer | None = None
        self._windows: dict[str, MainWindow] = {}

    def open_beans_dir(self, beans_dir_path: str):
        """Open a window for a beans directory, or focus existing."""
        resolved = str(Path(beans_dir_path).resolve())
        if resolved in self._windows:
            win = self._windows[resolved]
            win.raise_()
            win.activateWindow()
            return

        beans_dir = Path(resolved)
        db_path = beans_dir / "beans.db"
        if not db_path.exists():
            return

        win = MainWindow(beans_dir, on_open_dir=self.open_beans_dir)
        win.destroyed.connect(lambda: self._windows.pop(resolved, None))
        self._windows[resolved] = win
        win.show()

    def run(self, initial_beans_dir: str):
        self._qt_app = QApplication(sys.argv)
        self._qt_app.setApplicationName("Beans Stalk")
        self._qt_app.setQuitOnLastWindowClosed(True)

        self._ipc_server = IpcServer(on_path=self._on_ipc_path)
        self._ipc_server.start()

        def signal_handler(signum, frame):
            self._shutdown()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        signal_timer = QTimer()
        signal_timer.timeout.connect(lambda: None)
        signal_timer.start(250)

        self.open_beans_dir(initial_beans_dir)

        sys.exit(self._qt_app.exec())

    def _on_ipc_path(self, path: str):
        QTimer.singleShot(0, lambda: self.open_beans_dir(path))

    def _shutdown(self):
        if self._ipc_server:
            self._ipc_server.stop()
        for win in list(self._windows.values()):
            win.close()
        if self._qt_app:
            self._qt_app.quit()


def run_app(beans_dir: str):
    """Entry point called from main.py after IPC check."""
    app = StalkApp()
    app.run(beans_dir)
