import socket
import subprocess
import threading
import time as _time
from pathlib import Path
from typing import Callable

import typer

SOCKET_PATH = Path.home() / ".beans-stalk.sock"

app = typer.Typer(add_completion=False)


def try_send_to_running_instance(beans_dir_path: str) -> bool:
    if not SOCKET_PATH.exists():
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(SOCKET_PATH))
        sock.sendall(beans_dir_path.encode("utf-8"))
        sock.close()
        return True
    except (ConnectionRefusedError, FileNotFoundError):
        try:
            SOCKET_PATH.unlink()
        except FileNotFoundError:
            pass
        return False
    finally:
        sock.close()


class IpcServer:
    def __init__(self, on_path: Callable[[str], None]):
        self._on_path = on_path
        self._server_socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self):
        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            SOCKET_PATH.unlink()
        except FileNotFoundError:
            pass
        self._server_socket.bind(str(SOCKET_PATH))
        self._server_socket.listen(5)
        self._server_socket.settimeout(0.5)
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._server_socket is not None:
            self._server_socket.close()
            self._server_socket = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        try:
            SOCKET_PATH.unlink()
        except FileNotFoundError:
            pass

    def _accept_loop(self):
        while not self._stop_event.is_set():
            try:
                conn, _ = self._server_socket.accept()
                data = conn.recv(4096).decode("utf-8")
                conn.close()
                if data:
                    self._on_path(data)
            except socket.timeout:
                continue
            except OSError:
                break


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


def resolve_beans_dir_path(beans_dir: str | None) -> str:
    from beans.workspace import find_beans_dir

    if beans_dir is None:
        return str(find_beans_dir().resolve())

    p = Path(beans_dir)
    if p.is_dir() and (p / "beans.db").exists():
        return str(p.resolve())
    if p.name == "beans.db" and p.exists():
        return str(p.parent.resolve())
    return str(find_beans_dir(start=beans_dir).resolve())


@app.command()
def main(
    beans_dir: str = typer.Argument(None, help="Path to .beans directory or parent"),
    wait: bool = typer.Option(
        False,
        "-w",
        "--wait",
        help="Run the app in the foreground; bypass any running instance and stay attached until the window closes.",
    ),
):
    """Launch Beans Stalk DAG viewer."""
    resolved = resolve_beans_dir_path(beans_dir)

    if wait:
        from beans_stalk.app import run_app_foreground

        run_app_foreground(resolved)
        return

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
