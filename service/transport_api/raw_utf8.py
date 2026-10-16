"""Requests whose URL carries raw UTF-8 instead of percent escapes.

Some clients send `GET /v1/stationboard?station=Würenlos` with the `ü` as two
bare bytes. The old host (Apache + PHP) read that as if it had been escaped;
uvicorn's parser refuses it with a 400 before the application sees it - on
16 October 2026 some 14'000 requests a day, none of them in the statistics,
since they never reach the code that counts.

This protocol percent-escapes every byte above 0x7f in the request line
before the parser reads it. Escaped, the bytes mean the same thing, so the
application gets exactly the query the client meant. Headers and bodies are
left alone: only the request line is read before the parser, and only up to
its line end.

Used with `uvicorn --http transport_api.raw_utf8:RawUtf8HttpToolsProtocol`.
"""

from uvicorn.protocols.http.httptools_impl import HttpToolsProtocol


def escape_request_line(data: bytes) -> tuple[bytes, bool]:
    """`data` with the request line escaped, and whether the line goes on.

    The second value is true when `data` ends before the line does, so that
    the next chunk is still part of it.
    """
    end = data.find(b"\n")
    line, rest = (data, b"") if end < 0 else (data[: end + 1], data[end + 1 :])
    if not line.isascii():
        line = b"".join(b"%%%02X" % byte if byte > 0x7F else bytes((byte,)) for byte in line)
    return line + rest, end < 0


class RawUtf8HttpToolsProtocol(HttpToolsProtocol):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._in_request_line = True

    def data_received(self, data: bytes) -> None:
        if self._in_request_line:
            data, self._in_request_line = escape_request_line(data)
        super().data_received(data)

    def on_message_complete(self) -> None:
        # The next byte on a kept-alive connection starts a new request line.
        self._in_request_line = True
        super().on_message_complete()
