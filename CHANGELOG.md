# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-01-28

### Added

#### Core API Features
- **CV Parsing Endpoint** (`POST /cv/parse`): Extract and normalize text from PDF and DOCX files
- **CV Analysis Endpoint** (`POST /cv/analyze`): Comprehensive CV-to-job-description alignment analysis with structured JSON output
- **Health Check Endpoint** (`GET /health`): Service health verification (no authentication required)
- **ParseCVResponse Schema**: Typed Pydantic model for parse endpoint responses with file metadata and text preview

#### LLM Integration & Guardrails
- **LLM Adapter Interface** (`AbstractLLMClient`): Provider-agnostic abstraction for language models
- **OpenAI Client Implementation**: Structured integration with OpenAI API using Pydantic schema enforcement
- **LLM Client Factory**: Dynamic provider instantiation based on environment configuration
- **Schema Enforcement & Anti-Hallucination**: 
  - Evidence-based claims (LLM required to cite CV quotes as proof)
  - Pydantic validation to enforce response structure
  - Confidence scoring (low/medium/high)
  - Retry logic with fallback for LLM failures

#### Caching & Performance
- **Simple TTL Cache**: In-memory hash-based caching to avoid redundant LLM calls
- **Content Hash Invalidation**: SHA-256 hashing of CV + job description for deterministic cache keys
- **Configurable TTL and Capacity**: Cache control via environment settings (default: 3600s TTL, 1024 max entries)

#### Authentication & Rate Limiting
- **API Key Authentication**: X-API-Key header validation for all protected endpoints
- **Per-Key Rate Limiting**: Fixed-window rate limiter (default: 10 requests/minute per key)
- **Configurable Rate Limits**: Per-environment rate limit settings
- **Rate Limit Headers**: Retry-After responses for 429 status

#### File Parsing & Extraction
- **PDF Text Extraction** (`pypdf` integration): Support for text-based PDFs
- **DOCX Text Extraction** (`python-docx` integration): Support for Office documents
- **Text Normalization**: Whitespace cleanup and encoding handling
- **Extraction Timeouts**: 10-second timeout protection against hanging operations

#### Security & Validation
- **File Magic Number Validation**: Prevent MIME type spoofing with binary signature checks
  - PDF signature detection: `%PDF-`
  - DOCX signature detection: ZIP PK header
- **File Size Validation**: HTTP 413 responses for oversized uploads (default: 10MB limit)
- **ZIP Bomb Protection**: Configurable compression ratio checks and uncompressed size limits
- **Document Complexity Limits**:
  - PDF: Max 50 pages (configurable)
  - DOCX: Max 500 paragraphs (configurable)
- **Semantic Validation** (LLM-based, fail-open):
  - CV quality assessment (validates professional experience, education, skills present)
  - Job description validation
  - Low-confidence results logged but pipeline continues
- **Sensitive Data Redaction**: Automatic filtering of API keys, CV text, and job descriptions from logs

#### Configuration & Environment Management
- **Environment-Aware Config**: Loads `.env.{APP_ENV}` (development, testing, staging, production)
- **Pydantic Settings**: Type-safe configuration with validation on startup
- **LLM Settings**: Provider selection, API key, model name
- **App Settings**: 
  - File upload limits (size, formats)
  - CV/job description character limits
  - Cache configuration
  - Rate limit settings
  - Logging levels and formats
- **Docker Compose**: Development, testing, and production-ready orchestration

#### Logging & Observability
- **Structured Logging**: JSON format for machine-readable logs
- **Request ID Correlation**: X-Request-ID header generation/propagation via contextvars
- **Request Duration Tracking**: X-Request-Duration-ms header for performance monitoring
- **Sensitive Data Filtering**: Automatic redaction of PII and secrets (API keys, CV text, job descriptions)
- **Log Rotation**: Configurable file rotation with backup count and retention policies
- **Event-Driven Logging**:
  - Authentication events (success, missing key, validation failed)
  - Rate limit events (allowed, exceeded)
  - Parsing events (start, success, validation errors)
  - Analysis events (start, cache hit/miss, LLM calls, completion)
  - LLM adapter events (call start, success, failures with latency tracking)
  - Cache events (hit, miss, set operations)

#### Exception Handling & Error Responses
- **Centralized Exception Handlers**: Global error handling for consistent API responses
- **AppError Subclasses**:
  - `ValidationAppError`: 400 Bad Request for input validation failures
  - `AuthenticationAppError`: 403 Forbidden for auth failures
  - `LLMAppError`: 500 Internal Server Error for LLM integration failures
