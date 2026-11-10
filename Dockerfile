FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    RUNTIME_MODE=cloud ENABLE_CLOUD=false PORT=8080 SERVICE_ROLE=api
COPY pyproject.toml requirements.lock ./
COPY common ./common
COPY backend_a ./backend_a
COPY api ./api
COPY worker ./worker
COPY data ./data
RUN pip install --no-cache-dir -c requirements.lock . \
    && useradd --uid 10001 --create-home app
USER 10001
EXPOSE 8080
CMD ["python", "-m", "backend_a.entrypoint"]
