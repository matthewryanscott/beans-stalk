# macOS .app Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bundle Beans Stalk as a macOS `.app` so it runs as a long-running dock app, with the `stalk` CLI as a thin client that launches the `.app` when needed.

**Architecture:** The `.app` contains a shell launcher that activates the project's uv venv and runs a new `run_server()` entry point (no initial window, `setQuitOnLastWindowClosed(False)`). The `stalk` CLI resolves paths, launches the `.app` via `open` if the IPC socket isn't available, polls for readiness, and sends the path over the existing Unix domain socket.

**Tech Stack:** PySide6, Typer, shell scripting, macOS `sips`/`iconutil` for icon conversion.

---

### Task 1: Make `StalkApp.run()` support server mode (no initial window)

**Files:**
- Modify: `src/beans_stalk/app.py:72-92`
- Test: `tests/test_ipc.py`

- [ ] **Step 1: Write failing test for server mode (no initial dir)**

Add to `tests/test_ipc.py`:

```python
class TestServerMode:
    def test_run_server_starts_ipc_without_window(self, sock_path, qapp):
        """StalkApp in server mode starts IPC but opens no windows."""
        from beans_stalk.app import StalkApp

        app = StalkApp(qt_app=qapp)
        app.start_server()
        time.sleep(0.1)

        assert sock_path.exists()
        assert len(app._windows) == 0

        result = try_send_to_running_instance("/some/path")
        assert result is True

        app.stop_server()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/versafeed/proj/beans-stalk && uv run pytest tests/test_ipc.py::TestServerMode::test_run_server_starts_ipc_without_window -v`
Expected: FAIL — `StalkApp` doesn't accept `qt_app` or have `start_server`/`stop_server`

- [ ] **Step 3: Implement server mode in StalkApp**

Modify `src/beans_stalk/app.py`. The key changes:

1. `StalkApp.__init__` accepts an optional `qt_app` parameter (for testing and for the `.app` launcher where QApplication is created externally).
2. New `start_server()` method — starts IPC server + signal handling, no window.
3. New `stop_server()` method — wraps `_shutdown()` for external callers.
4. `run()` becomes optional sugar that creates QApplication, calls `start_server()`, optionally opens a window, and enters the event loop.
5. When `initial_beans_dir` is `None`, `setQuitOnLastWindowClosed(False)`.

```python
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

    def __init__(self, qt_app: QApplication | None = None):
        self._qt_app = qt_app
        self._ipc_server: IpcServer | None = None
        self._windows: dict[str, MainWindow] = {}
        self._extra_windows: list[MainWindow] = []
        self._configs: dict[str, StalkConfig] = {}
        self._signal_timer: QTimer | None = None

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

    def start_server(self):
        """Start IPC server and signal handling. Does not enter event loop."""
        self._ipc_server = IpcServer(on_path=self._on_ipc_path)
        self._ipc_server.start()

        signal.signal(signal.SIGINT, lambda *_: self._shutdown())
        signal.signal(signal.SIGTERM, lambda *_: self._shutdown())

        self._signal_timer = QTimer()
        self._signal_timer.timeout.connect(lambda: None)
        self._signal_timer.start(250)

    def stop_server(self):
        """Stop the IPC server and clean up."""
        self._shutdown()

    def run(self, initial_beans_dir: str | None = None):
        """Create QApplication, start server, optionally open a window, enter event loop."""
        if self._qt_app is None:
            self._qt_app = QApplication(sys.argv)
        self._qt_app.setApplicationName("Beans Stalk")
        self._qt_app.setQuitOnLastWindowClosed(initial_beans_dir is not None)

        self.start_server()

        if initial_beans_dir is not None:
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


def run_server():
    """Entry point for .app bundle — server mode with no initial window."""
    app = StalkApp()
    app.run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/versafeed/proj/beans-stalk && uv run pytest tests/test_ipc.py -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 5: Commit**

```bash
cd /Users/versafeed/proj/beans-stalk
git add src/beans_stalk/app.py tests/test_ipc.py
git commit -m "feat(app): add server mode for headless .app operation"
```

---

### Task 2: Add `stalk-server` entry point to pyproject.toml

**Files:**
- Modify: `pyproject.toml:20-21`

- [ ] **Step 1: Add the entry point**

Add `stalk-server` to the `[project.scripts]` section:

```toml
[project.scripts]
stalk = "beans_stalk.main:app"
stalk-server = "beans_stalk.app:run_server"
```

- [ ] **Step 2: Verify the entry point resolves**

Run: `cd /Users/versafeed/proj/beans-stalk && uv run python -c "from beans_stalk.app import run_server; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/versafeed/proj/beans-stalk
git add pyproject.toml
git commit -m "feat: add stalk-server entry point for .app launcher"
```

---

### Task 3: Make `stalk` CLI a thin client that launches the `.app`

**Files:**
- Modify: `src/beans_stalk/main.py:78-102`
- Test: `tests/test_ipc.py`

- [ ] **Step 1: Write failing test for app-launch flow**

Add to `tests/test_ipc.py`:

```python
from unittest.mock import patch


