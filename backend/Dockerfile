FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg[binary] wheels are not required, but keep the
# image minimal and reproducible.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000

# --reload + a bind-mounted source dir (see docker-compose.yml) gives
# instant reload on code changes during local development.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
