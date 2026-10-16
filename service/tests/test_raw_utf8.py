"""Raw UTF-8 in the URL is read as if it had been escaped (raw_utf8.py)."""

import socket
import threading
import time

import pytest
import uvicorn

from transport_api.raw_utf8 import RawUtf8HttpToolsProtocol, escape_request_line


@pytest.mark.parametrize(
    "data, expected",
    [
        (
            b"GET /?s=W\xc3\xbcrenlos HTTP/1.1\r\nX: \xc3\xbc\r\n\r\n",
            (b"GET /?s=W%C3%BCrenlos HTTP/1.1\r\nX: \xc3\xbc\r\n\r\n", False),
        ),
        (b"GET /?s=Bern HTTP/1.1\r\n", (b"GET /?s=Bern HTTP/1.1\r\n", False)),
        # The line goes on in the next chunk.
        (b"GET /?s=Del\xc3\xa9", (b"GET /?s=Del%C3%A9", True)),
    ],
)
def test_only_the_request_line_is_escaped(data, expected):
    assert escape_request_line(data) == expected


async def _echo(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-length", b"%d" % len(scope["query_string"]))],
        }
    )
    await send({"type": "http.response.body", "body": scope["query_string"]})


@pytest.fixture(scope="module")
def port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            _echo, host="127.0.0.1", port=free, http=RawUtf8HttpToolsProtocol, log_level="error"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield free
    server.should_exit = True
    thread.join()


def _exchange(port: int, *chunks: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port)) as conn:
        for chunk in chunks:
            conn.sendall(chunk)
            time.sleep(0.05)
        conn.shutdown(socket.SHUT_WR)
        answer = b""
        while data := conn.recv(4096):
            answer += data
    return answer


def test_the_application_gets_the_escaped_query(port):
    answer = _exchange(
        port,
        b"GET /v1/stationboard?station=W\xc3\xbcrenlos HTTP/1.1\r\n"
        b"Host: x\r\nConnection: close\r\n\r\n",
    )

    assert answer.startswith(b"HTTP/1.1 200")
    assert answer.endswith(b"station=W%C3%BCrenlos")


def test_a_line_split_across_chunks_and_a_second_request_on_the_same_connection(port):
    answer = _exchange(
        port,
        b"GET /?id=Del\xc3",
        b"\xa9mont HTTP/1.1\r\nHost: x\r\n\r\n",
        b"GET /?id=Z\xc3\xbcrich HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n",
    )

    assert answer.count(b"HTTP/1.1 200") == 2
    assert b"id=Del%C3%A9mont" in answer
    assert answer.endswith(b"id=Z%C3%BCrich")