class TestCliLaunchesApp:
    def test_find_app_bundle_relative_to_package(self, tmp_path):
        """find_app_bundle() finds the .app relative to the source tree."""
        from beans_stalk.main import find_app_bundle

        # Simulate: <project>/src/beans_stalk/main.py
        src_dir = tmp_path / "src" / "beans_stalk"
        src_dir.mkdir(parents=True)
        fake_main = src_dir / "main.py"
        fake_main.touch()

        # Simulate: <project>/dist/Beans Stalk.app
        app_dir = tmp_path / "dist" / "Beans Stalk.app"
        app_dir.mkdir(parents=True)

        result = find_app_bundle(reference=fake_main)
        assert result is not None
        assert result == app_dir

    def test_launch_and_wait_for_server(self, sock_path):
        """launch_and_wait() opens the .app and polls until socket is ready."""
        from beans_stalk.main import launch_and_wait

        app_path = Path("/fake/Beans Stalk.app")

        # Start a server in background to simulate the .app coming up
        server = IpcServer(on_path=lambda p: None)

        def delayed_start():
            time.sleep(0.3)
            server.start()

        t = threading.Thread(target=delayed_start)
        t.start()

        with patch("subprocess.run") as mock_run:
            launch_and_wait(app_path, timeout=5.0)
            mock_run.assert_called_once_with(["open", str(app_path)])

        t.join()
        server.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/versafeed/proj/beans-stalk && uv run pytest tests/test_ipc.py::TestCliLaunchesApp -v`
Expected: FAIL — `find_app_bundle` and `launch_and_wait` don't exist

- [ ] **Step 3: Implement `find_app_bundle()` and `launch_and_wait()`**

Add these functions to `src/beans_stalk/main.py` (above the `@app.command()` decorator):

```python
import subprocess
import time as _time


def find_app_bundle(reference: Path | None = None) -> Path | None:
    """Locate Beans Stalk.app, checking paths in priority order."""
    if reference is None:
        reference = Path(__file__)
    # 1. Relative to source tree: <project>/dist/Beans Stalk.app
    project_root = reference.resolve().parent.parent.parent
    candidate = project_root / "dist" / "Beans Stalk.app"
    if candidate.is_dir():
        return candidate
    # 2. ~/Applications
    candidate = Path.home() / "Applications" / "Beans Stalk.app"
    if candidate.is_dir():
        return candidate
    # 3. /Applications
    candidate = Path("/Applications/Beans Stalk.app")
    if candidate.is_dir():
        return candidate
    return None


def launch_and_wait(app_path: Path, timeout: float = 10.0):
    """Launch the .app and poll until the IPC socket is ready."""
    subprocess.run(["open", str(app_path)])
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if SOCKET_PATH.exists():
            # Verify the socket is connectable, not just a stale file
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(str(SOCKET_PATH))
                sock.close()
                return
            except (ConnectionRefusedError, FileNotFoundError):
                pass
            finally:
                sock.close()
        _time.sleep(0.1)
    raise RuntimeError(
        f"Beans Stalk.app did not start within {timeout}s. "
        f"Socket not found at {SOCKET_PATH}"
    )
```

- [ ] **Step 4: Rewrite the `main()` CLI command as a thin client**

Replace the `main()` function in `src/beans_stalk/main.py`:

```python
@app.command()
def main(
    beans_dir: str = typer.Argument(None, help="Path to .beans directory or parent"),
):
    """Launch Beans Stalk DAG viewer."""
    from beans.workspace import find_beans_dir

    if beans_dir is None:
        resolved = str(find_beans_dir())
    else:
        p = Path(beans_dir)
        if p.is_dir() and (p / "beans.db").exists():
            resolved = str(p)
        elif p.name == "beans.db" and p.exists():
            resolved = str(p.parent)
        else:
            resolved = str(find_beans_dir(start=beans_dir))

    # Try sending to an already-running instance
    if try_send_to_running_instance(resolved):
        raise SystemExit(0)

    # Server not running — find and launch the .app
    app_path = find_app_bundle()
    if app_path is None:
        typer.echo("Error: Could not find Beans Stalk.app", err=True)
        typer.echo(
            "Run scripts/build_app.sh to create it, or copy it to ~/Applications/",
            err=True,
        )
        raise SystemExit(1)

    launch_and_wait(app_path)

    if not try_send_to_running_instance(resolved):
        typer.echo("Error: Failed to connect after launching Beans Stalk.app", err=True)
        raise SystemExit(1)

    raise SystemExit(0)
