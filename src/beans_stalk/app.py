import signal
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from beans_stalk.config import StalkConfig
from beans_stalk.main import IpcServer
from beans_stalk.ui.main_window import MainWindow


class StalkApp:
    """Application lifecycle manager."""

    def __init__(self):
        self._qt_app: QApplication | None = None
        self._ipc_server: IpcServer | None = None
        self._windows: dict[str, MainWindow] = {}
        self._extra_windows: list[MainWindow] = []
        self._configs: dict[str, StalkConfig] = {}

    def _get_config(self, beans_dir: Path) -> StalkConfig:
        """Get or create a shared config for a beans directory."""
        resolved = str(beans_dir.resolve())
        if resolved not in self._configs:
            self._configs[resolved] = StalkConfig.load(beans_dir)
        return self._configs[resolved]

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

        config = self._get_config(beans_dir)
        win = MainWindow(beans_dir, on_open_dir=self.open_beans_dir,
                         on_new_window=self.open_new_window, config=config)
        win.destroyed.connect(lambda: self._windows.pop(resolved, None))
        self._windows[resolved] = win
        win.show()

    def open_new_window(self, beans_dir_path: str, navigate_to: str):
        """Open an additional window for a beans directory, navigated to a specific node."""
        beans_dir = Path(beans_dir_path).resolve()
        db_path = beans_dir / "beans.db"
        if not db_path.exists():
            return

        config = self._get_config(beans_dir)
        win = MainWindow(beans_dir, on_open_dir=self.open_beans_dir,
                         on_new_window=self.open_new_window,
                         navigate_to=navigate_to, config=config)
        self._extra_windows.append(win)
        win.destroyed.connect(lambda: self._remove_extra_window(win))
        win.show()

    def _remove_extra_window(self, win):
        try:
            self._extra_windows.remove(win)
        except ValueError:
            pass

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
        for win in list(self._extra_windows):
            win.close()
        if self._qt_app:
            self._qt_app.quit()


def run_app(beans_dir: str):
    """Entry point called from main.py after IPC check."""
    app = StalkApp()
    app.run(beans_dir)
