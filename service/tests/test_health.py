from datetime import timedelta


def test_health_reports_ok(client):
    response = client.get("/v2/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_is_in_zurich_time(client):
    """The timezone trap, asserted rather than trusted.

    A container defaults to UTC. The /v1 shape prints local times without an
    offset, so a service running on UTC would be wrong by an hour or two and
    nothing would fail. Here the offset is visible: Switzerland is one or two
    hours ahead, never zero.
    """
    body = client.get("/v2/health").json()

    assert body["timezone"] == "Europe/Zurich"

    offset = _offset(body["time"])
    assert offset in (timedelta(hours=1), timedelta(hours=2)), body["time"]


def _offset(timestamp: str) -> timedelta:
    from datetime import datetime

    parsed = datetime.fromisoformat(timestamp)
    assert parsed.utcoffset() is not None, "timestamp carries no offset"
    return parsed.utcoffset()
