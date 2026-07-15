FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY data_quality_gate ./data_quality_gate
RUN python -m pip install --no-cache-dir .

ENTRYPOINT ["data-quality-gate"]
