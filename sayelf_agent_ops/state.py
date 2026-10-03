from __future__ import annotations

from enum import StrEnum

from .models import WorkItem


class WorkState(StrEnum):
    INBOX = "INBOX"
    SCOPED = "SCOPED"
    WORKING = "WORKING"
    READY = "READY"


class TransitionRejected(RuntimeError):
    pass


_ALLOWED = {
    WorkState.INBOX: {WorkState.SCOPED},
    WorkState.SCOPED: {WorkState.WORKING},
    WorkState.WORKING: {WorkState.READY},
    WorkState.READY: set(),
}


class StateEngine:
    def transition(self, workitem: WorkItem, target: WorkState) -> WorkItem:
        current = WorkState(workitem.state)

        if target not in _ALLOWED[current]:
            raise TransitionRejected(f"ILLEGAL_TRANSITION:{current}->{target}")

        if current == WorkState.INBOX and target == WorkState.SCOPED:
            if not (workitem.goal and workitem.deliverable and workitem.industry):
                raise TransitionRejected("SCOPE_INCOMPLETE")

        if current == WorkState.SCOPED and target == WorkState.WORKING:
            if not (workitem.selected_role and workitem.selected_skills and workitem.execution_plan):
                raise TransitionRejected("ROUTING_INCOMPLETE")

        if current == WorkState.WORKING and target == WorkState.READY:
            if not workitem.outputs:
                raise TransitionRejected("REQUIRED_OUTPUT_MISSING")

        workitem.state = target.value
        workitem.history.append({
            "event": "state-transition",
            "from": current.value,
            "to": target.value,
        })
        return workitem
