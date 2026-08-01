# 🚀 Project Bootstrap Pack: AI Adaptive Coach v7.0

Данный файл содержит полный пакет для быстрого запуска разработки приложения **AI Adaptive Coach v7.0** с нуля в Google Antigravity с использованием роя из 20 агентов.

---

## 📂 Шаг 1. Подготовка Рабочей Директории

1. Создайте папку проекта на вашем диске:
   `C:\Users\Anany\.gemini\antigravity\scratch\ai_coach_v7`
2. Откройте Google Antigravity и установите эту папку в качестве **активного Workspace**.

---

## 🏛️ Шаг 2. Полная Мультиагентная Иерархия (20 Агентов, 5 Крыльев)

```mermaid
flowchart TD
    ORCH[👑 Chief Product & Engineering Director<br/><i>orchestrator</i>]

    ORCH --> MED[🩺 1. Medical & Sports Science Wing]
    ORCH --> LEG[⚖️ 2. Legal & Regulatory Compliance Wing]
    ORCH --> RES[🔍 3. Research & Product Discovery Wing]
    ORCH --> ENG[⚙️ 4. Engineering & Design Wing]
    ORCH --> MKT[📈 5. Growth & Community Wing]

    subgraph "🩺 1. Медицинское Крыло"
        MED --> MED_DOC[🩺 Chief Sports Medicine Officer: <i>sports_medicine_physician</i>]
        MED --> PUBMED[🧪 Sports Evidence Researcher: <i>sports_science_researcher</i>]
        MED --> BIOMEC[🦵 Biomechanics Physiologist: <i>biomechanics_physiologist</i>]
    end

    subgraph "⚖️ 2. Юридическое Крыло"
        LEG --> LAW_GLOBAL[⚖️ Global SaaS Legal Counsel: <i>legal_compliance_counsel</i>]
        LEG --> LAW_RU[🇷🇺 Russian Legal Counsel (152/323/38/54-ФЗ): <i>ru_compliance_counsel</i>]
        LEG --> DPO[🛡️ Data Protection Officer (GDPR/HIPAA): <i>data_privacy_dpo</i>]
    end

    subgraph "🔍 3. Исследовательское Крыло"
        RES --> RES_LEAD[🔍 Research Swarm Lead: <i>research_swarm_lead</i>]
        RES --> MKT_RES[📊 Athlete & Market Researcher: <i>market_user_researcher</i>]
        RES --> COACH_ADV[👨‍🏫 B2B Coach Advocate: <i>coach_experience_advocate</i>]
    end

    subgraph "⚙️ 4. Инженерное Крыло"
        ENG --> ENG_LEAD[⚙️ Technical Lead & Architect: <i>engineering_lead</i>]
        ENG --> UIUX[🎨 UI/UX Designer (Next.js/PWA): <i>ui_ux_design_system</i>]
        ENG --> AI_ENG[🧠 AI Prompt Engineer: <i>sports_ai_engineer</i>]
        ENG --> BACK[🔌 Async Backend Integrator: <i>backend_integrator</i>]
        ENG --> DATA[📈 Telemetry & FIT Data Engineer: <i>analytics_data_engineer</i>]
        ENG --> QA[🛡️ QA & Safety Auditor: <i>qa_safety_auditor</i>]
        ENG --> DEVOPS[🚀 SRE & DevOps Engineer: <i>devops_infra</i>]
    end

    subgraph "📈 5. Маркетинговое Крыло"
        MKT --> MKT_LEAD[📈 Go-To-Market Lead: <i>growth_product_lead</i>]
        MKT --> SAAS[💎 SaaS Product Manager: <i>product_saas_architect</i>]
        MKT --> GROWTH[📢 Growth & Community Manager: <i>growth_marketer</i>]
        MKT --> COPY[✍️ Technical UX Copywriter: <i>content_copywriter</i>]
    end
```

---

## 🗺️ Шаг 3. Итоговый План Реализации (Phases 0 - 4)

