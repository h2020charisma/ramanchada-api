# ramanchada-api

A web API for the RamanChada 2 Raman spectroscopy harmonisation library, incorporating the AMBIT/eNanoMapper data model.

## Developer notes

### Installation

[Install Poetry](https://python-poetry.org/docs/#installation), then run:
```
poetry install
```

### Run development server

```
poetry run dev
```

### Work in a shell with installed package and dependencies

```
poetry shell
```

Exit with `exit` or Ctrl-D.

### Add dependency

```
poetry add <pkgname>
```

### Run tests

```
poetry run pytest
```

### Test Docker image

```
docker build -t ramanchada-api:latest .
docker run -it --rm -p 127.0.0.1:8000:80 ramanchada-api
```

### Submodule update

Add and commit or stash any uncommitted changes, then run:
```
git submodule update --remote
git commit -am "Pull the latest commit for the submodules"
git push
```

### Run development server (old)
```
uvicorn src.rcapi.main:app --reload
```
