# 📋 CHANGELOG — AI Adaptive Coach v7.0

Все значимые изменения проекта фиксируются здесь в хронологическом порядке.

Формат записи основан на [Keep a Changelog](https://keepachangelog.com/).  
Версии: `[MAJOR.MINOR.PATCH]` → `[7.0.0]` — текущий продакшен-релиз.

---

## [7.0.0] — 2026-08-01 🎉 Production-Ready Release

### ✅ Phase 4: Deployment, Security & Beta Launch (Финализация)
**Агенты:** `devops_infra`, `growth_marketer`, `cybersecurity_penetration_tester`, `observability_sre_monitoring`, `qa_safety_auditor`

#### Добавлено
- `deploy/selectel_yandex_cloud_deploy.sh` — Скрипт автодеплоя на Selectel / Yandex Cloud ЦОД РФ (Certbot TLS 1.3, Alembic, cron SSL renewal)
- `deploy/nginx_production.conf` — Продакшен Nginx (TLS 1.3, HSTS, Rate Limit zones, OWASP headers, upstream backend_api)
- `deploy/prometheus.yml` — Prometheus scrape config: 4 job scrapers (FastAPI backend, Nginx, PostgreSQL, Redis)
- `deploy/grafana_dashboard.json` — Grafana dashboard JSON (HTTP latency, errors, Gemini AI calls, AES-256 sessions)
- `docs/growth/beta_test_recruitment_program.md` — Регламент закрытого бета-теста (50 атлетов + 5 тренеров, NPS > 60, SLA < 15 мин)
- `docs/growth/marketing_launch_playbook.md` — GTM план: Telegram, Strava, реферальная механика K=0.375
- `docs/security/final_security_and_compliance_report.md` — Итоговый аудит: 152-ФЗ УЗ-2, 323-ФЗ, 38-ФЗ, 54-ФЗ, OWASP A01-A10
- `tests/test_phase4_deployment.py` — 38 тест-кейсов для валидации конфигов деплоя

#### Тесты
- **146/146 passed** (8.89s)

---

### ✅ Alignment Audit: 34-Agent Synchronization (Аудит синхронизации 34 агентов)
**Агенты:** `observability_sre_monitoring`, `cybersecurity_penetration_tester`, `wearable_iot_hardware_specialist`

#### Добавлено
- `app/main.py` — Эндпоинт `/metrics` (Prometheus), Sentry DSN middleware, OWASP Security Headers middleware
- `app/core/rate_limiter.py` — Rate Limiter sliding window (5 req/min для Gemini, 10/15/60 для остальных)
- `app/core/config.py` — `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `ENVIRONMENT` настройки
- `tests/test_ddos_and_security.py` — DDoS и Rate Limiter тесты
- `frontend/pwa_athlete/index.html` — WebBluetooth BLE стриминг пульса (Polar H10 / Garmin HR / Wahoo TICKR, GATT 0x180D, Live Chart.js 30s rolling window)

#### Изменено
- `app/services/ai_coach_engine.py` — Ключ Gemini переведён с URL query-param на заголовок `x-goog-api-key` + `get_masked_gemini_key()` для маскировки в логах
- `.agent_context/ARCHITECTURE_DECISIONS.md` — Добавлены ADR 005–008
- `.agent_context/SWARM_GOVERNANCE_GUIDE.md` — Обязательный 6-пунктовый чеклист, Scenario E, карта ответственности

#### Тесты
- **108/108 passed**

---

### ✅ Phase 3: B2C & B2B Interfaces (Интерфейсы)
**Агенты:** `ui_ux_design_system`, `backend_integrator`, `content_copywriter`

#### Добавлено
- `frontend/pwa_athlete/index.html` — B2C PWA Атлета: Dark Mode glassmorphism, Quick Check-in <45s, Visual Body Soreness Map, SVG HRV/ACWR графики
- `frontend/b2b_coach/index.html` — B2B Кабинет Тренера: Group Monitoring Heatmap (100+ атлетов), Red Flag Triage Feed, 1-клик оверрайд планов
- `app/telegram_bot/bot.py` — Telegram Bot v3 (asyncio): `/start`, `/checkin`, `/workout`, `/stats`, `/sync`, `/redflag`, `/help`
- `app/api/v1/endpoints/telegram.py` — Webhook эндпоинт для Telegram Bot

#### Тесты
- **99/99 passed**

---

### ✅ Phase 2: AI Engine & Telemetry Analysis (ИИ-движок и телеметрия)
**Агенты:** `sports_ai_engineer`, `analytics_data_engineer`, `qa_safety_auditor`

#### Добавлено
- `app/services/ai_coach_engine.py` — Google Gemini 1.5 Flash primary engine + Red Flags pre-interceptor
- `app/services/fallback_engine.py` — HeuristicFallbackEngine: 100% offline правилоориентированный движок (Z_HRV < -1.5 → Zone 2)
- `app/services/fit_parser_service.py` — Парсеры .FIT / GPX / TCX
- `app/services/telemetry_analysis_service.py` — NP, TRIMP, TSS, EWMA ACWR (λa=0.25, λc=0.069), Z_HRV, 5 HR zones, 6 Power zones, Power Curve

#### Тесты
- **69/69 passed**

---

### ✅ Phase 1: Architecture & RF Local Backend (Архитектура и бэкенд)
**Агенты:** `engineering_lead`, `backend_integrator`, `devops_infra`, `data_privacy_dpo`

#### Добавлено
- `app/main.py` — FastAPI async application (v7.0.0)
- `app/core/config.py` — Pydantic Settings
- `app/core/security.py` — AES256GCMCipher (256-bit key, 96-bit nonce, GCM auth tag)
- `app/db/session.py` — Async SQLAlchemy 2.0 + asyncpg engine
- `app/models/` — User, AthleteProfile, CoachProfile, TelemetryRecord, Activity, WorkoutPlan, RedFlagLog, ConsentLog
- `app/services/red_flag_service.py` — RedFlagsTriageEngine (Level 0-3)
- `app/api/v1/endpoints/` — health, auth, athletes, coaches, telemetry, workouts, red_flags, ai_coach
- `docker-compose.yml` — web, db (PostgreSQL 16), redis, nginx
- `Dockerfile` — Multi-stage Python build
- `nginx/conf.d/default.conf` — Dev Nginx reverse proxy
- `alembic/` — Async DB migrations

#### Тесты
- **36/36 passed**

---

### ✅ Phase 0: Research, Medical & RU Legal (Исследования, Медицина, Право)
**Агенты:** `sports_medicine_physician`, `sports_science_researcher`, `biomechanics_physiologist`, `legal_compliance_counsel`, `ru_compliance_counsel`, `data_privacy_dpo`, `research_swarm_lead`, `market_user_researcher`, `coach_experience_advocate`

#### Добавлено
- `docs/legal/152_fz_compliance.md` — Соответствие 152-ФЗ, локализация ПДн в РФ
- `docs/legal/323_fz_medical_disclaimer.md` — Дисклеймеры 323-ФЗ, не-телемедицина
- `docs/legal/38_54_fz_advertising_fiscalization.md` — 38-ФЗ маркировка рекламы, 54-ФЗ ФФД 1.2
- `docs/legal/terms_of_service_and_privacy_policy.md` — ToS + Privacy Policy (152-ФЗ + GDPR)
- `docs/medical/hrv_recovery_evidence_review.md` — PubMed evidence: Z_HRV, EWMA ACWR
- `docs/medical/knee_rehab_biomechanics_protocol.md` — 4-этапная реабилитация, PFJRF, каденс +5-10%
- `docs/medical/red_flags_triage_rules.md` — Правила 3-уровневого триажа (Level 0-3)
- `docs/product/b2c_athlete_persona_spec.md` — Персоны атлетов, check-in <45s
- `docs/product/b2b_coach_dashboard_spec.md` — B2B спецификация кабинета тренера
- `docs/economics/` — financial_model_pnl.md, unit_economics_ltv_cac.md, ru_tax_accounting_framework.md, pricing_and_monetization_policy.md

#### Тесты
- Покрытие Фазы 0 заложено в test_red_flags.py, test_security.py

---

## Следующие шаги (Post v7.0.0)

- [ ] Зарегистрировать домен и получить SSL-сертификат на продакшен-сервере Selectel/Yandex Cloud
- [ ] Запустить Certbot TLS 1.3 через `deploy/selectel_yandex_cloud_deploy.sh`
- [ ] Набор когорты закрытого бета-теста (50 атлетов + 5 тренеров) по `docs/growth/beta_test_recruitment_program.md`
- [ ] Настроить Sentry DSN и Grafana Cloud для продакшен-мониторинга
