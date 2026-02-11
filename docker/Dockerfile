FROM python:3.11-slim

WORKDIR /app
COPY app/main.py /app/main.py

# Minimal, no deps
ENTRYPOINT ["python", "/app/main.py"]
