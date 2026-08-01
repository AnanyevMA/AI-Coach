"""
orchestrator.py — AI Adaptive Coach v7.0 | Deterministic Orchestration State Machine Engine
Version: 2.0.0

Architecture:
  - Reads agents_config.json for agent definitions and PoLP
  - Reads routing_rules.yaml for task-type → domain → agent routing
  - Uses BlackboardAdapter for task persistence (FileSystem by default)
  - Implements full State Machine: BACKLOG → ENRICHING → READY_FOR_DEV →
    IN_PROGRESS → CODE_REVIEW → COMPLIANCE_REVIEW → DONE | BLOCKED

Usage:
  python orchestrator/orchestrator.py                    # run engine (polls Blackboard)
  python orchestrator/orchestrator.py --create-task      # create task interactively
  python orchestrator/orchestrator.py --status           # show Blackboard status
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import time
import datetime
import logging
from pathlib import Path
from typing import Optional
try:
    from orchestrator.blackboard_adapter import FileSystemAdapter, BlackboardAdapter
except ImportError:
    from blackboard_adapter import FileSystemAdapter, BlackboardAdapter

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "agents_config.json"
ROUTING_PATH = Path(__file__).parent / "routing_rules.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("orchestrator")


# ---------------------------------------------------------------------------
# Arbitration Priority (mirrored from agents_config.json for fast access)
# ---------------------------------------------------------------------------
ARBITRATION_PRIORITY = [
    "security_policy_keeper",
    "legal_compliance_policy_keeper",
    "finance_budget_policy_keeper",
    "product_ux_policy_keeper",
]

POLICY_GATE_MAP = {
    "security_policy_keeper":        "security",
    "legal_compliance_policy_keeper": "legal",
    "finance_budget_policy_keeper":   "finance",
    "product_ux_policy_keeper":       "product",
}

CIRCUIT_BREAKER_MAX_WORKER_ATTEMPTS = 3
CIRCUIT_BREAKER_MAX_LEAD_RECONFIG   = 2


# ---------------------------------------------------------------------------
# State Machine Transitions
# ---------------------------------------------------------------------------
class StateMachine:
    TRANSITIONS = {
        "BACKLOG":            ["ENRICHING"],
        "ENRICHING":          ["READY_FOR_DEV", "BLOCKED"],
        "READY_FOR_DEV":      ["IN_PROGRESS"],
        "IN_PROGRESS":        ["CODE_REVIEW", "IN_PROGRESS", "BLOCKED"],
        "CODE_REVIEW":        ["COMPLIANCE_REVIEW", "IN_PROGRESS"],
        "COMPLIANCE_REVIEW":  ["DONE", "BLOCKED"],
        "BLOCKED":            ["ENRICHING", "DONE"],  # ENRICHING = human unblock
        "DONE":               [],
    }

    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        return to_status in cls.TRANSITIONS.get(from_status, [])


# ---------------------------------------------------------------------------
# Orchestrator Engine
# ---------------------------------------------------------------------------
class OrchestratorEngine:

    def __init__(self, adapter: BlackboardAdapter, config: dict):
        self.bb = adapter
        self.config = config
        self.poll_interval = 10  # seconds
        log.info("OrchestratorEngine v2.0 initialized")

    # ---- Main loop ----

    def run(self):
        log.info("Starting orchestration loop (Ctrl+C to stop)")
        while True:
            try:
                self._tick()
            except KeyboardInterrupt:
                log.info("Orchestrator stopped.")
                break
            except Exception as e:
                log.error(f"Tick error: {e}")
            time.sleep(self.poll_interval)

    def _tick(self):
        """Process all active tasks in Blackboard."""
        for status in ["BACKLOG", "ENRICHING", "READY_FOR_DEV", "IN_PROGRESS", "CODE_REVIEW", "COMPLIANCE_REVIEW", "BLOCKED"]:
            tasks = self.bb.list_by_status(status)
            for task in tasks:
                self._process_task(task)

    def _process_task(self, task: dict):
        task_id = task["task_id"]
        status  = task["status"]
        log.debug(f"Processing {task_id} [{status}]")

        if status == "BACKLOG":
            self._transition_to_enriching(task)
        elif status == "ENRICHING":
            self._check_policy_gates(task)
        elif status == "READY_FOR_DEV":
            self._assign_to_team_lead(task)
        elif status == "CODE_REVIEW":
            self._run_qa_review(task)
        elif status == "COMPLIANCE_REVIEW":
            self._run_compliance_review(task)
        elif status == "BLOCKED":
            self._check_human_decision(task)

    # ---- State transitions ----

    def _transition_to_enriching(self, task: dict):
        """Assign Policy Keepers based on routing rules."""
        task["status"] = "ENRICHING"
        task["policy_gates"] = {
            "security": {"status": "PENDING", "decision": None, "notes": ""},
            "legal":    {"status": "PENDING", "decision": None, "notes": ""},
            "finance":  {"status": "PENDING", "decision": None, "notes": ""},
            "product":  {"status": "PENDING", "decision": None, "notes": ""},
        }
        self._log_transition(task, "BACKLOG", "ENRICHING", "orchestrator_engine")
        self.bb.update_task(task["task_id"], task)
        log.info(f"  {task['task_id']}: BACKLOG → ENRICHING (policy keepers assigned)")

    def _check_policy_gates(self, task: dict):
        """Evaluate policy gates using Arbitration Hierarchy."""
        gates = task.get("policy_gates", {})
        all_done = all(g["status"] != "PENDING" for g in gates.values())
        if not all_done:
            return  # Wait for Policy Keepers to fill gates

        # Apply Arbitration Priority: P1 → P2 → P3 → P4
        for keeper in ARBITRATION_PRIORITY:
            gate_key = POLICY_GATE_MAP[keeper]
            gate = gates.get(gate_key, {})
            decision = gate.get("decision")

            if decision == "REJECTED" and keeper in ("security_policy_keeper", "legal_compliance_policy_keeper"):
                # P1/P2: Hard Block
                task["arbitration"]["conflict_detected"] = True
                task["arbitration"]["conflicting_policies"] = [keeper]
                task["arbitration"]["applied_priority"] = keeper
                self._trigger_escalation(task, keeper, gate.get("notes", ""))
                return

            if decision == "SCOPE_REDUCE" and keeper == "finance_budget_policy_keeper":
                # P3: Reduce scope, re-route to Team Lead
                log.warning(f"  {task['task_id']}: P3 SCOPE_REDUCE — routing to team lead for scope adjustment")
                task["status"] = "READY_FOR_DEV"
                task["arbitration"]["resolution"] = "scope_reduced_by_finance"
                self._log_transition(task, "ENRICHING", "READY_FOR_DEV", "finance_budget_policy_keeper")
                self.bb.update_task(task["task_id"], task)
                return

        # All gates passed (or P4 adapt request handled by lead)
        task["status"] = "READY_FOR_DEV"
        self._log_transition(task, "ENRICHING", "READY_FOR_DEV", "orchestrator_engine")
        self.bb.update_task(task["task_id"], task)
        log.info(f"  {task['task_id']}: ENRICHING → READY_FOR_DEV (all policy gates APPROVED)")

    def _assign_to_team_lead(self, task: dict):
        """Route task to correct Team Lead based on domain."""
        domain = task.get("layer_routing", {}).get("domain", "engineering")
        lead_map = {
            "engineering": "engineering_lead",
            "medical":     "medical_team_lead",
            "growth":      "growth_team_lead",
            "research":    "research_team_lead",
            "economics":   "economics_team_lead",
            "legal":       "legal_ops_team_lead",
        }
        lead = lead_map.get(domain, "engineering_lead")
        task["layer_routing"]["assigned_team_lead"] = lead
        task["status"] = "IN_PROGRESS"
        task["execution"]["attempt"] = 1
        self._log_transition(task, "READY_FOR_DEV", "IN_PROGRESS", lead)
        self.bb.update_task(task["task_id"], task)
        log.info(f"  {task['task_id']}: READY_FOR_DEV → IN_PROGRESS (assigned to {lead})")

    def _run_qa_review(self, task: dict):
        """Trigger QA review (qa_safety_auditor)."""
        # In real implementation: call qa_safety_auditor agent
        # Here we advance if test_results field is filled
        if task.get("execution", {}).get("test_results") == "PASS":
            task["status"] = "COMPLIANCE_REVIEW"
            self._log_transition(task, "CODE_REVIEW", "COMPLIANCE_REVIEW", "qa_safety_auditor")
            self.bb.update_task(task["task_id"], task)
            log.info(f"  {task['task_id']}: CODE_REVIEW → COMPLIANCE_REVIEW")
        elif task.get("execution", {}).get("test_results") == "FAIL":
            attempt = task["execution"].get("attempt", 1)
            if attempt < CIRCUIT_BREAKER_MAX_WORKER_ATTEMPTS:
                task["execution"]["attempt"] = attempt + 1
                task["status"] = "IN_PROGRESS"
                self._log_transition(task, "CODE_REVIEW", "IN_PROGRESS", "orchestrator_engine")
                self.bb.update_task(task["task_id"], task)
                log.info(f"  {task['task_id']}: CODE_REVIEW → IN_PROGRESS (retry {attempt+1}/{CIRCUIT_BREAKER_MAX_WORKER_ATTEMPTS})")
            else:
                self._trigger_escalation(task, "worker_exhausted", f"QA failed after {attempt} attempts")

    def _run_compliance_review(self, task: dict):
        """Final compliance check before DONE."""
        compliance = task.get("execution", {}).get("compliance_result")
        if compliance == "PASS":
            task["status"] = "DONE"
            self._log_transition(task, "COMPLIANCE_REVIEW", "DONE", "security_policy_keeper")
            self.bb.update_task(task["task_id"], task)
            self.bb.archive_task(task["task_id"])
            log.info(f"  {task['task_id']}: COMPLIANCE_REVIEW → DONE ✓")
        elif compliance == "FAIL":
            self._trigger_escalation(task, "compliance_failed", "Compliance review rejected final artifacts")

    def _check_human_decision(self, task: dict):
        """Resume task after human decision."""
        human = task.get("human_escalation", {})
        if human.get("human_decision") and human.get("awaiting_human_input"):
            decision = human["human_decision"]
            task["human_escalation"]["awaiting_human_input"] = False
            if decision == "CLOSE":
                task["status"] = "DONE"
                self.bb.archive_task(task["task_id"])
                log.info(f"  {task['task_id']}: BLOCKED → DONE (closed by human)")
            else:
                task["status"] = "ENRICHING"
                task["execution"]["attempt"] = 0
                self._log_transition(task, "BLOCKED", "ENRICHING", "human")
                self.bb.update_task(task["task_id"], task)
                log.info(f"  {task['task_id']}: BLOCKED → ENRICHING (human unblocked: {decision})")

    # ---- Circuit Breaker / Escalation ----

    def _trigger_escalation(self, task: dict, reason: str, detail: str):
        """Circuit Breaker → Human Escalation."""
        task["status"] = "BLOCKED"
        task["human_escalation"] = {
            "triggered": True,
            "interrupt_file": f"INTERRUPT_REQ_{task['task_id']}.json",
            "failure_reason": reason,
            "detail": detail,
            "proposed_options": [
                "Option A: Modify task requirements to satisfy policy",
                "Option B: Reduce task scope",
                "Option C: Close task (DONE without implementation)",
            ],
            "awaiting_human_input": True,
            "created_at": datetime.datetime.now().isoformat(),
            "sla_hours": 24,
            "human_decision": None,
        }
        self._log_transition(task, task["status"], "BLOCKED", "human_escalation_handler")
        self.bb.update_task(task["task_id"], task)
        self.bb.create_interrupt(task["task_id"], task["human_escalation"])
        log.warning(f"  {task['task_id']}: BLOCKED — Circuit Breaker: {reason}")

    # ---- Helpers ----

    def _log_transition(self, task: dict, from_s: str, to_s: str, actor: str):
        task.setdefault("status_history", []).append({
            "from": from_s,
            "to": to_s,
            "actor": actor,
            "timestamp": datetime.datetime.now().isoformat(),
        })

    # ---- CLI ----

    @classmethod
    def create_task(cls, bb: BlackboardAdapter, title: str, description: str,
                    domain: str = "engineering", task_type: str = "backend",
                    priority: str = "NORMAL") -> str:
        """Create a new task on the Blackboard."""
        today = datetime.date.today().strftime("%Y%m%d")
        existing = len(bb.list_by_status("ALL"))
        task_id = f"TASK-{today}-{existing+1:04d}"
        task = {
            "task_id": task_id,
            "title": title,
            "description": description,
            "initiator": "human",
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
            "status": "BACKLOG",
            "status_history": [{"status": "BACKLOG", "timestamp": datetime.datetime.now().isoformat(), "actor": "human"}],
            "layer_routing": {
                "domain": domain,
                "task_type": task_type,
                "policy_review_required": ["security_policy_keeper", "legal_compliance_policy_keeper", "finance_budget_policy_keeper", "product_ux_policy_keeper"],
                "assigned_team_lead": None,
                "assigned_worker": None,
            },
            "policy_gates": {},
            "arbitration": {"conflict_detected": False, "conflicting_policies": [], "resolution": None, "applied_priority": None},
            "execution": {"attempt": 0, "max_attempts": 3, "artifacts_produced": [], "test_results": None, "compliance_result": None, "error_log": []},
            "human_escalation": {"triggered": False, "interrupt_file": None, "proposed_options": [], "human_decision": None, "awaiting_human_input": False},
            "dependencies": [],
            "tags": [],
            "priority": priority,
        }
        bb.create_task(task)
        log.info(f"Task created: {task_id} — '{title}'")
        return task_id


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Adaptive Coach — Orchestrator Engine v2.0")
    parser.add_argument("--run",         action="store_true", help="Start orchestration loop")
    parser.add_argument("--status",      action="store_true", help="Show Blackboard status summary")
    parser.add_argument("--create-task", action="store_true", help="Create a new task on the Blackboard")
    args = parser.parse_args()

    # Load config
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    # Init Blackboard adapter
    bb_cfg = config["orchestration"]["blackboard"]
    bb = FileSystemAdapter(
        tasks_path=BASE_DIR / bb_cfg["tasks_path"],
        interrupts_path=BASE_DIR / bb_cfg["interrupts_path"],
        archive_path=BASE_DIR / bb_cfg.get("archive_path", "blackboard/archive"),
    )

    if args.status:
        index = bb.get_index()
        print("\n=== BLACKBOARD STATUS ===")
        by_status: dict = {}
        for task_id, meta in index.items():
            s = meta.get("status", "UNKNOWN")
            by_status.setdefault(s, []).append(task_id)
        for status, ids in sorted(by_status.items()):
            print(f"  {status:<20}: {len(ids):>3}  {', '.join(ids[:3])}{'...' if len(ids)>3 else ''}")
        print(f"\n  Total tasks: {len(index)}")

    elif args.create_task:
        title = input("Task title: ")
        desc  = input("Description: ")
        domain = input("Domain [engineering/medical/growth/research/economics/legal]: ") or "engineering"
        ttype  = input("Task type [backend/ai_model/telemetry/ui_ux/...]: ") or "backend"
        OrchestratorEngine.create_task(bb, title, desc, domain, ttype)

    else:
        engine = OrchestratorEngine(bb, config)
        engine.run()
