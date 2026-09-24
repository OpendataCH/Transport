# Transport API

The Swiss public transport API behind **https://transport.opendata.ch**, run by
[Opendata.ch](https://opendata.ch). It is a free, stateless front for
[timetable.search.ch](https://timetable.search.ch/api/help).

- API documentation: https://transport.opendata.ch/docs.html
- Statistics: https://transport.opendata.ch/stats
- Operations: the [wiki](https://gitlab.com/opendata.ch/Transport/-/wikis/home)

The application is in [`service/`](service/): FastAPI, serving the API under
`/v1` and the website around it. Until 2026 it was a PHP application; its
history is in this repository's git log and in [CHANGELOG.md](CHANGELOG.md).

```sh
docker compose up --build     # http://localhost:8000/
```

Questions and contact: transport@opendata.ch
