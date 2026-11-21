# Transport API

> **Development happens on GitLab:** https://gitlab.com/opendata.ch/Transport —
> issues and merge requests go there. The repository on GitHub
> (github.com/OpendataCH/Transport) is a read-only mirror.

The Swiss public transport API behind **https://transport.opendata.ch**, run by
[Opendata.ch](https://opendata.ch). It answers from its own copy of the national
timetable and its real-time feed on
[opentransportdata.swiss](https://opentransportdata.swiss/), routed by
[MOTIS](https://github.com/motis-project/motis). Until October 2026 it was a
front for [timetable.search.ch](https://timetable.search.ch/api/help).

- API documentation: https://transport.opendata.ch/docs.html
- Statistics: https://transport.opendata.ch/stats
- For AI assistants: the MCP server at https://transport.opendata.ch/mcp ([how to add it](https://transport.opendata.ch/docs.html#mcp))
- Operations: the [wiki](https://gitlab.com/opendata.ch/Transport/-/wikis/home)

The application is in [`service/`](service/): FastAPI, serving the API under
`/v1` and the website around it. Until 2026 it was a PHP application; its
history is in this repository's git log and in [CHANGELOG.md](CHANGELOG.md).

```sh
docker compose up --build     # http://localhost:8000/
```

Questions and contact: transport@opendata.ch
