#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_governance.py — Универсальная динамическая точка проверки проекта.

Архитектура:
    Этот скрипт СОЗНАТЕЛЬНО не содержит хардкодированных списков агентов,
    файлов, ADR или документов. Вся конфигурация вынесена в:

        .agent_context/governance_manifest.json

    Manifest — живой документ. Его обновляют агенты и разработчики при
    изменении проекта. Валидатор читает manifest и строит проверки динамически.

Что делает валидатор:
    1. Читает governance_manifest.json
    2. Проверяет обязательные файлы управления (из manifest)
    3. AUTO-DISCOVERS агентов из SWARM_STATE.md, сверяет с agents/ dir
    4. Проверяет наличие и содержимое deploy-артефактов (из manifest)
    5. AUTO-DISCOVERS ADR из ARCHITECTURE_DECISIONS.md (regex pattern)
    6. AUTO-DISCOVERS все .md файлы из docs/ + явно обязательные (из manifest)
    7. Проверяет исходный код (ключевые файлы + запрещённые паттерны)
    8. Запускает pytest, сверяет счётчик со SWARM_STATE.md
    9. Выполняет кастомные проверки (из секции custom_checks в manifest)
   10. Генерирует итоговый отчёт с рекомендациями

Использование:
    py -3 scripts/validate_governance.py             # полная проверка
    py -3 scripts/validate_governance.py --no-pytest  # пропустить pytest
    py -3 scripts/validate_governance.py --section agents  # только агенты
    py -3 scripts/validate_governance.py --show-manifest   # показать конфиг

Обновление конфигурации:
    НЕ ПРАВЬТЕ ЭТОТ ФАЙЛ для добавления новых агентов, документов или ADR.
    Обновляйте .agent_context/governance_manifest.json.
