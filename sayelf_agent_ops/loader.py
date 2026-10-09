"""Sprint 02 — Lazy Skill Loader.

Rule 2 — Load only what the plan needs, inside a context budget.
Also enforces runtime capability discovery and license policy, because a
skill that cannot run here, or may not be used commercially, must never be
loaded in the first place.

Sprint 01 rules preserved:
- Registration is not activation (Registry stays idle).
- Registered skills are not automatically loaded.
"""
from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from typing import Callable

from .models import ExecutionPlan
from .registry import Registry


@dataclass(frozen=True)
class SkillManifest:
    skill_id: str
    source: str = "native"          # "native" or "distilled:<owner>/<repo>"
    license: str = "proprietary"    # SPDX id or "proprietary"
    commercial_use: bool = True


# Licenses that forbid commercial use. Such skills may be studied and
# distilled, never shipped in a commercial deliverable chain.
NON_COMMERCIAL_LICENSES = frozenset({
    "PolyForm-Noncommercial-1.0.0",
    "CC-BY-NC-4.0",
    "CC-BY-NC-SA-4.0",
    "personal-noncommercial",
})


@dataclass(frozen=True)
class LoadResult:
    plan_id: str
    loaded: tuple[str, ...]
    blocked: dict[str, str]

    @property
    def ok(self) -> bool:
        return not self.blocked


def discover_capabilities(
    probes: dict[str, Callable[[], bool]] | None = None,
) -> frozenset[str]:
    """Probe the environment instead of assuming it. Extra probes can be
    injected (e.g. a connector check) without touching this function."""
    default: dict[str, Callable[[], bool]] = {
        "python": lambda: sys.version_info >= (3, 11),
        "node": lambda: shutil.which("node") is not None,
        "ffmpeg": lambda: shutil.which("ffmpeg") is not None,
        "git": lambda: shutil.which("git") is not None,
    }
    if probes:
        default.update(probes)
    found = set()
    for name, probe in default.items():
        try:
            if probe():
                found.add(name)
        except Exception:
            pass
    return frozenset(found)


class SkillLoader:
    def __init__(
        self,
        registry: Registry,
        capabilities: frozenset[str] | set[str],
        manifests: dict[str, SkillManifest] | None = None,
        core: tuple[str, ...] = (),
        max_loaded: int = 4,
        commercial: bool = True,
        pack_manifests: dict[str, SkillManifest] | None = None,
    ):
        self.registry = registry
        self.capabilities = frozenset(capabilities)
        self.manifests = manifests or {}
        # One manifest per industry pack (e.g. a pack distilled from an
        # external repo): its source/license applies to every skill in it
        # unless that skill has its own manifest.
        self.pack_manifests = pack_manifests or {}
        self.core = core
        self.max_loaded = max_loaded
        self.commercial = commercial
        self._loaded: dict[str, set[str]] = {}   # skill_id -> plan ids holding it
        for skill_id in core:
            reason = self._check(skill_id)
            if reason:
                raise ValueError(f"CORE_SKILL_BLOCKED:{skill_id}:{reason}")
            self._loaded[skill_id] = {"__core__"}

    @property
    def loaded_skills(self) -> int:
        return len(self._loaded)

    def is_loaded(self, skill_id: str) -> bool:
        return skill_id in self._loaded

    def _industry_of(self, skill_id: str) -> str | None:
        skill = self.registry.skills.get(skill_id)
        role = self.registry.roles.get(skill.owner_scope) if skill else None
        return role.industry if role else None

    def manifest(self, skill_id: str) -> SkillManifest:
        if skill_id in self.manifests:
            return self.manifests[skill_id]
        pack = self.pack_manifests.get(self._industry_of(skill_id) or "")
        if pack is not None:
            return SkillManifest(skill_id=skill_id, source=pack.source,
                                 license=pack.license, commercial_use=pack.commercial_use)
        return SkillManifest(skill_id=skill_id)

    @property
    def loaded_packs(self) -> tuple[str, ...]:
        """Industries that currently have at least one skill in context."""
        found = []
        for skill_id in self._loaded:
            industry = self._industry_of(skill_id)
            if industry and industry not in found:
                found.append(industry)
        return tuple(found)

    def _check(self, skill_id: str) -> str | None:
        skill = self.registry.skills.get(skill_id)
        if skill is None:
            return "UNREGISTERED"
        m = self.manifest(skill_id)
        if self.commercial and (
            not m.commercial_use or m.license in NON_COMMERCIAL_LICENSES
        ):
            return f"LICENSE_NONCOMMERCIAL:{m.license}"
        missing = [c for c in skill.required_capabilities if c not in self.capabilities]
        if missing:
            return f"MISSING_CAPABILITY:{','.join(missing)}"
        return None

    def load_for_plan(self, plan: ExecutionPlan) -> LoadResult:
        wanted = []
        for step in plan.steps:
            if step.skill not in wanted:
                wanted.append(step.skill)

        blocked: dict[str, str] = {}
        for skill_id in wanted:
            reason = self._check(skill_id)
            if reason:
                blocked[skill_id] = reason

        new = [s for s in wanted if s not in self._loaded and s not in blocked]
        if not blocked and len(self._loaded) + len(new) > self.max_loaded:
            for s in new:
                blocked[s] = f"CONTEXT_BUDGET:{self.max_loaded}"

        # All-or-nothing: a half-loaded plan is worse than a clear block.
        if blocked:
            return LoadResult(plan_id=plan.id, loaded=(), blocked=blocked)

        for skill_id in wanted:
            self._loaded.setdefault(skill_id, set()).add(plan.id)
        return LoadResult(plan_id=plan.id, loaded=tuple(wanted), blocked={})

    def release(self, plan: ExecutionPlan) -> tuple[str, ...]:
        released = []
        for skill_id, holders in list(self._loaded.items()):
            if plan.id in holders:
                holders.discard(plan.id)
                if not holders:
                    del self._loaded[skill_id]
                    released.append(skill_id)
        return tuple(released)
