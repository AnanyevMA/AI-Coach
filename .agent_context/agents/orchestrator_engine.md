# Agent State: orchestrator_engine

> **Layer:** Core
> **Role:** Deterministic Orchestration State Machine
> **Status:** Active — Always Running
> **Version:** 2.0.0

---

## Primary Responsibilities

- Читает Blackboard (`blackboard/tasks/*.json`) и продвигает задачи по State Machine
- Триггерит агентов Layer 1 → 2 → 3 в строгом порядке на основе статуса задачи
- Применяет Arbitration Hierarchy при конфликте Policy Gates
- Создаёт `INTERRUPT_REQ_<task_id>.json` при Circuit Breaker срабатывании

## State Machine Transitions

```
BACKLOG → ENRICHING        : назначить Policy Keepers из routing_rules.yaml
ENRICHING → READY_FOR_DEV  : все policy_gates = APPROVED
ENRICHING → BLOCKED        : любой policy_gate = REJECTED (P1/P2) или scope_reduce (P3)
READY_FOR_DEV → IN_PROGRESS: Team Lead назначен, Worker вызван
IN_PROGRESS → CODE_REVIEW  : Worker завершил execution.attempt <= 3
IN_PROGRESS → BLOCKED      : attempt = 3 AND Team Lead reconfig_attempts >= 2
CODE_REVIEW → COMPLIANCE_REVIEW: review = PASS
COMPLIANCE_REVIEW → DONE   : compliance = PASS
* → BLOCKED                : P1 REJECT немедленно
```

## Arbitration Rules

```python
PRIORITY = [
    "security_policy_keeper",       # P1: блокирует всё немедленно
    "legal_compliance_policy_keeper",# P2: блокирует фичу
    "finance_budget_policy_keeper",  # P3: ограничивает scope
    "product_ux_policy_keeper",      # P4: адаптируется
]
```

## Key Artifacts

- [`orchestrator/orchestrator.py`](file:///D:/PyCharm_Projects/AI%20Sport/orchestrator/orchestrator.py) — State Machine Engine
- [`orchestrator/routing_rules.yaml`](file:///D:/PyCharm_Projects/AI%20Sport/orchestrator/routing_rules.yaml) — маршрутизация задач
- [`blackboard/tasks/`](file:///D:/PyCharm_Projects/AI%20Sport/blackboard/tasks) — Task JSON артефакты

## Last Significant Actions

- 2026-08-01: Создан в рамках ЭТАПА 2 рефакторинга (3-слойная To-Be архитектура)
- Заменяет ручную передачу задач между агентами
