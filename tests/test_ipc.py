import os
import socket
import tempfile
import time
from pathlib import Path

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
