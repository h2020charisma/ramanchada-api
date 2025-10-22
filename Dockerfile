FROM python:3.12-slim AS requirements-stage

WORKDIR /tmp

COPY ./pyproject.toml ./poetry.lock* /tmp/

RUN pip install poetry poetry-plugin-export
RUN poetry export -f requirements.txt --output requirements.txt --without=dev --without-hashes


FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=requirements-stage /tmp/requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /tmp/requirements.txt

RUN find /tmp -mindepth 1 -delete

COPY ./src/rcapi /app/rcapi
COPY ./__rcapi_*__.* /app/

RUN sed -i '/^upload_dir:/s|:.*|: "/var/uploads"|' /app/rcapi/config/config.yaml

RUN mkdir -p /var/uploads/TEMPLATES
COPY ./tests/resources/templates/dose_response.json /var/uploads/TEMPLATES/3c22a1f0-a933-4855-848d-05fcc26ceb7a.json

ENV RAMANCHADA_API_CONFIG="/app/rcapi/config/config.yaml"
EXPOSE 80
WORKDIR /app

CMD ["uvicorn", "rcapi.main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "4"]