| Фаза | Задача | Ответственные Агенты | Ключевые Результаты |
| :--- | :--- | :--- | :--- |
| **Phase 0** | **Исследования, Юриспруденция и Медицина** | `sports_science_researcher`, `sports_medicine_physician`, `ru_compliance_counsel`, `legal_compliance_counsel`, `market_user_researcher` | 📜 Документы 152-ФЗ, 323-ФЗ, 38-ФЗ, ToS, Medical Disclaimer.<br/>🧪 Мета-анализы из PubMed по $HRV$ и восстановлению коленей.<br/>📊 Спецификация болей тренеров (B2B). |
| **Phase 1** | **Архитектура & Локальный Бэкенд в РФ** | `engineering_lead`, `backend_integrator`, `ru_compliance_counsel`, `devops_infra` | ⚡ Проект на Python 3.11+ (FastAPI + PostgreSQL + Redis + Alembic).<br/>🔐 Шифрование AES-256 персональных фитнес-данных.<br/>☁️ Настройка серверов в РФ (Selectel / Yandex Cloud). |
| **Phase 2** | **ИИ-Движок & Анализ Телеметрии** | `sports_ai_engineer`, `analytics_data_engineer`, `qa_safety_auditor` | 🧠 AICoachEngine на Gemini 1.5 Pro с проверкой красных флагов.<br/>📈 Парсинг `.FIT` файлов (пульс, темп, каденс, мощность).<br/>🛡️ Эвристический fallback-режим при сбоях ИИ. |
| **Phase 3** | **Интерфейсы B2C и B2B (Bot + Portal)** | `ui_ux_design_system`, `content_copywriter`, `backend_integrator` | 📱 Telegram Bot v3 / PWA для спортсменов.<br/>💻 Web Кабинет Тренера на React / Next.js (сводная аналитика группы). |
| **Phase 4** | **Деплой, Защита Данных и Бета-Тест** | `devops_infra`, `growth_marketer`, `orchestrator` | 🚀 Docker-compose, SSL, Grafana/Sentry.<br/>📢 Сбор 50 атлетов и 5 тренеров в закрытый бета-тест. |

---

## 💬 Шаг 4. Главный Стартовый Промпт (Master Prompt)

Скопируйте текст ниже и вставьте его в чат Antigravity при первом запуске в рабочей директории:

```markdown
Привет! Мы начинаем полную разработку приложения AI Adaptive Coach v7.0 с нуля в текущей рабочей директории. 

Ты выступаешь в роли Chief Product & Engineering Director (Orchestrator). В твое подчинение входит рой из 20 специализированных агентов, разделенных на 5 крыльев:
1. 🩺 Medical & Sports Science Wing (sports_medicine_physician, sports_science_researcher, biomechanics_physiologist)
2. ⚖️ Legal & Regulatory Compliance Wing (legal_compliance_counsel, ru_compliance_counsel, data_privacy_dpo)
3. 🔍 Research & Product Discovery Wing (research_swarm_lead, market_user_researcher, coach_experience_advocate)
4. ⚙️ Engineering & Design Wing (engineering_lead, ui_ux_design_system, sports_ai_engineer, backend_integrator, analytics_data_engineer, qa_safety_auditor, devops_infra)
5. 📈 Growth & Community Wing (growth_product_lead, product_saas_architect, growth_marketer, content_copywriter)

Твоя первая задача — инициализировать эти роли с помощью инструмента define_subagent (установив enable_subagent_tools: true для Тимлидов) и сразу запустить Фазу 0 (Phase 0: Research, Medical & RU Legal):
1. Вызови ru_compliance_counsel и legal_compliance_counsel для подготовки документации по 152-ФЗ, 323-ФЗ, 38-ФЗ, 54-ФЗ, ToS и Medical Disclaimer в папке /docs/legal/.
2. Вызови sports_science_researcher и sports_medicine_physician для поиска мета-анализов в PubMed и создания врачебного регламента красных флагов в /docs/medical/.
3. Вызови market_user_researcher и coach_experience_advocate для создания спецификации B2C атлета и B2B Кабинета Тренера в /docs/product/.

Приступай к выполнению Фазы 0!
```
