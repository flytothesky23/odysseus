"""Bounded deterministic design audit and allowlisted repair loop."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from src.report_design import DesignSpec


@dataclass(frozen=True)
class DesignFinding:
    severity: str
    evidence: str
    target: str
    allowed_fix: str
    expected_result: str


@dataclass(frozen=True)
class DesignAuditRound:
    round_number: int
    findings: tuple[DesignFinding, ...]
    patches: tuple[str, ...]
    passed: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _audit(spec: DesignSpec, renderer_id: str) -> tuple[DesignFinding, ...]:
    findings: list[DesignFinding] = []
    if spec.tokens.body_size_px < 16:
        findings.append(DesignFinding(
            severity="high",
            evidence=f"body_size_px={spec.tokens.body_size_px}",
            target="tokens.body_size_px",
            allowed_fix="raise-to-16",
            expected_result="readable base copy on desktop and mobile",
        ))
    if spec.tokens.line_height < 1.55:
        findings.append(DesignFinding(
            severity="medium",
            evidence=f"line_height={spec.tokens.line_height}",
            target="tokens.line_height",
            allowed_fix="raise-to-1.55",
            expected_result="long-form Korean paragraph rhythm remains readable",
        ))
    if renderer_id == "scroll_story" and spec.motion_preset not in {
        "subtle-reveal",
        "scene-observer",
    }:
        findings.append(DesignFinding(
            severity="medium",
            evidence=f"motion_preset={spec.motion_preset}",
            target="motion_preset",
            allowed_fix="use-scene-observer",
            expected_result="bounded progressive enhancement without scroll hijacking",
        ))
    if not spec.offline or not spec.print_fallback or not spec.reduced_motion:
        findings.append(DesignFinding(
            severity="critical",
            evidence="offline/print/reduced-motion invariant disabled",
            target="renderer invariants",
            allowed_fix="restore-required-invariants",
            expected_result="standalone accessible artifact",
        ))
    return tuple(findings)


def run_design_critique_loop(
    spec: DesignSpec,
    *,
    renderer_id: str,
    max_rounds: int = 2,
) -> tuple[DesignSpec, tuple[DesignAuditRound, ...]]:
    """Audit and patch only allowlisted presentation fields within a hard cap."""
    current = spec
    trace: list[DesignAuditRound] = []
    for round_number in range(1, max(1, min(int(max_rounds), 3)) + 1):
        findings = _audit(current, renderer_id)
        if not findings:
            trace.append(DesignAuditRound(round_number, (), (), True))
            break
        patches: list[str] = []
        tokens = current.tokens
        if any(f.allowed_fix == "raise-to-16" for f in findings):
            tokens = replace(tokens, body_size_px=16)
            patches.append("tokens.body_size_px=16")
        if any(f.allowed_fix == "raise-to-1.55" for f in findings):
            tokens = replace(tokens, line_height=1.55)
            patches.append("tokens.line_height=1.55")
        motion = current.motion_preset
        if any(f.allowed_fix == "use-scene-observer" for f in findings):
            motion = "scene-observer"
            patches.append("motion_preset=scene-observer")
        invariants = any(
            f.allowed_fix == "restore-required-invariants"
            for f in findings
        )
        current = replace(
            current,
            tokens=tokens,
            motion_preset=motion,
            offline=True if invariants else current.offline,
            print_fallback=True if invariants else current.print_fallback,
            reduced_motion=True if invariants else current.reduced_motion,
        )
        trace.append(DesignAuditRound(round_number, findings, tuple(patches), False))
    if trace and not trace[-1].passed:
        final_findings = _audit(current, renderer_id)
        trace.append(DesignAuditRound(len(trace) + 1, final_findings, (), not final_findings))
    return current, tuple(trace)
