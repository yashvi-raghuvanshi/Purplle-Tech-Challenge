FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY api/ api/
COPY scripts/ scripts/
COPY dashboard/ dashboard/
COPY store_layout.json .

RUN mkdir -p /app/data

ENV DATABASE_URL=sqlite:////app/data/store_intel.db
ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
