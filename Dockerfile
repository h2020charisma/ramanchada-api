FROM python:3.11-slim as requirements-stage

WORKDIR /tmp

RUN pip install poetry

COPY ./pyproject.toml ./poetry.lock* /tmp/
COPY ./extern/pynanomapper /tmp/extern/pynanomapper
COPY ./extern/ramanchada2 /tmp/extern/ramanchada2

RUN poetry export -f requirements.txt --output requirements.txt --without=dev --without-hashes

FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11-slim

RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=requirements-stage /tmp/requirements.txt /app/requirements.txt
COPY ./extern/pynanomapper /tmp/extern/pynanomapper
COPY ./extern/ramanchada2 /tmp/extern/ramanchada2

RUN sed -i 's/^-e //' /app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

RUN find /tmp -mindepth 1 -delete

COPY ./src/rcapi /app/rcapi

RUN sed -i '/^upload_dir:/s|:.*|: "/var/uploads"|' /app/rcapi/config/config.yaml

RUN mkdir -p /var/uploads/TEMPLATES

COPY ./tests/resources/templates/dose_response.json /var/uploads/TEMPLATES/3c22a1f0-a933-4855-848d-05fcc26ceb7a.json

ENV RAMANCHADA_API_CONFIG="/app/rcapi/config/config.yaml"
ENV MODULE_NAME="rcapi.main"
