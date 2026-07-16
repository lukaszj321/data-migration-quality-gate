FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY data_quality_gate ./data_quality_gate

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir . \
    && addgroup --system dqg \
    && adduser --system --ingroup dqg --home /app dqg \
    && mkdir -p /app/reports \
    && chown -R dqg:dqg /app/reports

USER dqg

ENTRYPOINT ["data-quality-gate"]
