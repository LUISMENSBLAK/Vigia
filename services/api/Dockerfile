FROM python:3.12.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN pip install --no-cache-dir uv==0.10.9 && uv sync --frozen --no-dev
COPY services ./services
COPY workers ./workers

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "services.api.vigia_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
