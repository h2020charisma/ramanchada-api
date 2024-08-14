# ramanchada-api

A web API for the RamanChada 2 Raman spectroscopy harmonisation library, incorporating the AMBIT/eNanoMapper data model.

## Developer notes

### Installation

[Install Poetry](https://python-poetry.org/docs/#installation), then run:
```
poetry install
```

### Run a development server

```
poetry run dev
```

### Work in a shell with installed package and dependencies

```
poetry shell
```

Exit with `exit` or Ctrl-D.

### Add a dependency

```
poetry add <pkgname>
```

### Run the tests

```
poetry run pytest
```

### Update the dependencies

To update the dependencies to compatible versions per `pyproject.toml` specifications:
```
poetry update
```
Note that this does not update the submodules: see below how to update them.

### Test the Docker image

```
docker build -t ramanchada-api:latest .
docker run -it --rm -p 127.0.0.1:8000:80 ramanchada-api
```

### Update the submodules

Add and commit or stash any uncommitted changes, then run:
```
git submodule update --remote
poetry lock --no-update
git add extern poetry.lock
git commit -m "Pull the latest commit for the submodules"
git push
```

### Run a development server (old)
```
uvicorn src.rcapi.main:app --reload
```
