"""
test_mas_orchestrator.py — Pytest Suite for 3-Layer MAS Orchestrator Engine & Blackboard Adapter
AI Adaptive Coach v7.0
"""

import json
import pytest
from pathlib import Path
from orchestrator.blackboard_adapter import FileSystemAdapter
from orchestrator.orchestrator import OrchestratorEngine

BASE_DIR = Path(__file__).parent.parent


@pytest.fixture
def temp_blackboard_dirs(tmp_path):
    tasks_d = tmp_path / "tasks"
    interrupts_d = tmp_path / "interrupts"
    archive_d = tmp_path / "archive"
    adapter = FileSystemAdapter(tasks_d, interrupts_d, archive_d)
    return adapter, tmp_path


def test_blackboard_adapter_crud(temp_blackboard_dirs):
    adapter, _ = temp_blackboard_dirs
    
    # 1. Create Task
    task_id = OrchestratorEngine.create_task(
        adapter,
        title="Test Backend Refactor",
        description="Refactor API models for 152-FZ",
        domain="engineering",
        task_type="backend",
        priority="HIGH"
    )
    assert task_id.startswith("TASK-")
    
    # 2. Get Task
    task = adapter.get_task(task_id)
    assert task is not None
    assert task["status"] == "BACKLOG"
    assert task["title"] == "Test Backend Refactor"
    assert task["priority"] == "HIGH"

    # 3. List by Status
    backlog_tasks = adapter.list_by_status("BACKLOG")
    assert len(backlog_tasks) == 1
    assert backlog_tasks[0]["task_id"] == task_id

    # 4. Update Task
    task["status"] = "ENRICHING"
    adapter.update_task(task_id, task)
    updated = adapter.get_task(task_id)
    assert updated["status"] == "ENRICHING"

    # 5. Archive Task
    adapter.archive_task(task_id)
    assert adapter.get_task(task_id) is None  # Moved from active tasks


def test_orchestrator_state_machine_flow(temp_blackboard_dirs):
    adapter, _ = temp_blackboard_dirs
    config = json.loads((BASE_DIR / "agents_config.json").read_text(encoding="utf-8"))
    engine = OrchestratorEngine(adapter, config)

    # Create task
    task_id = OrchestratorEngine.create_task(
        adapter,
        title="AI Prompt Refactor",
        description="Refactor Gemini Flash prompts for safety",
        domain="engineering",
        task_type="ai_model"
    )

    # Tick 1: BACKLOG → ENRICHING
    engine._tick()
    t1 = adapter.get_task(task_id)
    assert t1["status"] == "ENRICHING"
    assert "security" in t1["policy_gates"]

    # Fill Policy Gates (Simulate P1-P4 approval)
    for gate in t1["policy_gates"].values():
        gate["status"] = "APPROVED"
        gate["decision"] = "APPROVED"
    adapter.update_task(task_id, t1)

    # Tick 2: ENRICHING → READY_FOR_DEV → IN_PROGRESS (single tick progression)
    engine._tick()
    t2 = adapter.get_task(task_id)
    assert t2["status"] == "IN_PROGRESS"
    assert t2["layer_routing"]["assigned_team_lead"] == "engineering_lead"

    # Simulate QA PASS in CODE_REVIEW
    t2["status"] = "CODE_REVIEW"
    t2["execution"]["test_results"] = "PASS"
    adapter.update_task(task_id, t2)

    # Tick 4: CODE_REVIEW → COMPLIANCE_REVIEW
    engine._tick()
    t4 = adapter.get_task(task_id)
    assert t4["status"] == "COMPLIANCE_REVIEW"

    # Simulate Compliance PASS
    t4["execution"]["compliance_result"] = "PASS"
    adapter.update_task(task_id, t4)

    # Tick 5: COMPLIANCE_REVIEW → DONE (Archived)
    engine._tick()
    assert adapter.get_task(task_id) is None


def test_circuit_breaker_escalation(temp_blackboard_dirs):
    adapter, tmp_path = temp_blackboard_dirs
    config = json.loads((BASE_DIR / "agents_config.json").read_text(encoding="utf-8"))
    engine = OrchestratorEngine(adapter, config)

    # Create task
    task_id = OrchestratorEngine.create_task(
        adapter,
        title="Unsafe Secret Exposure Task",
        description="Attempt to hardcode secret key",
        domain="engineering",
        task_type="backend"
    )

    # Advance to ENRICHING
    engine._tick()
    t = adapter.get_task(task_id)

    # Fill Security Gate as REJECTED (P1 Hard Block)
    t["policy_gates"]["security"] = {
        "status": "REJECTED",
        "decision": "REJECTED",
        "notes": "Hardcoded secret detected in PR"
    }
    t["policy_gates"]["legal"]["status"] = "APPROVED"
    t["policy_gates"]["finance"]["status"] = "APPROVED"
    t["policy_gates"]["product"]["status"] = "APPROVED"
    adapter.update_task(task_id, t)

    # Tick: ENRICHING → BLOCKED
    engine._tick()
    blocked_t = adapter.get_task(task_id)
    assert blocked_t["status"] == "BLOCKED"
    assert blocked_t["human_escalation"]["triggered"] is True
    
    # Check interrupt file created
    interrupt_file = tmp_path / "interrupts" / f"INTERRUPT_REQ_{task_id}.json"
    assert interrupt_file.exists()
