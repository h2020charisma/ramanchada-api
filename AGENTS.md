# AGENTS.md

## Sources

- Prefer `pyproject.toml`, `.python-version`, `src/rcapi/main.py`, `src/rcapi/config/app_config.py`, `src/configs/*.yaml`, `Dockerfile`, `.github/workflows/ci.yml`, `.github/dependabot.yml`, and `tests/` for current behavior.
- `README.md` has useful basic commands but is not enough on its own to understand configuration, API contracts, testing, or deployment.
- Keep this file and `CONTRIBUTING.md` updated whenever commands, tooling, configuration loading, deployment behavior, authentication behavior, or public API assumptions change.

## Project Shape

- This is a Poetry-managed FastAPI backend for RamanChada 2 / AMBIT / eNanoMapper search and conversion workflows.
- Python package code lives under `src/rcapi`; the application entrypoint is `src/rcapi/main.py`.
- API routers live under `src/rcapi/api/` and are registered from `src/rcapi/main.py`.
- Core routers include `/db/query`, `/db/download`, `/db/dataset`, `/db/aop/*`, `/.well-known/mcp/*`, upload/process/task/info routes, and H5Grove under `/h5grove`.
- Service logic lives under `src/rcapi/services/`; shared response models are in `src/rcapi/services/standard_response.py`.
- Configuration models and loading live in `src/rcapi/config/app_config.py`.
- Packaged backend personalities/configurations live under `src/configs/`.
- Tests live under `tests/`; `integration/` is included in pytest configuration if present.

## Configuration

- Default bundled config: `src/configs/config.yaml`.
- Alternative bundled configs: `src/configs/config.chemicals.yaml`, `src/configs/config.enanomapper.yaml`, `src/configs/config.plastic.yaml`.
- Select a bundled config with `RCAPI_CONFIG_FILE=<name>.yaml`.
- Select an explicit external config with `RAMANCHADA_API_CONFIG=/absolute/path/to/config.yaml`.
- Config controls `application_name`, upload directory, Solr root/vector, collections, collection roles, fields, similarity modes, document types, and Keycloak metadata.
- `/db/query/sources` exposes client-facing discovery metadata from config: `application_name`, `default`, `data_sources`, `fields`, and `similarity`.
- Docker copies `src/configs` into `/app/configs` and rewrites `upload_dir` values to `/var/uploads`.
- Do not commit secrets or private deployment credentials in YAML config files, `.env`, tests, or Docker context.

## Commands

- Install dependencies: `poetry install`.
- Run the development server: `poetry run dev`.
- Run tests: `poetry run pytest`.
- Open a Poetry shell when needed: `poetry shell`.
- Add a dependency: `poetry add <package>`.
- Update compatible dependency versions: `poetry update`, then review `pyproject.toml` and `poetry.lock`.
- Build a Docker image: `docker build -t ramanchada-api:latest .`.
- Run the Docker image locally: `docker run -it --rm -p 127.0.0.1:8000:80 ramanchada-api`.
- The local Python version file is `.python-version` and currently specifies Python `3.12`; CI tests Python `3.10`, `3.11`, and `3.12`.

## API Contract