"""

import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import json
import re
import subprocess
import textwrap
from datetime import datetime
from pathlib import Path


# ============================================================
# ПУТИ
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
MANIFEST_PATH = BASE_DIR / ".agent_context" / "governance_manifest.json"


# ============================================================
# ЦВЕТА И ВЫВОД
# ============================================================
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

CHK_PASS = "[PASS]"
CHK_FAIL = "[FAIL]"
CHK_WARN = "[WARN]"
CHK_INFO = "[INFO]"
CHK_SKIP = "[SKIP]"


class Reporter:
    """Накапливает результаты и выводит форматированный отчёт."""

    def __init__(self):
        self._passed   = 0
        self._failed   = 0
        self._warnings = 0
        self._infos    = 0
        self._issues: list[str] = []   # только FAIL для итогового списка

    # --- вывод строк ---
    def ok(self, msg: str):
        self._passed += 1
        print(f"  {GREEN}{CHK_PASS}{RESET}  {msg}")

    def fail(self, msg: str, hint: str = ""):
        self._failed += 1
        self._issues.append(msg)
        suffix = f"  {DIM}-> {hint}{RESET}" if hint else ""
        print(f"  {RED}{CHK_FAIL}{RESET}  {msg}{suffix}")

    def warn(self, msg: str, hint: str = ""):
        self._warnings += 1
        suffix = f"  {DIM}-> {hint}{RESET}" if hint else ""
        print(f"  {YELLOW}{CHK_WARN}{RESET}  {msg}{suffix}")

    def info(self, msg: str):
        self._infos += 1
        print(f"  {CYAN}{CHK_INFO}{RESET}  {DIM}{msg}{RESET}")

    def skip(self, msg: str):
        print(f"  {DIM}{CHK_SKIP}  {msg}{RESET}")

    def section(self, title: str, index: int = 0, total: int = 0):
        counter = f" [{index}/{total}]" if total else ""
        print(f"\n{BOLD}{BLUE}{'=' * 65}{RESET}")
        print(f"{BOLD}{BLUE}  {title}{counter}{RESET}")
        print(f"{BOLD}{BLUE}{'=' * 65}{RESET}")

    def subsection(self, title: str):
        print(f"\n  {BOLD}-- {title} --{RESET}")

    # --- свойства ---
    @property
    def passed(self): return self._passed

    @property
    def failed(self): return self._failed

    @property
    def warnings(self): return self._warnings

    @property
    def total(self): return self._passed + self._failed + self._warnings

    def print_summary(self):
        print(f"\n{BOLD}{'=' * 65}{RESET}")
        print(f"{BOLD}  ИТОГОВЫЙ ОТЧЁТ{RESET}")
        print(f"  {GREEN}PASS:  {self._passed}{RESET}")
        print(f"  {YELLOW}WARN:  {self._warnings}{RESET}")
        print(f"  {RED}FAIL:  {self._failed}{RESET}")
        print(f"  {'─' * 35}")
        print(f"  Проверок: {self.total}")
        print(f"{BOLD}{'=' * 65}{RESET}")

        if self._issues:
            print(f"\n{BOLD}{RED}  Требуют исправления:{RESET}")
            for i, issue in enumerate(self._issues, 1):
                short = textwrap.shorten(issue, width=70, placeholder="...")
                print(f"    {i:2d}. {short}")

        if self._failed == 0 and self._warnings == 0:
            print(f"\n{GREEN}{BOLD}  >> ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ. Проект полностью синхронизирован.{RESET}\n")
        elif self._failed == 0:
            print(f"\n{YELLOW}{BOLD}  >> ПРЕДУПРЕЖДЕНИЯ: {self._warnings}. Рекомендуется устранить.{RESET}\n")
        else:
            print(f"\n{RED}{BOLD}  >> ОШИБКИ: {self._failed}. Обновите управляющие файлы!{RESET}")
            print(f"  {DIM}Чеклист: .agent_context/SWARM_GOVERNANCE_GUIDE.md{RESET}\n")

    def exit_code(self) -> int:
        return 1 if self._failed else 0


# ============================================================
# ЗАГРУЗКА МАНИФЕСТА
# ============================================================
def load_manifest(r: Reporter) -> dict | None:
    if not MANIFEST_PATH.exists():
        r.fail(
            f"governance_manifest.json НЕ НАЙДЕН: {MANIFEST_PATH.relative_to(BASE_DIR)}",
            hint="Создайте .agent_context/governance_manifest.json по шаблону из SWARM_GOVERNANCE_GUIDE.md"
        )
        return None
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = json.load(f)
        r.ok(f"governance_manifest.json загружен ({MANIFEST_PATH.stat().st_size:,} байт)")
        return manifest
    except json.JSONDecodeError as e:
        r.fail(f"governance_manifest.json содержит ошибку JSON: {e}")
        return None


# ============================================================
# 1. ОБЯЗАТЕЛЬНЫЕ ФАЙЛЫ УПРАВЛЕНИЯ
# ============================================================
def check_governance_files(r: Reporter, manifest: dict, total: int, idx: int):
    r.section("Обязательные файлы управления (.agent_context/ & root)", idx, total)
    thresholds = manifest.get("thresholds", {})
    min_bytes = thresholds.get("min_governance_file_bytes", 100)

    for entry in manifest.get("governance_files", []):
        path = BASE_DIR / entry["path"]
        desc = entry.get("description", "")
        keywords = entry.get("required_keywords", [])

        if not path.exists():
            r.fail(f"{entry['path']} — НЕ НАЙДЕН", hint=f"Создайте: {desc}")
            continue

        size = path.stat().st_size
        if size < min_bytes:
            r.warn(f"{entry['path']} — слишком мал ({size} байт)", hint="Заполните файл")
            continue

        # Проверяем обязательные ключевые слова
        if keywords:
            content = path.read_text(encoding="utf-8", errors="replace")
            missing_kw = [kw for kw in keywords if kw not in content]
            if missing_kw:
                r.fail(
                    f"{entry['path']} — не содержит ключевые слова: {missing_kw}",
                    hint=f"Обновите файл — {desc}"
                )
            else:
                r.ok(f"{entry['path']}  ({size:,} b)  [{', '.join(keywords[:2])}...]")
        else:
            r.ok(f"{entry['path']}  ({size:,} b)")


# ============================================================
# 2. АГЕНТЫ: АВТО-ОБНАРУЖЕНИЕ ИЗ SWARM_STATE.md
# ============================================================
def discover_agents_from_swarm_state(manifest: dict) -> list[str]:
    """Читает SWARM_STATE.md и извлекает имена агентов по regex-паттерну."""
    cfg = manifest.get("agents", {})
    state_file = BASE_DIR / cfg.get("swarm_state_file", ".agent_context/SWARM_STATE.md")
    pattern = cfg.get("agent_name_pattern", r"`([a-z][a-z0-9_]+)`")

    if not state_file.exists():
        return []

    content = state_file.read_text(encoding="utf-8", errors="replace")
    raw = re.findall(pattern, content)
    # Дедупликация, исключить слишком короткие и системные имена
    system_names = {"orchestrator", "lead", "agent", "agents", "wing", "doc", "file"}
    discovered = sorted({name for name in raw if len(name) > 6 and name not in system_names})
    return discovered


def check_agents(r: Reporter, manifest: dict, total: int, idx: int):
    r.section("Агенты: состояния & синхронизация с SWARM_STATE.md", idx, total)
    cfg = manifest.get("agents", {})
    agents_dir = BASE_DIR / cfg.get("agents_dir", ".agent_context/agents")
    thresholds = manifest.get("thresholds", {})
    min_bytes = thresholds.get("min_agent_state_bytes", 200)
    explicit_required = set(cfg.get("explicit_required", []))

    # Авто-обнаружение из SWARM_STATE.md
    if cfg.get("auto_discover", True):
        discovered = discover_agents_from_swarm_state(manifest)
        r.info(f"Авто-обнаружено из SWARM_STATE.md: {len(discovered)} имён агентов")
    else:
        discovered = []

    # Все .md файлы в agents/
    existing_files = {f.stem for f in agents_dir.glob("*.md")} if agents_dir.exists() else set()

    # Объединяем: авто-обнаруженные + явно обязательные
    deprecated_excluded = set(cfg.get("deprecated_excluded", []))
    all_expected = sorted((set(discovered) | explicit_required) - deprecated_excluded)

    if deprecated_excluded:
        r.info(f"Исключено (deprecated_excluded): {', '.join(sorted(deprecated_excluded))}")

    if not all_expected:
        r.warn("Список агентов пуст — проверьте SWARM_STATE.md и manifest.agents.explicit_required")
        return

    r.subsection(f"Файлы состояний ({len(all_expected)} ожидается)")

    thin_agents = []
    for agent in all_expected:
        state_file = agents_dir / f"{agent}.md"
        if not state_file.exists():
            r.fail(f"agents/{agent}.md — НЕ НАЙДЕН", hint="Создайте по шаблону из SWARM_GOVERNANCE_GUIDE.md")
        elif state_file.stat().st_size < min_bytes:
            thin_agents.append(agent)
            r.warn(
                f"agents/{agent}.md — {state_file.stat().st_size} байт (< {min_bytes})",
                hint="Добавьте '## Last Significant Actions'"
            )
        else:
            r.ok(f"agents/{agent}.md  ({state_file.stat().st_size:,} b)")

    # Файлы-сироты в agents/ (не упомянутые в SWARM_STATE)
    orphans = existing_files - set(all_expected)
    if orphans:
        for o in sorted(orphans):
            r.warn(f"agents/{o}.md — не упомянут в SWARM_STATE.md", hint="Добавьте агента в SWARM_STATE.md")

    # Итог
    r.subsection("Итог по агентам")
    r.ok(f"Всего файлов состояний в папке: {len(existing_files)}")
    r.ok(f"Ожидается (SWARM_STATE + manifest): {len(all_expected)}")
    if thin_agents:
        r.warn(f"Агентов с тонкими состояниями: {len(thin_agents)} — рекомендуется дополнить")


# ============================================================
# 3. ДЕПЛОЙ-АРТЕФАКТЫ
# ============================================================
def check_deploy_artifacts(r: Reporter, manifest: dict, total: int, idx: int):
    r.section("Продакшен деплой-артефакты", idx, total)
    thresholds = manifest.get("thresholds", {})
    min_bytes = thresholds.get("min_deploy_file_bytes", 500)

    for entry in manifest.get("deploy_artifacts", []):
        path = BASE_DIR / entry["path"]
        desc = entry.get("description", "")
        keywords = entry.get("required_keywords", [])

        if not path.exists():
            r.fail(f"{entry['path']} — НЕ НАЙДЕН", hint=desc)
            continue

        size = path.stat().st_size
        if size < min_bytes:
            r.warn(f"{entry['path']} — мал ({size} байт)")
            continue

        if keywords:
            content = path.read_text(encoding="utf-8", errors="replace")
            missing = [kw for kw in keywords if kw not in content]
            if missing:
                r.warn(f"{entry['path']} — не содержит: {missing}", hint=desc)
            else:
                r.ok(f"{entry['path']}  ({size:,} b)")
        else:
            r.ok(f"{entry['path']}  ({size:,} b)")


# ============================================================
# 4. ADR: АВТО-ОБНАРУЖЕНИЕ ИЗ ARCHITECTURE_DECISIONS.md
# ============================================================
def check_architecture_decisions(r: Reporter, manifest: dict, total: int, idx: int):
    r.section("Architecture Decision Records (ADR)", idx, total)
    cfg = manifest.get("architecture_decisions", {})
    adr_file = BASE_DIR / cfg.get("adr_file", ".agent_context/ARCHITECTURE_DECISIONS.md")
    pattern = cfg.get("adr_pattern", r"## ADR (\d+):")
    min_count = cfg.get("min_adr_count", 1)

    if not adr_file.exists():
        r.fail("ARCHITECTURE_DECISIONS.md — НЕ НАЙДЕН")
        return

    content = adr_file.read_text(encoding="utf-8", errors="replace")

    if cfg.get("auto_discover", True):
        # Находим все ADR по паттерну
        found_numbers = re.findall(pattern, content)
        unique_adrs = sorted(set(int(n) for n in found_numbers))
        r.info(f"Авто-обнаружено ADR: {len(unique_adrs)} шт. (паттерн: {pattern})")

        for n in unique_adrs:
            r.ok(f"ADR {n:03d} — зафиксирован")

        # Проверяем отсутствие пропусков в нумерации
        if unique_adrs:
            expected_seq = list(range(1, max(unique_adrs) + 1))
            gaps = [n for n in expected_seq if n not in unique_adrs]
            if gaps:
                r.warn(f"Пропуски в нумерации ADR: {gaps}", hint="Добавьте пропущенные ADR или перенумеруйте")

        if len(unique_adrs) < min_count:
            r.fail(
                f"Найдено ADR: {len(unique_adrs)}, минимум: {min_count}",
                hint=f"Добавьте ADR в {adr_file.name}"
            )
        else:
            r.ok(f"Итого ADR: {len(unique_adrs)} (минимум {min_count} — соответствует)")
    else:
        r.skip("Авто-обнаружение ADR отключено в manifest (auto_discover: false)")


# ============================================================
# 5. ДОКУМЕНТАЦИЯ: АВТО-ОБНАРУЖЕНИЕ + ЯВНЫЕ ТРЕБОВАНИЯ
# ============================================================
def check_documentation(r: Reporter, manifest: dict, total: int, idx: int):
    r.section("Документация (docs/)", idx, total)
    docs_cfg = manifest.get("docs", {})
    thresholds = manifest.get("thresholds", {})
    min_bytes = thresholds.get("min_doc_bytes", 500)
    docs_base = BASE_DIR / docs_cfg.get("base_dir", "docs")

    # Явно обязательные документы
    explicit = docs_cfg.get("explicit_required", [])
    if explicit:
        r.subsection(f"Явно обязательные документы ({len(explicit)})")
        for entry in explicit:
            path = BASE_DIR / entry["path"]
            desc = entry.get("description", "")
            if not path.exists():
                r.fail(f"{entry['path']} — НЕ НАЙДЕН", hint=desc)
            elif path.stat().st_size < min_bytes:
                r.warn(f"{entry['path']} — мал ({path.stat().st_size} байт)", hint=desc)
            else:
                r.ok(f"{entry['path']}  ({path.stat().st_size:,} b)")

    # Авто-обнаружение всех .md в docs/
    if docs_cfg.get("auto_discover", False) and docs_base.exists():
        all_docs = sorted(docs_base.rglob("*.md"))
        r.subsection(f"Авто-обнаруженные документы в docs/ ({len(all_docs)} .md файлов)")
        r.info(f"Базовая директория docs/: {docs_base}")
        empty_docs = []
        for doc in all_docs:
            size = doc.stat().st_size
            rel = doc.relative_to(BASE_DIR)
            if size < min_bytes:
                empty_docs.append(str(rel))
                r.warn(f"{rel}  ({size} байт) — пустой или слишком мал")
            else:
                r.ok(f"{rel}  ({size:,} b)")

        if not empty_docs:
            r.ok(f"Все {len(all_docs)} документов docs/ заполнены (>= {min_bytes} байт)")


# ============================================================
# 6. ИСХОДНЫЙ КОД
# ============================================================
def check_source_files(r: Reporter, manifest: dict, total: int, idx: int):
    r.section("Ключевые файлы исходного кода", idx, total)
    thresholds = manifest.get("thresholds", {})
    min_bytes = thresholds.get("min_governance_file_bytes", 100)

    for entry in manifest.get("source_files", []):
        path = BASE_DIR / entry["path"]
        desc = entry.get("description", "")
        keywords = entry.get("required_keywords", [])

        if not path.exists():
            r.fail(f"{entry['path']} — НЕ НАЙДЕН", hint=desc)
            continue

        size = path.stat().st_size
        if size < min_bytes:
            r.warn(f"{entry['path']} — мал ({size} байт)")
            continue

        if keywords:
            content = path.read_text(encoding="utf-8", errors="replace")
            missing = [kw for kw in keywords if kw.lower() not in content.lower()]
            if missing:
                r.warn(f"{entry['path']} — не найдено: {missing}", hint=desc)
            else:
                r.ok(f"{entry['path']}  ({size:,} b)  [{', '.join(keywords[:2])}...]")
        else:
            r.ok(f"{entry['path']}  ({size:,} b)  {DIM}{desc}{RESET}")


# ============================================================
# 7. PYTEST: ДИНАМИЧЕСКОЕ ЧИСЛО ТЕСТОВ
# ============================================================
def check_pytest(r: Reporter, manifest: dict, total: int, idx: int, skip: bool = False):
    r.section("Тесты: pytest vs SWARM_STATE.md", idx, total)
    if skip:
        r.skip("pytest пропущен (--no-pytest)")
        return

    thresholds = manifest.get("thresholds", {})
    min_count = thresholds.get("min_test_count", 1)
    timeout = thresholds.get("pytest_timeout_seconds", 60)
    sync_cfg = manifest.get("swarm_state_sync", {})
    swarm_file = BASE_DIR / sync_cfg.get("file", ".agent_context/SWARM_STATE.md")
    count_pattern = sync_cfg.get("test_count_pattern", r"(\d+)/(\d+)\s+Pytest")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header"],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=timeout,
        )
        output = result.stdout + result.stderr
        match = re.search(r"(\d+)\s+(?:tests?\s+(?:collected|selected))", output)

        if not match:
            r.warn("Не удалось определить число тестов из вывода pytest", hint=f"Output: {output[:200]}")
            return

        actual = int(match.group(1))
        r.ok(f"pytest собрал: {actual} тестов")

        # Сравнение с порогом
        if actual < min_count:
            r.fail(
                f"Тестов меньше минимума: {actual} < {min_count}",
                hint=f"Обновите thresholds.min_test_count в governance_manifest.json до {actual}"
            )
        else:
            r.ok(f"Тестов >= минимума: {actual} >= {min_count}")

        # Сравнение с SWARM_STATE.md
        if swarm_file.exists():
            swarm_content = swarm_file.read_text(encoding="utf-8", errors="replace")
            sm = re.search(count_pattern, swarm_content)
            if sm:
                recorded = int(sm.group(1))
                if recorded == actual:
                    r.ok(f"SWARM_STATE.md актуален: {recorded}/{actual}")
                else:
                    r.fail(
                        f"SWARM_STATE.md УСТАРЕЛ: зафиксировано {recorded}, фактически {actual}",
                        hint="Обновите счётчик тестов в SWARM_STATE.md"
                    )
            else:
                r.warn(
                    f"Счётчик тестов не найден в SWARM_STATE.md (паттерн: '{count_pattern}')",
                    hint="Добавьте строку вида '146/146 Pytest'"
                )
        else:
            r.warn(f"SWARM_STATE.md не найден: {swarm_file}")

    except subprocess.TimeoutExpired:
        r.warn(f"pytest --collect-only превысил таймаут {timeout}s")
    except Exception as e:
        r.warn(f"Ошибка запуска pytest: {e}")


# ============================================================
# 8. КАСТОМНЫЕ ПРОВЕРКИ (из manifest.custom_checks)
# ============================================================
def run_custom_checks(r: Reporter, manifest: dict, total: int, idx: int):
    r.section("Кастомные проверки (manifest.custom_checks)", idx, total)
    checks = manifest.get("custom_checks", [])

    if not checks:
        r.skip("Кастомных проверок нет — добавьте в manifest.custom_checks")
        return

    for chk in checks:
        cid   = chk.get("id", "CC-???")
        desc  = chk.get("description", "")
        ctype = chk.get("type", "")
        sev   = chk.get("severity", "WARN")
        emit  = r.fail if sev == "FAIL" else r.warn

        label = f"{cid}: {desc}"

        # --- file_exists ---
        if ctype == "file_exists":
            path = BASE_DIR / chk["path"]
            if path.exists():
                r.ok(f"{label}  [{path.name}]")
            else:
                emit(label, hint=f"Создайте: {chk['path']}")

        # --- file_exists_any ---
        elif ctype == "file_exists_any":
            found = [f for f in chk.get("files", []) if (BASE_DIR / f).exists()]
            if found:
                r.ok(f"{label}  [{found[0]}]")
            else:
                emit(label, hint=f"Нужен один из: {chk.get('files', [])}")

        # --- file_contains_pattern ---
        elif ctype == "file_contains_pattern":
            path = BASE_DIR / chk["file"]
            if not path.exists():
                emit(f"{label} — файл не найден: {chk['file']}")
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            patterns = chk.get("required_patterns", [])
            missing = [p for p in patterns if not re.search(p, content)]
            if missing:
                emit(f"{label} — паттерн не найден: {missing}", hint=f"в файле {chk['file']}")
            else:
                r.ok(f"{label}")

        # --- file_no_pattern (безопасность) ---
        elif ctype == "file_no_pattern":
            files = chk.get("files", [])
            forbidden = chk.get("forbidden_patterns", [])
            found_violations = []
            for fpath in files:
                p = BASE_DIR / fpath
                if not p.exists():
                    continue
                content = p.read_text(encoding="utf-8", errors="replace")
                for fp in forbidden:
                    if re.search(fp, content):
                        found_violations.append(f"{fpath}:{fp}")
            if found_violations:
                emit(f"{label} — найдены запрещённые паттерны!", hint=str(found_violations[:2]))
            else:
                r.ok(f"{label}")

        # --- project_no_pattern (поиск по всей кодовой базе) ---
        elif ctype == "project_no_pattern":
            dirs = chk.get("dirs", [])
            forbidden = chk.get("forbidden_patterns", [])
            found_violations = []
            for d in dirs:
                dp = BASE_DIR / d
                if not dp.is_dir():
                    continue
                for py_file in dp.rglob("*.py"):
                    try:
                        content = py_file.read_text(encoding="utf-8", errors="replace")
                        for fp in forbidden:
                            if re.search(fp, content):
                                found_violations.append(str(py_file.relative_to(BASE_DIR)))
                    except Exception:
                        pass
            if found_violations:
                emit(f"{label}", hint=f"Нарушения в: {found_violations[:3]}")
            else:
                r.ok(f"{label}")

        # --- directory_naming ---
        elif ctype == "directory_naming":
            d = BASE_DIR / chk["dir"]
            pat = chk.get("pattern", ".*")
            if not d.is_dir():
                r.warn(f"{label} — директория не найдена: {chk['dir']}")
                continue
            all_files = [f for f in d.iterdir() if f.is_file()]
            non_compliant = [f.name for f in all_files if not re.fullmatch(pat, f.name)]
            if non_compliant:
                emit(f"{label} — не соответствуют '{pat}': {non_compliant}", hint=f"в {chk['dir']}/")
            else:
                r.ok(f"{label}  [{len(all_files)} файлов, все соответствуют паттерну]")

        else:
            r.warn(f"{label} — неизвестный тип проверки: '{ctype}'", hint="Добавьте обработчик в validate_governance.py")


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ КОМАНДЫ CLI
# ============================================================
def show_manifest(manifest: dict):
    """Вывод структуры манифеста для ориентации."""
    proj = manifest.get("project", {})
    print(f"\n{BOLD}Манифест проекта:{RESET}")
    print(f"  Проект:  {proj.get('name')} v{proj.get('version')}")
    print(f"  Фаза:    {proj.get('current_phase')} [{proj.get('phase_status')}]")
    print(f"\n{BOLD}Секции в governance_manifest.json:{RESET}")
    sections = [
        ("project",               "Метаданные проекта"),
        ("thresholds",            "Числовые пороги (min_test_count, min_bytes...)"),
        ("governance_files",      "Обязательные файлы управления"),
        ("deploy_artifacts",      "Продакшен деплой-артефакты"),
        ("source_files",          "Ключевые файлы исходного кода"),
        ("docs",                  "Документация (explicit + auto-discover)"),
        ("architecture_decisions","ADR конфигурация (auto_discover из ARCHITECTURE_DECISIONS.md)"),
        ("agents",                "Агенты (auto_discover из SWARM_STATE.md + explicit_required)"),
        ("swarm_state_sync",      "Синхронизация счётчика тестов со SWARM_STATE.md"),
        ("custom_checks",         "Расширяемые кастомные проверки (CC-*)"),
    ]
    for key, desc in sections:
        present = key in manifest
        marker = f"{GREEN}[+]{RESET}" if present else f"{YELLOW}[ ]{RESET}"
        count = ""
        if present and isinstance(manifest[key], list):
            count = f" ({len(manifest[key])} записей)"
        print(f"  {marker} {BOLD}{key}{RESET}{count}  {DIM}{desc}{RESET}")
    print()


# ============================================================
# ТОЧКА ВХОДА
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="validate_governance.py — Динамический валидатор проекта. Конфиг: .agent_context/governance_manifest.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--no-pytest", action="store_true", help="Пропустить запуск pytest")
    parser.add_argument("--show-manifest", action="store_true", help="Показать структуру манифеста и выйти")
    parser.add_argument(
        "--section", choices=["governance", "agents", "deploy", "adr", "docs", "source", "pytest", "custom"],
        help="Запустить только одну секцию проверок"
    )
    args = parser.parse_args()

    r = Reporter()

    # Шапка
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{BOLD}{'=' * 65}{RESET}")
    print(f"{BOLD}  [SWARM] Governance Integrity Validator{RESET}")
    print(f"{BOLD}  Манифест: {MANIFEST_PATH.relative_to(BASE_DIR)}{RESET}")
    print(f"{BOLD}  Запущен:  {now}{RESET}")
    print(f"{BOLD}{'=' * 65}{RESET}")

    # Загрузка манифеста (обязательный шаг)
    manifest = load_manifest(r)
    if manifest is None:
        r.print_summary()
        return 1

    if args.show_manifest:
        show_manifest(manifest)
        return 0

    # Информация о проекте из манифеста
    proj = manifest.get("project", {})
    r.info(f"Проект: {proj.get('name', '?')} v{proj.get('version', '?')} | Фаза: {proj.get('current_phase', '?')} [{proj.get('phase_status', '?')}]")

    # Определяем, какие секции запускать
    only = args.section
    SECTIONS = [
        ("governance", "1", "Файлы управления",    lambda t, i: check_governance_files(r, manifest, t, i)),
        ("agents",     "2", "Агенты",              lambda t, i: check_agents(r, manifest, t, i)),
        ("deploy",     "3", "Деплой-артефакты",    lambda t, i: check_deploy_artifacts(r, manifest, t, i)),
        ("adr",        "4", "ADR",                 lambda t, i: check_architecture_decisions(r, manifest, t, i)),
        ("docs",       "5", "Документация",        lambda t, i: check_documentation(r, manifest, t, i)),
        ("source",     "6", "Исходный код",        lambda t, i: check_source_files(r, manifest, t, i)),
        ("pytest",     "7", "Тесты",               lambda t, i: check_pytest(r, manifest, t, i, skip=args.no_pytest)),
        ("custom",     "8", "Кастомные проверки",  lambda t, i: run_custom_checks(r, manifest, t, i)),
    ]

    active = [(k, n, d, fn) for k, n, d, fn in SECTIONS if only is None or k == only]
    total = len(active)
    for idx, (_, num, _, fn) in enumerate(active, 1):
        fn(total, idx)

    r.print_summary()
    return r.exit_code()


if __name__ == "__main__":
    sys.exit(main())