- **Structured Error Responses**: Include error code, message, details, and request_id
- **Stack Trace Protection**: Errors logged server-side only, never exposed to clients

#### OpenAPI & Documentation
- **OpenAPI Metadata**: Custom description, version, contact, and license information
- **API Key Security Scheme**: X-API-Key defined in OpenAPI spec
- **Endpoint Tagging**: CV and Health endpoint groups in Swagger/Redoc
- **Health Endpoint Exemption**: /health excluded from auth requirement in schema
- **Comprehensive README**: Architecture diagrams, quick start guides, API reference, security notes
- **Type-Safe Responses**: Pydantic models for all endpoints (ParseCVResponse, CVAnalysisResponse)

#### Testing Infrastructure
- **16 Test Suites** with 174+ passing tests:
  - File validation (magic bytes, size limits, complexity)
  - Authentication and rate limiting
  - CV parsing (PDF/DOCX extraction, timeout protection)
  - Semantic validation (LLM-based gibberish detection)
  - Analysis service (caching, retry logic, truncation)
  - Exception handling and error responses
  - Middleware (request ID correlation)
  - Logging filters (sensitive data redaction)
  - Cache behavior (TTL, eviction)
  - LLM integration (factory, error handling)
- **Docker Compose Test Environment**: Isolated testing with dedicated .env.testing
- **Async Test Support**: pytest-asyncio for async endpoint testing

#### Project Structure & Code Quality
- **Clean Architecture**: Services → Adapters → Routes separation
- **Dependency Injection**: Factory patterns for LLM and router registration
- **Type Hints**: Mandatory for all public functions
- **Google-Style Docstrings**: Comprehensive documentation with parameter/return descriptions
- **App Factory Pattern**: Testable application initialization via `create_app()`
- **Middleware Stack**: Auth, rate limiting, request ID correlation, logging

#### Container & Deployment
- **Dockerfile**: Python 3.11-slim with optimized layering
- **Docker Compose**: Development and test environment orchestration
- **Environment-Agnostic Image**: Configuration injected at runtime
- **Uvicorn Configuration**: Host 0.0.0.0, port 8000, production-ready defaults

#### Refinements During Development
- **Pydantic Settings Loading**: Fixed environment variable resolution and test isolation
- **File Validation Logic**: Refined MIME type spoofing detection mechanism
- **Integration Tests**: Corrected truncation warnings to expect separate events (CV and job)
- **Type Safety**: Resolved Pylance type errors in Form parameter declarations

### Changed

- **CV Parser Service Refactoring**: Improved separation of concerns with focused functions
  - `_validate_file_type()`: MIME type validation
  - `_extract_text_by_type()`: Format-specific extraction delegation
  - `_build_warnings()`: Centralized quality validation logic
- **Analysis Service Configuration**: Migrated hardcoded constants to centralized config
  - `MIN_CV_CHARS`: Configurable via AppSettings
  - `CV_PREVIEW_CHARS`: Configurable via AppSettings
- **LLM Error Handling**: Converted generic RuntimeError to LLMAppError in OpenAI adapter
- **Validation Prompts**: Improved formatting with textwrap.dedent() for better readability
- **Exception Type Consistency**: Extraction timeouts now raise ValidationAppError (HTTP 400) instead of generic ValueError
- **Middleware Registration Order**: Auth → Rate Limit → Request ID for correct precedence

#### Technical Debt Addressed
- Removed obsolete version field from docker-compose.test.yml
- Hardened .gitignore rules for environment files
- Updated .dockerignore for image optimization
- Standardized error handling across adapter layer

### Security

- **File Upload Protection**: Magic number validation prevents MIME type spoofing
- **Resource Exhaustion Prevention**: 
  - File size limits (HTTP 413 on excess)
  - Extraction timeouts (10s guard)
  - PDF page limits (max 50)
  - DOCX paragraph limits (max 500)
  - ZIP bomb protection with compression ratio checks
- **Data Redaction**: Sensitive fields (API keys, CV text, job descriptions) never logged
- **Request Correlation**: X-Request-ID enables secure distributed tracing
- **No Persistent Storage**: All processing in-memory (no database state retention)

---

## Unreleased

_No unreleased changes at this time._

---

## Legend

- **Added**: New features, endpoints, or capabilities
- **Changed**: Modifications to existing functionality and refactoring
- **Security**: Security improvements and vulnerability fixes

## Versioning Policy

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR.MINOR.PATCH** (e.g., 1.2.3)
- **0.x.y**: Beta/MVP phase (breaking changes allowed in minor versions)
- **1.0.0+**: Stable API (breaking changes only in major versions)

---

_Last updated: 2026-01-28_
