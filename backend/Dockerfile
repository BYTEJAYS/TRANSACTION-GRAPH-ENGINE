FROM python:3.11-slim

WORKDIR /app

# System dependencies for scientific packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install Python dependencies (torch CPU only for container)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt || \
    pip install --no-cache-dir \
        fastapi uvicorn[standard] websockets pydantic pydantic-settings \
        aiokafka sqlalchemy asyncpg aioredis redis \
        networkx scipy scikit-learn numpy pandas shap joblib \
        httpx faker pytz orjson python-dateutil

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
