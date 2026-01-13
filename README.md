# CV Analyzer API

API for analyzing resumes (PDF/DOCX) against job descriptions and returning structured insights.

## 🚀 Features (MVP)
- Upload resume files (PDF or DOCX)
- Extract and normalize text content
- Parse resume data
- **API Key authentication** for secure access
- LLM-powered analysis with structured JSON output
- Response caching to reduce costs
- Dockerized environment

## 🧱 Tech Stack
- Python 3.11
- FastAPI
- LLM (OpenAI, Anthropic, Ollama support planned)
- Docker
- Pydantic for validation

## 🔐 Authentication

All API endpoints (except `/health`) require the `X-API-Key` header.

```bash
# Set API keys in .env
API_KEYS=your-secret-key-1,your-secret-key-2

# Make authenticated requests
curl -X POST "http://localhost:8000/v1/cv/parse" \
  -H "X-API-Key: your-secret-key-1" \
  -F "cv_file=@resume.pdf"
```

For development, you can disable authentication with `API_KEY_REQUIRED=false`.

## ⚠️ Limitations (MVP)
- PDF must be text-based (no OCR)
- Job description must be provided as plain text
- In-memory cache (resets on restart)

## ▶️ Quick Start

```bash
# 1. Setup environment
cp .env.example .env
Edit .env: set LLM_API_KEY and API_KEYS

# 2. Run
docker compose up --build

# 3. Test
curl -H "X-API-Key: your-key" http://localhost:8000/health
```

## 📋 API Endpoints

- `GET /health` - Health check
- `POST /v1/cv/parse` - Parse CV file (requires auth)
- `POST /v1/cv/analyze` - Analyze CV vs job description (requires auth)

## 🚧 Planned Features

- Rate limiting per API key
- Structured logging
- Support for multiple LLM providers
- Batch analysis
- Results export (PDF, JSON)
