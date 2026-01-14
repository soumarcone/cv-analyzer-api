FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Copy .env.example as documentation (image is environment-agnostic)
# Do not copy .env, .env.testing, .env.development, or .env.production
# Configuration is injected at runtime via environment variables
COPY .env.example .env.example

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
