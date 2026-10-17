# CATRS Security Architecture and Hardening Guide

## 1. Threat Model & Risk Assessment

| Threat / Risk Vector | Severity | Impact | Implemented Mitigation |
| :--- | :--- | :--- | :--- |
| **Wildcard CORS with Credentials** | High | Cross-Origin request forgery and browser data exfiltration | Replaced `allow_origins=["*"]` with configurable explicit allowlist (`CORS_ORIGINS`). |
| **Public Redis & Database Ports** | Critical | Unauthorized direct access to persistent stores | Bound host ports in `docker-compose.yml` strictly to `127.0.0.1`. |
| **Unauthenticated Dataset Switching** | High | Disruption of production routing state via `/dataset/select` | Enforced admin-level authorization via `X-Admin-API-Key`. |
| **Unauthenticated Route Manipulation** | High | Resource exhaustion, unfair priority routing exploitation | Added API key authentication via `X-API-Key` on protected routing & audit endpoints. |
| **Numeric Denial of Service (NaN / Inf)**| Medium | Engine crashes or infinite loops in travel-time calculations | Pydantic `@field_validator` rejects non-finite floats (`NaN`, `Inf`, `-Inf`). |
| **Container Root Privilege Escalation** | High | Host system compromise in the event of an RCE | Added non-root user `appuser` (UID 1000) in Dockerfiles; dropped root privileges. |
| **Information Leakage via Stack Traces**| Medium | Sensitive internal paths and configurations exposed to clients | Global exception handlers catch unhandled errors and return sanitized 500 responses. |
| **Policy Verification Bypass** | High | Malicious or expired policy schedules applied undetected | Independent audit service enforces strict effective and expiration date verification. |

---

## 2. Implemented Security Controls

### A. Authentication and Role-Based Access Control
The platform supports two levels of API token authentication:
- **Client / Ingestion API Key (`X-API-Key`)**:
  - Configured via `ROUTING_API_KEY` and `AUDIT_API_KEY`.
  - Required for `/route`, `/route/plan`, `/predict`, `/audit/outcome`, `/audit/batch`, and `/audit/summary`.
  - In development/synthetic mode without keys set, endpoints remain accessible for local developer ergonomics.
- **Administrative API Key (`X-Admin-API-Key`)**:
  - Configured via `ADMIN_API_KEY`.
  - Strictly required for privileged operations such as dataset mode switches (`/dataset/select`).

### B. Input Validation & Strict Payload Boundaries
All FastAPI endpoints enforce strict Pydantic schemas:
- `extra = "forbid"` prevents parameter injection and unexpected payload poisoning.
- Custom field validators inspect all speed, volume, distance, and weight fields to ensure finite numerical values.
- Speed values must fall within physical bounds `[1.0, 300.0]`.

### C. CORS Configuration
In both `routing-engine` and `audit-service`:
```python
settings = Settings.from_env()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
```
Default origins are restricted to `["http://localhost:3000", "http://127.0.0.1:3000"]`. In production, set `CORS_ORIGINS` to the exact trusted frontend domain(s).

### D. Network and Storage Isolation
- In `infra/docker-compose.yml`, TimescaleDB and Redis port bindings are restricted to `127.0.0.1:5432:5432` and `127.0.0.1:6379:6379`.
- The audit service has been decoupled from Redis; its internal dependencies require only TimescaleDB, minimizing unnecessary network exposure.

### E. Container Security & Non-Root Execution
Application containers for both services build with a dedicated low-privilege system user:
```dockerfile
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser
```
Resource limits (deploy.resources.limits) constrain CPU and memory usage to prevent noisy-neighbor DoS:
- `postgres`: 2.0 CPUs, 2048 MB memory.
- `redis`: 1.0 CPU, 512 MB memory.
- `routing-engine`: 2.0 CPUs, 2048 MB memory.
- `audit-service`: 1.0 CPU, 1024 MB memory.

### F. Safe Exception Handling
Unhandled exceptions are intercepted by a global exception handler:
```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.error("Unhandled exception: %s", str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "InternalServerError", "message": "An unexpected error occurred. Sensitive details have been redacted."}
    )
```

---

## 3. Secret Management & Production Checklist

1. **Environment Variables**:
   - Never commit `.env` or production secrets to Git.
   - Use `.env.example` as a template for production deployment.
2. **Database Credentials**:
   - Replace default `traffic:traffic` credentials with high-entropy passwords injected via secret managers (e.g. AWS Secrets Manager, HashiCorp Vault).
3. **API Keys**:
   - Generate cryptographically secure API keys using `openssl rand -hex 32`.
4. **Audit Verification**:
   - Ensure the policy audit service is hosted behind an independent network gateway to prevent co-mingling of audit logs with routing telemetry.
