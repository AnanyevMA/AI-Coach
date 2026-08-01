# 📖 Swarm Governance & Maintenance Guide: AI Adaptive Coach v7.0

> **Location:** `.agent_context/SWARM_GOVERNANCE_GUIDE.md`  
> **Purpose:** Operational protocols for maintaining project quality, agent context, and architectural integrity across all phases.  
> **Last Updated:** 2026-08-01 (Post Phase 4 Complete — 146/146 tests passing)

---

## 🔄 Обязательный Чеклист После Любых Изменений

> [!IMPORTANT]
> После КАЖДОГО значимого изменения в проекте необходимо выполнить **все** пункты этого чеклиста. Пропуск ведёт к потере контекста роя.

```
[ ] 1. Запустить полный тест-сюит: py -3 -m pytest — нет регрессий
[ ] 2. Обновить .agent_context/SWARM_STATE.md — фазы, счётчик тестов, индекс файлов
[ ] 3. Обновить .agent_context/ARCHITECTURE_DECISIONS.md — добавить ADR для нового решения
[ ] 4. Обновить файл состояния затронутого агента в .agent_context/agents/<agent>.md
[ ] 5. Обновить README.md в корне проекта — если изменилась структура или функциональность
[ ] 6. Обновить .agent_context/governance_manifest.json — если добавлены файлы, агенты, документы или ADR
[ ] 7. Зафиксировать изменение в CHANGELOG.md
[ ] 8. Запустить финальный валидатор: py -3 scripts/validate_governance.py — 0 FAIL
```


---

## Governance Manifest: единая точка конфигурации проверок

> **Файл:** `.agent_context/governance_manifest.json`

Это **живой конфиг** — НЕ правьте `scripts/validate_governance.py` для рутинных изменений.
Все проверки строятся динамически по содержимому манифеста.

### Что обновлять при изменениях проекта:

| Изменение в проекте | Что обновить в manifest |
| :--- | :--- |
| Добавлен новый агент | `agents.explicit_required` (или SWARM_STATE.md — авто-обнаружение) |
| Добавлен новый деплой-файл | Добавить запись в `deploy_artifacts[]` |
| Добавлен новый ключевой исходник | Добавить запись в `source_files[]` |
| Добавлен новый ADR | Обновить `architecture_decisions.min_adr_count` |
| Добавлен обязательный документ | Добавить в `docs.explicit_required[]` |
| Изменилось количество тестов | Обновить `thresholds.min_test_count` |
| Добавлена новая проверка безопасности | Добавить запись в `custom_checks[]` |
| Изменилась версия | Обновить `project.version` и `governance_files[README].required_keywords` |

### Команды валидатора:

```bash
# Полная проверка всего проекта
py -3 scripts/validate_governance.py

# Показать текущую конфигурацию манифеста
py -3 scripts/validate_governance.py --show-manifest

# Проверить только конкретную секцию (быстро)
py -3 scripts/validate_governance.py --section agents
py -3 scripts/validate_governance.py --section docs
py -3 scripts/validate_governance.py --section adr
py -3 scripts/validate_governance.py --section custom

# Пропустить pytest (например, при работе без venv)
py -3 scripts/validate_governance.py --no-pytest
```

### Типы кастомных проверок (custom_checks):

| Тип | Назначение |
| :--- | :--- |
| `file_exists` | Файл должен существовать |
| `file_exists_any` | Хотя бы один из списка должен существовать |
| `file_contains_pattern` | Файл должен содержать regex-паттерн |
| `file_no_pattern` | Файл НЕ должен содержать паттерн (безопасность) |
| `project_no_pattern` | Никакой `.py` файл в папке не должен содержать паттерн |
| `directory_naming` | Все файлы в папке должны соответствовать паттерну имени |

---

## Сценарии Операционного Обслуживания

### Scenario A: Добавление нового агента (Adding a New Agent)
1. **Создать файл состояния:** `.agent_context/agents/<new_agent_name>.md` по шаблону ниже.
2. **Добавить в иерархию:** Добавить агента в соответствующее крыло в `.agent_context/SWARM_STATE.md`.
3. **Привязать к лиду крыла:** Указать Wing Lead в файле состояния.
4. **Обновить счётчик:** Обновить число агентов в заголовке `SWARM_STATE.md`.
5. **Обновить манифест:** Если агент критический, добавить в `agents.explicit_required` в `governance_manifest.json`.


