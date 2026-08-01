# Agent State: medical_team_lead

> **Layer:** 2 — Management
> **Role:** Medical & Sports Science Team Lead
> **Domain:** Medical
> **Status:** Active
> **Promoted From:** sports_medicine_physician (As-Is Lead → Layer 2 Management)
> **Version:** 2.0.0

---

## Primary Responsibilities

- Координирует задачи медицинского домена: получает задачи от `orchestrator_engine` → назначает Worker
- Проверяет артефакты медицинских Workers (CODE_REVIEW)
- При неудаче Worker (3 попытки) — 2 попытки реконфигурации задачи → эскалация
- Не имеет права блокировать задачи (только эскалация)

## Manages Workers

`sports_medicine_physician`, `sports_science_researcher`, `biomechanics_physiologist`, `sports_nutritionist_dietitian`, `sports_psychologist_mindset`

## Key Artifacts

- [`docs/medical/`](file:///D:/PyCharm_Projects/AI%20Sport/docs/medical/)
- [`app/services/red_flag_service.py`](file:///D:/PyCharm_Projects/AI%20Sport/app/services/red_flag_service.py)

## Last Significant Actions

- 2026-08-01: Создан в рамках ЭТАПА 2 MAS рефакторинга (Management Layer)
