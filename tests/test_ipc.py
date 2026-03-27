import os
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from beans_stalk.main import IpcServer, try_send_to_running_instance, SOCKET_PATH


@pytest.fixture()
def sock_path(monkeypatch):
    """Provide a short socket path that fits within AF_UNIX limits."""
    fd, path = tempfile.mkstemp(suffix=".sock", dir="/tmp")
    os.close(fd)
    os.unlink(path)  # we just need the name, not the file
    p = Path(path)
    monkeypatch.setattr("beans_stalk.main.SOCKET_PATH", p)
    yield p
    # cleanup
    try:
        p.unlink()
    except FileNotFoundError:
        pass


class TestIpc:
    def test_try_send_fails_when_no_server(self, sock_path):
        result = try_send_to_running_instance("/some/path")
        assert result is False

    def test_server_receives_path(self, sock_path):
        received = []
        server = IpcServer(on_path=lambda p: received.append(p))
        server.start()
        time.sleep(0.1)
        result = try_send_to_running_instance("/some/beans/dir")
        assert result is True
        time.sleep(0.1)
        server.stop()
        assert received == ["/some/beans/dir"]

    def test_stale_socket_cleanup(self, sock_path):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(sock_path))
        sock.close()
        assert sock_path.exists()
        result = try_send_to_running_instance("/path")
        assert result is False
        assert not sock_path.exists()

    def test_server_stop_removes_socket(self, sock_path):
        server = IpcServer(on_path=lambda p: None)
        server.start()
        time.sleep(0.1)
        assert sock_path.exists()
        server.stop()
        assert not sock_path.exists()


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