```

- [ ] **Step 5: Add missing imports at top of main.py**

The file needs `subprocess` and the `time` alias. Full imports block:

```python
import socket
import subprocess
import threading
import time as _time
from pathlib import Path
from typing import Callable

import typer
```

- [ ] **Step 6: Run all tests**

Run: `cd /Users/versafeed/proj/beans-stalk && uv run pytest tests/test_ipc.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/versafeed/proj/beans-stalk
git add src/beans_stalk/main.py tests/test_ipc.py
git commit -m "feat(cli): make stalk a thin client that launches .app"
```

---

### Task 4: Create placeholder icon and build script

**Files:**
- Create: `resources/icon.png`
- Create: `scripts/build_app.sh`

- [ ] **Step 1: Create the resources directory and placeholder icon**

Generate a 1024x1024 placeholder PNG using Python (a green circle with "BS" text):

```bash
cd /Users/versafeed/proj/beans-stalk
mkdir -p resources
uv run python -c "
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QImage, QPainter, QFont, QColor
img = QImage(1024, 1024, QImage.Format.Format_ARGB32)
img.fill(Qt.GlobalColor.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
p.setBrush(QColor('#4CAF50'))
p.setPen(Qt.PenStyle.NoPen)
p.drawEllipse(64, 64, 896, 896)
p.setPen(QColor('white'))
font = QFont('Helvetica', 320, QFont.Weight.Bold)
p.setFont(font)
p.drawText(QRect(0, 0, 1024, 1024), Qt.AlignmentFlag.AlignCenter, 'BS')
p.end()
img.save('resources/icon.png')
print('Created resources/icon.png')
"
```

- [ ] **Step 2: Write the build script**

Create `scripts/build_app.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$PROJECT_ROOT/dist/Beans Stalk.app"
CONTENTS="$APP_DIR/Contents"

echo "Building Beans Stalk.app..."

# Clean previous build
rm -rf "$APP_DIR"

# Create directory structure
mkdir -p "$CONTENTS/MacOS"
mkdir -p "$CONTENTS/Resources"

# --- Info.plist ---
cat > "$CONTENTS/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Beans Stalk</string>
    <key>CFBundleDisplayName</key>
    <string>Beans Stalk</string>
    <key>CFBundleIdentifier</key>
    <string>com.versafeed.beans-stalk</string>
    <key>CFBundleVersion</key>
    <string>0.1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundleExecutable</key>
    <string>beans-stalk</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

# --- Launcher script ---
cat > "$CONTENTS/MacOS/beans-stalk" << LAUNCHER
#!/usr/bin/env bash
set -euo pipefail

# Resolve project root from .app location
APP_DIR="\$(cd "\$(dirname "\$0")/../.." && pwd)"
PROJECT_ROOT="\$(cd "\$APP_DIR/.." && pwd)"

# Activate the uv venv
PYTHON="\$PROJECT_ROOT/.venv/bin/python"
if [ ! -f "\$PYTHON" ]; then
    osascript -e 'display alert "Beans Stalk" message "Could not find Python venv at '\$PROJECT_ROOT/.venv'. Run uv sync first." as critical'
    exit 1
fi

exec "\$PYTHON" -m beans_stalk.app
LAUNCHER
chmod +x "$CONTENTS/MacOS/beans-stalk"

# --- Icon ---
ICON_SRC="$PROJECT_ROOT/resources/icon.png"
if [ -f "$ICON_SRC" ]; then
    ICONSET_DIR=$(mktemp -d)/icon.iconset
    mkdir -p "$ICONSET_DIR"

    # Generate required icon sizes
    for size in 16 32 128 256 512; do
        sips -z $size $size "$ICON_SRC" --out "$ICONSET_DIR/icon_${size}x${size}.png" > /dev/null 2>&1
        double=$((size * 2))
        sips -z $double $double "$ICON_SRC" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" > /dev/null 2>&1
    done

    iconutil -c icns "$ICONSET_DIR" -o "$CONTENTS/Resources/icon.icns"
    rm -rf "$(dirname "$ICONSET_DIR")"
    echo "Icon converted from $ICON_SRC"
else
    echo "Warning: No icon found at $ICON_SRC — app will use default icon"
fi

echo "Built: $APP_DIR"
echo ""
echo "The .app expects the project venv at $PROJECT_ROOT/.venv"
echo "Make sure you've run: uv sync"
```

- [ ] **Step 3: Make the build script executable and run it**

```bash
cd /Users/versafeed/proj/beans-stalk
chmod +x scripts/build_app.sh
./scripts/build_app.sh
```

Expected: `Built: .../dist/Beans Stalk.app` with no errors.

- [ ] **Step 4: Verify the .app structure**

```bash
ls -la "/Users/versafeed/proj/beans-stalk/dist/Beans Stalk.app/Contents/MacOS/beans-stalk"
ls -la "/Users/versafeed/proj/beans-stalk/dist/Beans Stalk.app/Contents/Resources/icon.icns"
ls -la "/Users/versafeed/proj/beans-stalk/dist/Beans Stalk.app/Contents/Info.plist"
```

Expected: All three files exist. `beans-stalk` is executable.

- [ ] **Step 5: Commit**

```bash
cd /Users/versafeed/proj/beans-stalk
git add resources/icon.png scripts/build_app.sh
git commit -m "feat: add placeholder icon and build_app.sh for macOS bundle"
```

---

### Task 5: Add `__main__.py` for `python -m beans_stalk.app` support

The `.app` launcher runs `python -m beans_stalk.app`, which requires a `__main__.py` or the module to be invokable. Since `app.py` is a module (not a package), the simplest approach is to add a `__main__.py` at the package level that routes to `run_server`.

**Files:**
- Create: `src/beans_stalk/__main__.py`

- [ ] **Step 1: Check current `__main__.py` doesn't exist or what it does**

```bash
cat /Users/versafeed/proj/beans-stalk/src/beans_stalk/__main__.py 2>/dev/null || echo "does not exist"
```

- [ ] **Step 2: Reconsider — the launcher runs `python -m beans_stalk.app`**

Actually, `python -m beans_stalk.app` executes `app.py` as a script. We need a guard at the bottom of `app.py`:

Add to `src/beans_stalk/app.py` at the very end:

```python
if __name__ == "__main__":
    run_server()
```

- [ ] **Step 3: Test it works**

```bash
cd /Users/versafeed/proj/beans-stalk
timeout 3 uv run python -m beans_stalk.app || true
```

Expected: App starts (and gets killed by timeout). No import errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/versafeed/proj/beans-stalk
git add src/beans_stalk/app.py
git commit -m "feat(app): add __main__ guard for python -m invocation"
```

---

### Task 6: Add `dist/` to `.gitignore` and do end-to-end smoke test

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add dist/ to .gitignore**

Check if `.gitignore` exists and add `dist/` if not already present:

```bash
cd /Users/versafeed/proj/beans-stalk
grep -q '^dist/' .gitignore 2>/dev/null || echo 'dist/' >> .gitignore
```

- [ ] **Step 2: End-to-end smoke test — launch .app and send a path via CLI**

```bash
cd /Users/versafeed/proj/beans-stalk

# Make sure no stale server
rm -f ~/.beans-stalk.sock

# Launch the .app
open "dist/Beans Stalk.app"

# Wait for socket
for i in $(seq 1 30); do
    [ -S ~/.beans-stalk.sock ] && break
    sleep 0.2
done

# Verify socket exists
ls -la ~/.beans-stalk.sock

# Send a test path (will fail gracefully if no beans.db there, but proves IPC works)
uv run stalk . || true

# Quit the app
osascript -e 'tell application "Beans Stalk" to quit' 2>/dev/null || true
```

- [ ] **Step 3: Commit .gitignore**

```bash
cd /Users/versafeed/proj/beans-stalk
git add .gitignore
git commit -m "chore: add dist/ to .gitignore"
```

---

### Task 7: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
cd /Users/versafeed/proj/beans-stalk
uv run pytest -v
```

Expected: All tests pass, no regressions.

- [ ] **Step 2: Fix any failures if needed**

If any existing tests break due to the `app.py` constructor change (`qt_app` parameter), update them to pass `qt_app=None` explicitly or adjust the test fixtures.