**Шаблон файла состояния нового агента:**
```markdown
# 🤖 Agent State: <agent_name>

> **Role:** <Роль>
> **Wing:** <Крыло>
> **Wing Lead:** <Имя лида>
> **Status:** Active

## 🎯 Primary Responsibilities
- <Обязанности 1>

## 📄 Key Artifacts Produced & Maintained
- [`<file.py>`](file:///D:/PyCharm_Projects/AI Sport/<file.py>)

## 📋 Last Significant Actions
| Дата | Фаза | Действие | Результат |
| :--- | :--- | :--- | :--- |
| YYYY-MM-DD | Phase N | Создан файл X | ✅ |

## 🚦 Current Status & Blockers
- **Активных блокеров:** Нет
```

---

### Scenario B: Пересмотр структуры агентов (Revising Agent Hierarchy)
1. Обновить Mermaid-диаграмму и списки крыльев в `SWARM_STATE.md`.
2. Обновить файлы состояний всех затронутых агентов.
3. Добавить запись в `ARCHITECTURE_DECISIONS.md` с обоснованием реструктуризации.

---

### Scenario C: Добавление новой концепции или архитектурного решения
1. **Написать ADR:** Новая запись в `.agent_context/ARCHITECTURE_DECISIONS.md` (`ADR 00N: <Название>`). Указать Context, Decision, Status, Files.
2. **Обновить спецификации:** Создать или обновить документ в `docs/` (`docs/product/`, `docs/medical/`, `docs/legal/`, `docs/economics/`).
3. **Написать тесты:** Добавить тест-кейсы в `tests/` для новой концепции.
4. **Обновить состояние агента**, который отвечает за это крыло.

---

### Scenario D: Добавление мелкой функции или хотфикса
1. Убедиться, что изменение не нарушает 152-ФЗ (шифрование AES-256) и правила триажа Red Flags.
2. Реализовать код и соответствующий pytest-тест.
3. Запустить `py -3 -m pytest` — убедиться в 0 регрессий.
4. Добавить 1-строчную запись в раздел `## 📋 Last Significant Actions` файла состояния агента.
5. Обновить счётчик тестов в `SWARM_STATE.md`.

---

### Scenario E: Завершение Фазы проекта
1. Обновить статус фазы на ✅ COMPLETED в таблице `SWARM_STATE.md`.
2. Зафиксировать итоговое число пройденных тестов в строке фазы.
3. Обновить раздел `## 📁 Key File Index` в `SWARM_STATE.md`.
4. Обновить `walkthrough.md` с описанием всех изменений фазы.
5. Обновить `README.md` в корне проекта.

---

## 🛡️ Правила Защиты Ключевых Инвариантов

| Инвариант | Правило | Файл |
| :--- | :--- | :--- |
| 152-ФЗ шифрование | Любые PII-поля ВСЕГДА через `AES256GCMCipher` | `app/core/security.py` |
| 323-ФЗ граница | LLM НИКОГДА не диагностирует заболевания, блокировка через Red Flags | `app/services/red_flag_service.py` |
| Gemini API ключ | API-ключ ТОЛЬКО в env vars, НИКОГДА в коде, маскировка в логах | `app/core/config.py` |
| Тесты | `py -3 -m pytest` ВСЕГДА 100% зелёный перед любым коммитом | `tests/` |
| Тест-прогресс | Счётчик тестов в `SWARM_STATE.md` ВСЕГДА актуален | `.agent_context/SWARM_STATE.md` |

---

## 📊 Карта ответственности (Какой агент за что отвечает)

| Изменение | Ответственный агент | Файл состояния |
| :--- | :--- | :--- |
| Изменение в API/Backend | `engineering_lead`, `backend_integrator` | `engineering_lead.md` |
| Изменение ИИ-промптов | `sports_ai_engineer` | `sports_ai_engineer.md` |
| Изменение медицинских правил | `sports_medicine_physician` | `sports_medicine_physician.md` |
| Изменение юридических документов | `legal_compliance_counsel`, `ru_compliance_counsel` | `legal_compliance_counsel.md` |
| Изменение цен/тарифов | `saas_pricing_monetization_expert`, `cfo_financial_strategist` | `saas_pricing_monetization_expert.md` |
| Изменение деплоя/инфраструктуры | `devops_infra`, `cicd_automation_engineer` | `devops_infra.md` |
| Изменение PWA/Frontend | `ui_ux_design_system`, `mobile_native_engineer` | `ui_ux_design_system.md` |
| Добавление тестов | `qa_safety_auditor` | `qa_safety_auditor.md` |
| Изменение финансовой модели | `cfo_financial_strategist`, `unit_economics_analyst` | `cfo_financial_strategist.md` |
| Безопасность/пентест | `cybersecurity_penetration_tester` | `cybersecurity_penetration_tester.md` |
