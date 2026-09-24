"""The transport vhost's access log, received from nginx and kept as daily files.

On the old host Apache wrote the access log to a file, rotated it daily and kept
ninety days of it; that log is what answers questions like "who sends this" or
"which clients ignore a 429". On the new host the reverse proxy is shared with
the portal, logs to stdout, and Docker keeps 30 MB of that for all sites
together - minutes of this API's traffic.

So nginx sends this one vhost's log over syslog (UDP, which cannot hold up a
request) to this process, which writes

    access-YYYY-MM-DD.log      today, in the combined format Apache used
    access-YYYY-MM-DD.log.gz   earlier days, compressed once the day is over

and deletes what is older than LOG_KEEP_DAYS. Local time decides the day.

Standard library only, so it runs in any Python image - on the servers in the
image of the Python service, which is already there.
"""

import gzip
import os
import re
import shutil
import signal
import socket
import sys
import threading
import time
from datetime import date, timedelta

LOG_DIR = os.environ.get("LOG_DIR", "/logs")
PORT = int(os.environ.get("LOG_PORT", "5514"))
KEEP_DAYS = int(os.environ.get("LOG_KEEP_DAYS", "30"))

# nginx prefixes each line with "<pri>timestamp tag: "; the line starts after it.
TAG = b"transport: "
NAME = re.compile(r"^access-(\d{4}-\d{2}-\d{2})\.log(\.gz)?$")


def path_of(day: str) -> str:
    return os.path.join(LOG_DIR, f"access-{day}.log")


def compress(path: str) -> None:
    """Gzip a finished day and remove the plain file."""
    with open(path, "rb") as source, gzip.open(path + ".gz", "wb") as target:
        shutil.copyfileobj(source, target)
    os.remove(path)


def tidy(today: str) -> None:
    """Compress finished days left plain, and delete what is past keeping."""
    oldest = (date.fromisoformat(today) - timedelta(days=KEEP_DAYS)).isoformat()
    for name in os.listdir(LOG_DIR):
        match = NAME.match(name)
        if not match:
            continue
        day, packed = match.groups()
        path = os.path.join(LOG_DIR, name)
        if day < oldest:
            os.remove(path)
        elif day < today and not packed:
            compress(path)


def main() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    receiver.bind(("0.0.0.0", PORT))
    receiver.settimeout(1.0)

    day = None
    out = None
    flushed = time.monotonic()

    def stop(*_):
        if out is not None:
            out.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    while True:
        try:
            message = receiver.recv(65535)
        except TimeoutError:
            message = None

        today = time.strftime("%Y-%m-%d")
        if today != day:
            if out is not None:
                out.close()
            day = today
            out = open(path_of(day), "ab")
            # Off the receiving loop: a day's file is large, and UDP does not wait.
            threading.Thread(target=tidy, args=(day,), daemon=True).start()

        if message:
            start = message.find(TAG)
            line = message[start + len(TAG) :] if start >= 0 else message
            out.write(line.rstrip(b"\r\n") + b"\n")

        if time.monotonic() - flushed >= 1.0:
            out.flush()
            flushed = time.monotonic()


if __name__ == "__main__":
    main()
