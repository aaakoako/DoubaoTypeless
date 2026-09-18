"""Insert attempt journal. Injection is not confirmation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Result = Literal["RUNNING", "NO_STEPS", "PARTIAL", "UNKNOWN", "CONFIRMED", "CANCELLED"]
FORBIDDEN_CONFIRM_EVIDENCE = frozenset({"none", "os_input_count"})


@dataclass
class Step:
    index: int
    kind: Literal["image", "text"]
    asset_id: str | None
    state: str = "pending"
    evidence: str = "none"


@dataclass
class Attempt:
    attempt_id: str
    intent_id: str
    bundle_id: str
    adapter_id: str
    result: Result = "RUNNING"
    steps: list[Step] = field(default_factory=list)
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "attempt_id": self.attempt_id,
            "intent_id": self.intent_id,
            "bundle_id": self.bundle_id,
            "adapter_id": self.adapter_id,
            "result": self.result,
            "steps": [
                {
                    "index": s.index,
                    "kind": s.kind,
                    "asset_id": s.asset_id,
                    "state": s.state,
                    "evidence": s.evidence,
                }
                for s in self.steps
            ],
        }
        if self.error_code:
            payload["error_code"] = self.error_code
        return payload

    def confirm_if_observed(self) -> None:
        if not self.steps:
            self.result = "NO_STEPS"
            return
        if any(s.state != "observed" for s in self.steps):
            if any(s.state in {"injected", "unknown"} for s in self.steps):
                self.result = "UNKNOWN" if any(s.state == "unknown" for s in self.steps) else "PARTIAL"
            return
        if any(s.evidence in FORBIDDEN_CONFIRM_EVIDENCE for s in self.steps):
            raise ValueError("injection is not receipt")
        if any(s.evidence not in {"target_attachment", "target_text", "user_confirmed"} for s in self.steps):
            raise ValueError("unproven confirmation")
        self.result = "CONFIRMED"
