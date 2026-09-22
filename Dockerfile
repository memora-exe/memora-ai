# ponytail: single-stage python slim image; upgrade to multi-stage if compile deps (gcc) become heavy
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=3020

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3020
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3020"]
