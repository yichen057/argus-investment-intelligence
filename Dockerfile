FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y antiword \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts/kafka_local_acceptance.py ./scripts/kafka_local_acceptance.py
COPY evals ./evals
COPY examples ./examples

RUN pip install --no-cache-dir -e ".[storage,models,cloud,observability]"

EXPOSE 8000

CMD ["uvicorn", "investment_agent.app:app", "--host", "0.0.0.0", "--port", "8000"]
