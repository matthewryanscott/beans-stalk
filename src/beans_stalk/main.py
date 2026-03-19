import socket
import threading
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

    if try_send_to_running_instance(resolved):
        raise SystemExit(0)

    from beans_stalk.app import run_app

    run_app(resolved)
