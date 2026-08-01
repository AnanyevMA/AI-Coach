# 🏛️ Architecture Decision Records (ADR): AI Adaptive Coach v7.0

> **Location:** `.agent_context/ARCHITECTURE_DECISIONS.md`  
> **Status:** Active & Enforced  
> **Last Updated:** 2026-08-01 (Post Phase 4 Complete)

---

## ADR 001: 152-ФЗ Personal Data Localization & Field-Level Encryption

* **Context:** Under Russian Federal Law 152-ФЗ, personal data (PII) and fitness/health metrics (HRV, resting HR, medical notes) of RF citizens must be localized in Russian cloud infrastructure (Selectel / Yandex Cloud) and protected at rest.
* **Decision:**
  - Implement field-level **AES-256-GCM** encryption (`AES256GCMCipher` in `app/core/security.py`) for sensitive columns (`full_name`, `phone_number`, `medical_conditions`, `hrv_rmssd`, `resting_hr`).
  - Require a 256-bit base64-encoded `DATA_ENCRYPTION_KEY_BASE64` secret.
  - Require explicit user consent logging (`ConsentLog` model) storing IP, timestamp, user-agent, and 152-ФЗ clause reference.
* **Status:** ✅ Implemented & Tested (Phase 1)
* **Files:** [`app/core/security.py`](file:///D:/PyCharm_Projects/AI%20Sport/app/core/security.py), [`app/models/audit.py`](file:///D:/PyCharm_Projects/AI%20Sport/app/models/audit.py)

---

## ADR 002: Medical Triage Engine & Non-Telemedicine Boundary (323-ФЗ)

* **Context:** Russian Healthcare Law 323-ФЗ prohibits unlicensed software from diagnosing conditions or prescribing medical treatment.
* **Decision:**
  - Enforce a 3-tier triage system (`RedFlagsTriageEngine` in `app/services/red_flag_service.py`):
    - **Level 1 (Emergency Hard Lock):** Cardiac symptoms (chest pain, syncope, resting HR $\ge 210$). Immediate STOP code, ui lock, emergency referral prompt.
    - **Level 2 (Medical Lock):** Severe HRV drop ($Z < -3.0$), ACWR $> 1.50$, fever ($\ge 37.5^\circ\text{C}$), acute joint pain (VAS $\ge 6$). Freeze training plan until physician clearance.
    - **Level 3 (Caution Reset):** Moderate HRV drop ($Z < -1.5$), elevated resting HR ($+10$ bpm). Auto-reduce workload by 50% (Zone 1 only).
  - All UI surfaces must display mandatory disclaimers establishing that AI Adaptive Coach is an informational athletic tool, not a medical service.
* **Status:** ✅ Implemented & Tested (Phase 1-2)
* **Files:** [`app/services/red_flag_service.py`](file:///D:/PyCharm_Projects/AI%20Sport/app/services/red_flag_service.py), [`docs/medical/red_flags_triage_rules.md`](file:///D:/PyCharm_Projects/AI%20Sport/docs/medical/red_flags_triage_rules.md)

---

## ADR 003: Physiological Load & Recovery Formulas

* **Context:** The AI engine requires objective, evidence-based formulas for load management and readiness scoring.
* **Decision:**
  - **HRV Baseline:** Calculate 7-day rolling average $\ln(\text{rMSSD})$ relative to 30-day baseline $\mu$ and standard deviation $\sigma$:
    $$Z_{\text{HRV}} = \frac{\ln(\text{rMSSD}_{7\text{d}}) - \mu_{30\text{d}}}{\sigma_{30\text{d}}}$$
  - **Acute:Chronic Workload Ratio (ACWR):** EWMA (Exponentially Weighted Moving Average) with $\lambda_a = 2 / (7 + 1) = 0.25$ for acute load and $\lambda_c = 2 / (28 + 1) = 0.069$ for chronic load. Optimal range ("Sweet Spot"): $0.80 \le \text{ACWR} \le 1.30$.
  - **Knee Biomechanics:** Cadence adjustment $+5\dots10\%$ to decrease peak patellofemoral joint force ($PFJRF$) by $14-20\%$ (*Heiderscheit et al.*).
* **Status:** ✅ Implemented & Tested (Phase 2)
* **Files:** [`app/services/telemetry_analysis_service.py`](file:///D:/PyCharm_Projects/AI%20Sport/app/services/telemetry_analysis_service.py), [`docs/medical/hrv_recovery_evidence_review.md`](file:///D:/PyCharm_Projects/AI%20Sport/docs/medical/hrv_recovery_evidence_review.md)

---

## ADR 004: Async Technology Stack & Database Architecture

* **Context:** The system needs to support low-latency Telegram Bot interactions, real-time B2B Web Cabinet updates, and asynchronous `.FIT` file telemetry processing.
* **Decision:**
  - **Language & Core Framework:** Python 3.11+ with FastAPI.
  - **ORM & Driver:** Async SQLAlchemy 2.0 with `asyncpg` driver for PostgreSQL 16.
  - **Caching & Queue:** Redis 7 for session caching and async task queues.
  - **Database Migrations:** Async Alembic.
  - **Deployment Stack:** Docker multi-stage containerization behind Nginx reverse proxy.
* **Status:** ✅ Implemented & Tested (Phase 1-4)
* **Files:** [`app/db/session.py`](file:///D:/PyCharm_Projects/AI%20Sport/app/db/session.py), [`docker-compose.yml`](file:///D:/PyCharm_Projects/AI%20Sport/docker-compose.yml)

---

## ADR 005: AI Engine — Low-Cost Google Gemini Flash + Offline Heuristic Fallback

* **Context:** The AI engine must use affordable or free AI inference. User directive: «ИИ движок должен быть желательно бесплатным или с низкой стоимостью от GOOGLE».
* **Decision:**
  - Primary AI engine: **Google Gemini 1.5 Flash** (`gemini-1.5-flash`) at $0.075/1M tokens (free tier available in Google AI Studio).
  - Fallback: `HeuristicFallbackEngine` — 100% offline deterministic rule-based engine converting high-intensity sessions to Zone 2 recovery when $Z_{\text{HRV}} < -1.5$ or ACWR $> 1.4$.
  - Red Flag pre-interceptor blocks all LLM calls at Level 1/2 triage.
  - API key stored in env vars only, transmitted via HTTP header `x-goog-api-key`, masked in logs via `get_masked_gemini_key()`.
* **Status:** ✅ Implemented & Tested (Phase 2)
* **Files:** [`app/services/ai_coach_engine.py`](file:///D:/PyCharm_Projects/AI%20Sport/app/services/ai_coach_engine.py), [`app/services/fallback_engine.py`](file:///D:/PyCharm_Projects/AI%20Sport/app/services/fallback_engine.py)

---

## ADR 006: API Rate Limiting & DDoS Protection

* **Context:** Unlimited calls to the Gemini API would cause financial token exhaustion. The `/upload-fit` endpoint is CPU-heavy and vulnerable to DoS.
* **Decision:**
  - Implement `RateLimiter` (sliding window algorithm) in `app/core/rate_limiter.py`.
  - Limits: `/generate-plan` → 5 req/min, `/analyze-activity` → 10 req/min, `/upload-fit` → 10 req/min, `/hrv` → 15 req/min.
  - Returns HTTP `429 Too Many Requests` with `Retry-After` header.
  - OWASP security headers applied via HTTP middleware to all responses: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `X-XSS-Protection`.
* **Status:** ✅ Implemented & Tested (34-Agent Alignment Audit)
* **Files:** [`app/core/rate_limiter.py`](file:///D:/PyCharm_Projects/AI%20Sport/app/core/rate_limiter.py), [`app/main.py`](file:///D:/PyCharm_Projects/AI%20Sport/app/main.py)

---

## ADR 007: Observability Stack — Prometheus /metrics + Sentry DSN

* **Context:** Production deployment requires real-time error tracking and infrastructure monitoring for SRE on-call alerting.
* **Decision:**
  - Expose `/metrics` endpoint in Prometheus text format: `http_requests_total`, `http_errors_total`, `process_uptime_seconds`, `aes256_encryption_active`.
  - Integrate Sentry SDK for exception capture. PII masking: `send_default_pii=False`. Middleware catches all unhandled exceptions.
  - Grafana dashboard JSON in `deploy/grafana_dashboard.json` pre-configured with HTTP latency panels, 5xx error rates, and Gemini API call counters.
  - Prometheus scrape config in `deploy/prometheus.yml` targeting 4 exporters: FastAPI backend, Nginx, PostgreSQL, Redis.
* **Status:** ✅ Implemented & Tested (Phase 4)
* **Files:** [`app/main.py`](file:///D:/PyCharm_Projects/AI%20Sport/app/main.py), [`deploy/prometheus.yml`](file:///D:/PyCharm_Projects/AI%20Sport/deploy/prometheus.yml), [`deploy/grafana_dashboard.json`](file:///D:/PyCharm_Projects/AI%20Sport/deploy/grafana_dashboard.json)

---

## ADR 008: WebBluetooth BLE Real-Time Heart Rate Streaming

* **Context:** Athletes use BLE chest straps (Polar H10, Garmin HR, Wahoo TICKR). Real-time HR display without mobile app installation is required for PWA.
* **Decision:**
  - Implement Web Bluetooth API in `frontend/pwa_athlete/index.html` using GATT **Heart Rate Service (0x180D)** / **Heart Rate Measurement characteristic (0x2A37)**.
  - Parse UINT8/UINT16 HR formats, Contact Status, Energy Expended, and RR-intervals (for online HRV computation).
  - Demo mode (`#ble-demo-btn`) for testing without physical hardware.
  - Live Chart.js rolling 30-second window updating at 1 Hz.
* **Status:** ✅ Implemented (34-Agent Alignment Audit, wearable_iot_hardware_specialist)
* **Files:** [`frontend/pwa_athlete/index.html`](file:///D:/PyCharm_Projects/AI%20Sport/frontend/pwa_athlete/index.html)

---

## ADR 009: 3-Layer Hierarchical Matrix MAS Architecture with Deterministic Orchestrator

* **Date:** 2026-08-01
* **Context:** As-Is система (35 агентов, 6 крыльев) не имела Оркестратора, Blackboard и формального протокола разрешения конфликтов. Wing Leads совмещали роли Manager и Worker (SRP violation). Отсутствовали Policy Keepers с правом блокировки задач.
* **Decision:**
  - Рефакторинг в **3-слойную иерархическую матричную архитектуру** (To-Be):
    * **Core**: `orchestrator_engine` (State Machine), `blackboard_manager`, `human_escalation_handler`
    * **Layer 1 — Policy**: 4 Policy Keepers с Arbitration Priority P1→P4
    * **Layer 2 — Management**: 6 Team Leads (координация без права блокировки)
    * **Layer 3 — Execution**: 25 Workers (max 3 self-fix attempts)
  - **Orchestrator**: Python `orchestrator.py` (State Machine) + `routing_rules.yaml` (YAML конфиг, нет правки Python)
  - **Blackboard**: FileSystem `blackboard/tasks/*.json` с абстрактным `BlackboardAdapter` (→ Redis/PG в одну строку)
  - **Micro-communication**: прямые вызовы Lead↔Worker без записи в Blackboard (экономия токенов); только финальные исходы пишутся в Blackboard
  - **Arbitration Hierarchy**: P1 (Security) → P2 (Legal) → P3 (Finance/scope_reduce) → P4 (Product/adapt)
  - **Human-in-the-Loop**: Circuit Breaker → `INTERRUPT_REQ_<task_id>.json` → ожидание решения
  - **3 агента удалены** (дубли/поглощены): `product_saas_architect`, `ip_trademark_counsel`, `cloud_finops_cost_engineer`
  - **7 новых агентов**: 3 Core + 4 Policy Keepers
* **Consequences:**
  - Итого: 38 ролей (3 Core + 4 Layer 1 + 6 Layer 2 + 25 Layer 3)
  - Все задачи проходят через Policy Gates перед выполнением
  - Конфликты требований разрешаются детерминированно без Human-in-the-Loop (кроме P1/P2 Hard Block)
  - Routing без правки Python: `routing_rules.yaml` достаточно
* **Status:** ✅ Implemented (MAS Refactor ЭТАП 2, 2026-08-01)
* **Files:**
  - [`agents_config.json`](file:///D:/PyCharm_Projects/AI%20Sport/agents_config.json)
  - [`orchestrator/orchestrator.py`](file:///D:/PyCharm_Projects/AI%20Sport/orchestrator/orchestrator.py)
  - [`orchestrator/blackboard_adapter.py`](file:///D:/PyCharm_Projects/AI%20Sport/orchestrator/blackboard_adapter.py)
  - [`orchestrator/routing_rules.yaml`](file:///D:/PyCharm_Projects/AI%20Sport/orchestrator/routing_rules.yaml)