- FastAPI publishes OpenAPI and Swagger docs at runtime; keep route signatures, response models, summaries, and descriptions useful for humans and tools.
- `GET|POST /db/query` is the main search endpoint.
- Direct `/db/query` GET dynamic filters use `qdynamic.<field>=value` query parameters.
- `/db/query` POST dynamic filters use JSON body key `qdynamic`.
- Repeated `data_source` parameters select Solr collections. Missing or inaccessible private collections may be dropped according to token and role visibility.
- `GET /db/query/field?name=<field>` returns static facet values.
- `GET /db/query/field/terms?name=<field>&prefix=<term>&limit=<n>` returns autocomplete terms.
- `GET /db/query/sources` returns the client discovery contract: `application_name`, `default`, `data_sources`, `fields`, and `similarity`.
- `GET /db/dataset?domain=<domain>&values=True` returns dataset/chart-compatible values when available.
- `GET /db/download` returns HDF5, image, thumbnail, b64png, json, or other supported download representations depending on `what`. Unlike `/db/query`, `/db/download` (including `solr2json`) does **not** apply the `SOLR_DOCS` type filter — if a collection's `type_s` is absent from `SOLR_DOCS`, `/db/query` returns `numFound:0` while `/db/download` still returns data. Keep `SOLR_DOCS` in sync with served collections; `tests/test_solr_docs_config.py` guards this invariant.
- `POST /db/download?what=knnquery` expects multipart form field `files`; spectrum uploads return compressed vector data and molecule uploads from `.smi` or `.mol` return molecule vector data.
- `/db/aop/material` and `/db/aop/ke` expose AOP lookup functionality.
- `/.well-known/mcp/manifest.json` and `/.well-known/mcp/tools.json` expose MCP metadata derived from the FastAPI app and query configuration.

## MCP Notes

- Keep MCP manifest/tool metadata synchronized with actual API behavior and OpenAPI route definitions.
- Direct `/db/query` GET filters are parsed as `qdynamic.*`. If MCP helper text or generated hints mention `filters.*`, update the MCP metadata or translate to `qdynamic` before calling `/db/query`.
- MCP tool visibility and field/data-source metadata should follow the same role and config rules as the public API.

## Authentication And Access

- Authentication is optional for public data.
- `src/rcapi/services/kc.py` extracts bearer tokens from `Authorization` headers and decodes roles when needed.
- Public collection visibility is controlled by the configured `public` role.
- Private/protected collections are exposed only when token-derived roles match collection roles.
- Tokens are forwarded to Solr and HSDS/HDF5 access where relevant; do not log token values.
- CORS is handled by deployment middleware in the current Docker Compose setup; do not assume app-level CORS unless it is explicitly added.

## Testing And Quality

- Pytest configuration is in `pyproject.toml`.
- Run focused tests after code changes; run `poetry run pytest` for broad verification when feasible.
- Some tests exercise external Solr/HSDS behavior and CI provides `HS_ENDPOINT`, `HS_USERNAME`, and `HS_PASSWORD` where needed.
- CI deselects selected HSDS/download tests for Dependabot runs; keep those deselections current if test names change.
- Add or update tests when changing API contracts, config loading, source/role filtering, field discovery, vector upload behavior, AOP behavior, MCP metadata, or `SOLR_DOCS` / served-collection membership. See `tests/test_solr_docs_config.py` for the pattern used to guard collection-type visibility without a live Solr instance.
- There is no dedicated formatter or linter configured beyond pytest and yamllint config; follow the existing Python style and keep changes small.

## CI And Container

- GitHub Actions are under `.github/workflows/`; Dependabot configuration is `.github/dependabot.yml`.
- CI installs with Poetry, tests on Python `3.10`, `3.11`, and `3.12`, builds Docker images, and publishes to GHCR.
- The Docker image serves `uvicorn rcapi.main:app` on container port `80` with multiple workers.
- Keep Docker, Compose, CI, and config-loading assumptions synchronized when deployment behavior changes.

## Maintenance Rules

- Prefer configuration-driven behavior over hard-coded backend personalities.
- Treat `/db/query/sources` as a stable client discovery contract.
- Do not introduce frontend- or client-specific branches in backend behavior unless there is an explicit compatibility requirement.
- Keep OpenAPI/MCP metadata, tests, and config YAML synchronized when endpoints or request/response contracts change.
- Keep generated output, local uploads, virtual environments, and secrets out of commits.
- Update `AGENTS.md` and `CONTRIBUTING.md` in the same PR when changing install commands, scripts, test tooling, deployment assumptions, configuration loading, authentication behavior, or public API contracts.
