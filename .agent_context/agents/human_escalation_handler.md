# Agent State: human_escalation_handler

> **Layer:** Core
> **Role:** Human-in-the-Loop Interface & Circuit Breaker
> **Status:** Active (triggered on BLOCKED events)
> **Version:** 2.0.0

---

## Primary Responsibilities

- Формирует `INTERRUPT_REQ_<task_id>.json` при срабатывании Circuit Breaker
- Ожидает Human решения (polling `human_decision` поля задачи)
- После получения решения возобновляет задачу или закрывает её
- Логирует все Escalation события в `blackboard/interrupts/`

## Escalation Triggers

| Триггер | Условие |
|---|---|
| Worker exhausted | `execution.attempt >= 3` AND `team_lead.reconfig_attempts >= 2` |
| P1 Hard Block | `security_policy_keeper` = REJECTED (немедленная эскалация) |
| P2 Hard Block | `legal_compliance_policy_keeper` = REJECTED |
| SLA breach | задача в одном статусе > `sla_hours` |

## INTERRUPT_REQ Format

```json
{
  "task_id": "TASK-YYYYMMDD-NNNN",
  "failure_reason": "...",
  "blocked_by_policy": "...",
  "policy_rejection_reason": "...",
  "error_logs": ["attempt_1: ...", "attempt_2: ..."],
  "proposed_options": ["Option A: ...", "Option B: ...", "Option C: ..."],
  "awaiting_human_input": true,
  "created_at": "ISO-8601",
  "sla_hours": 24
}
```

## Key Artifacts

- [`blackboard/interrupts/`](file:///D:/PyCharm_Projects/AI%20Sport/blackboard/interrupts/)
- [`orchestrator/orchestrator.py`](file:///D:/PyCharm_Projects/AI%20Sport/orchestrator/orchestrator.py) — circuit_breaker() метод

## Last Significant Actions

- 2026-08-01: Создан в рамках ЭТАПА 2 (новый механизм Human-in-the-Loop)
