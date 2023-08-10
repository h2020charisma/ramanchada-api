FROM python:3.9-slim as requirements-stage

WORKDIR /tmp

RUN pip install poetry

COPY ./pyproject.toml ./poetry.lock* /tmp/
COPY ./pynanomapper /tmp/pynanomapper
COPY ./ramanchada2 /tmp/ramanchada2

RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

FROM tiangolo/uvicorn-gunicorn:python3.9-slim

LABEL maintainer="Luchesar ILIEV <luchesar.iliev@gmail.com>" \
      org.opencontainers.image.created=$BUILD_DATE \
      org.opencontainers.image.description="RamanChada 2 API service" \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.schema-version="1.0" \
      org.opencontainers.image.source="https://github.com/h2020charisma/ramanchada-api" \
      org.opencontainers.image.title="ramanchada-api" \
      org.opencontainers.image.url="https://github.com/h2020charisma/ramanchada-api/blob/main/README.md" \
      org.opencontainers.image.vendor="IDEAconsult" \
      org.opencontainers.image.version="latest"

COPY --from=requirements-stage /tmp/requirements.txt /app/requirements.txt
COPY ./pynanomapper /tmp/pynanomapper
COPY ./ramanchada2 /tmp/ramanchada2

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

RUN find /tmp -mindepth 1 -delete

ENV RAMANCHADA_API_CONFIG="/app/app/config/config.yaml"

COPY ./app /app/app

RUN sed -i '/^upload_dir:/s|:.*|: "/var/uploads"|' /app/app/config/config.yaml
