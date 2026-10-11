"""Local, reversible overlays that consolidate registered skills into AI-native roles."""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import RoleContract, SkillContract, WorkItem
from .packs import RouteRule
from .registry import Registry
from .router import Router

_REVIEW_MARKERS = ("qa", "review", "audit", "验收", "质检", "复核", "审核")
_PRODUCER_MARKERS = ("implementation", "writing", "generation", "制作", "写作", "开发", "生成")
_GENERIC_ALIASES = {"工作", "内容", "开发", "设计", "任务", "处理", "work", "task", "create"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", value.casefold(), flags=re.UNICODE)


def _industry_scoped_alias(needle: str, industry: str, base_registry: Registry):
    def matches(text: str) -> bool:
        if needle not in _norm(text):
            return False
        try:
            baseline = Router(base_registry).route(
                WorkItem(id="ROLE-SCOPE", input=text, goal=text, deliverable=text)
            )
        except ValueError as error:
            code, _, detail = str(error).partition(":")
            if code == "UNROUTABLE_DELIVERABLE":
                return True
            if code != "AMBIGUOUS_ROUTING_RULE":
                return False
            conflicting_ids = set(detail.split(","))
            conflicting_rules = [
                rule for rule in base_registry.route_rules if rule.id in conflicting_ids
            ]
            # Allow a user overlay to resolve a genuine within-industry tie,
            # but never use ambiguity as a way to cross an industry boundary.
            return bool(conflicting_rules) and all(
                rule.industry == industry for rule in conflicting_rules
            )
        return baseline.industry == industry
    return matches


@contextmanager
def _connection(path: Path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


class RoleUpdateStore:
    """Persists locally verified role bundles; never creates executable skills."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _connection(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS role_updates (
                    update_id TEXT PRIMARY KEY, industry TEXT NOT NULL,
                    suggested_name TEXT NOT NULL, responsibility TEXT NOT NULL,
                    role_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
                    evidence_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS role_update_skills (
                    update_id TEXT NOT NULL, source_role_id TEXT NOT NULL,
                    source_skill_id TEXT NOT NULL, custom_skill_id TEXT NOT NULL,
                    PRIMARY KEY(update_id, source_skill_id)
                );
                CREATE TABLE IF NOT EXISTS role_update_aliases (
                    update_id TEXT NOT NULL, custom_skill_id TEXT NOT NULL,
                    alias TEXT NOT NULL, normalized_alias TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS role_update_events (
                    event_id TEXT PRIMARY KEY, update_id TEXT NOT NULL,
                    event TEXT NOT NULL, detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

    def reconcile(
        self,
        registry: Registry,
        suggested_name: str,
        responsibility: str,
        source_skill_ids: list[str],
        aliases_by_skill: dict[str, list[str]],
        positive_examples_by_skill: dict[str, list[str]],
        negative_examples: list[str],
    ) -> dict[str, Any]:
        """Validate a compact role bundle against existing skills and route evidence."""
        if not isinstance(suggested_name, str) or not 2 <= len(suggested_name.strip()) <= 80:
            return {"ok": False, "error": "INVALID_ROLE_NAME"}
        if not isinstance(responsibility, str) or not 12 <= len(responsibility.strip()) <= 500:
            return {"ok": False, "error": "INVALID_RESPONSIBILITY"}
        if not isinstance(source_skill_ids, list) or not 2 <= len(source_skill_ids) <= 8:
            return {"ok": False, "error": "INVALID_SKILL_BUNDLE_SIZE"}
        if not all(isinstance(sid, str) for sid in source_skill_ids):
            return {"ok": False, "error": "INVALID_SOURCE_SKILL"}
        if len(set(source_skill_ids)) != len(source_skill_ids):
            return {"ok": False, "error": "DUPLICATE_SOURCE_SKILL"}
        if not isinstance(aliases_by_skill, dict) or not isinstance(positive_examples_by_skill, dict):
            return {"ok": False, "error": "SKILL_ROUTE_EVIDENCE_MISMATCH"}
        if not all(isinstance(sid, str) and sid in registry.skills for sid in source_skill_ids):
            return {"ok": False, "error": "ROLE_HAS_NO_EXECUTABLE_SKILL"}
        sources = [registry.skills[sid] for sid in source_skill_ids]
        source_roles = [registry.roles.get(skill.owner_scope) for skill in sources]
        if any(role is None or role.status != "stable" for role in source_roles):
            return {"ok": False, "error": "SOURCE_ROLE_NOT_STABLE"}
        if any(role.id.startswith("custom.") for role in source_roles if role):
            return {"ok": False, "error": "NESTED_ROLE_BUNDLE_NOT_ALLOWED"}
        industries = {role.industry for role in source_roles if role}
        if len(industries) != 1:
            return {"ok": False, "error": "CROSS_INDUSTRY_BUNDLE_NOT_ALLOWED"}
        industry = next(iter(industries))
        source_role_ids = {role.id for role in source_roles if role}
        if len(source_role_ids) < 2:
            return {"ok": False, "error": "NO_ROLE_REDUCTION"}
        normalized_name = _norm(suggested_name)
        if any(role.industry == industry and _norm(role.name) == normalized_name
               for role in registry.roles.values()):
            return {"ok": False, "error": "DUPLICATE_ROLE_NAME"}
        if not all(sid in registry.roles[skill.owner_scope].allowed_skills for sid, skill in zip(source_skill_ids, sources)):
            return {"ok": False, "error": "INVALID_SOURCE_SKILL"}

        roles_text = " ".join(
            f"{role.id} {role.name} {role.responsibility}"
            for role in source_roles if role
        ).casefold()
        review_bundle = any(marker in roles_text for marker in _REVIEW_MARKERS) or any(
            marker in sid.casefold() or marker in skill.purpose.casefold()
            for sid, skill in zip(source_skill_ids, sources) for marker in _REVIEW_MARKERS
        )
        producer_bundle = any(
            marker in sid.casefold() or marker in skill.purpose.casefold()
            for sid, skill in zip(source_skill_ids, sources) for marker in _PRODUCER_MARKERS
        )
        if review_bundle and producer_bundle:
            return {"ok": False, "error": "INDEPENDENT_REVIEW_MUST_REMAIN_SEPARATE"}

        outputs: list[str] = []
        for skill in sources:
            outputs.extend(skill.produced_outputs)
        if len(outputs) != len(set(outputs)):
            return {"ok": False, "error": "REDUNDANT_OUTPUT_CONTRACTS"}

        expected = set(source_skill_ids)
        if any(set(mapping) != expected for mapping in (aliases_by_skill, positive_examples_by_skill)):
            return {"ok": False, "error": "SKILL_ROUTE_EVIDENCE_MISMATCH"}
        if not isinstance(negative_examples, list) or len(negative_examples) < 2:
            return {"ok": False, "error": "NEGATIVE_EXAMPLES_REQUIRED"}

        normalized_aliases: set[str] = set()
        for skill_id in source_skill_ids:
            aliases = aliases_by_skill.get(skill_id)
            positives = positive_examples_by_skill.get(skill_id)
            if not isinstance(aliases, list) or not 1 <= len(aliases) <= 8:
                return {"ok": False, "error": "INVALID_ALIASES"}
            if not isinstance(positives, list) or len(positives) < 2:
                return {"ok": False, "error": "POSITIVE_EXAMPLES_REQUIRED"}
            for alias in aliases:
                if not isinstance(alias, str) or not 2 <= len(alias.strip()) <= 80:
                    return {"ok": False, "error": "INVALID_ALIAS"}
                normalized = _norm(alias)
                if len(normalized) < 4 or normalized in {_norm(x) for x in _GENERIC_ALIASES}:
                    return {"ok": False, "error": "GENERIC_ALIAS"}
                if normalized in normalized_aliases:
                    return {"ok": False, "error": "DUPLICATE_ALIAS"}
                normalized_aliases.add(normalized)
            for sample in positives:
                if not isinstance(sample, str) or not 8 <= len(sample.strip()) <= 1000:
                    return {"ok": False, "error": "INVALID_POSITIVE_EXAMPLE"}
                if not any(_norm(alias) in _norm(sample) for alias in aliases):
                    return {"ok": False, "error": "POSITIVE_EXAMPLE_MISSING_ALIAS"}
            for sample in negative_examples:
                if not isinstance(sample, str) or not 8 <= len(sample.strip()) <= 1000:
                    return {"ok": False, "error": "INVALID_NEGATIVE_EXAMPLE"}

        with _connection(self.path) as db:
            taken = {row[0] for row in db.execute(
                "SELECT normalized_alias FROM role_update_aliases"
            )}
        if normalized_aliases & taken or any(
            left in right or right in left
            for left in normalized_aliases for right in taken
        ):
            return {"ok": False, "error": "ALIAS_CONFLICT"}
        ordered_aliases = sorted(normalized_aliases)
        if any(left in right or right in left
               for index, left in enumerate(ordered_aliases)
               for right in ordered_aliases[index + 1:]):
            return {"ok": False, "error": "OVERLAPPING_SKILL_ALIASES"}

        update_id = uuid.uuid4().hex
        role_id = f"custom.{industry}.{update_id[:10]}"
        custom_skill_ids = [f"{role_id}.{i + 1}" for i in range(len(sources))]
        clones = [SkillContract(
            id=custom_id, owner_scope=role_id, purpose=source.purpose,
            accepted_inputs=source.accepted_inputs, produced_outputs=source.produced_outputs,
            required_capabilities=source.required_capabilities, validation=source.validation,
            status=source.status,
        ) for custom_id, source in zip(custom_skill_ids, sources)]
        role = RoleContract(
            id=role_id, industry=industry, name=suggested_name.strip(),
            responsibility=responsibility.strip(), owned_outputs=tuple(outputs),
            allowed_skills=tuple(custom_skill_ids),
            forbidden_scope=tuple(dict.fromkeys(
                scope for source_role in source_roles if source_role for scope in source_role.forbidden_scope
            )), status="stable",
        )
        base_registry = Registry(
            roles=dict(registry.roles), skills=dict(registry.skills),
            route_rules=[rule for rule in registry.route_rules if not rule.id.startswith("user-role.")],
            packs=dict(registry.packs), active_role_ids=set(registry.active_role_ids),
        )
        rules: list[RouteRule] = []
        for index, (custom_id, aliases) in enumerate(zip(custom_skill_ids, (aliases_by_skill[s] for s in source_skill_ids))):
            for alias_index, alias in enumerate(aliases):
                needle = _norm(alias)
                rules.append(RouteRule(
                    id=f"user-role.{update_id}.{index}.{alias_index}",
                    predicate=_industry_scoped_alias(needle, industry, base_registry), priority=250,
                    deliverable_type=outputs_by_skill(sources[index]), industry=industry,
                    level="custom", role=role_id, skills=(custom_id,),
                    reason=f"用户本机核验的 AI 岗位组合，匹配能力：{sources[index].purpose}。",
                ))
        probe_registry = Registry(
            roles=dict(registry.roles), skills=dict(registry.skills),
            route_rules=list(registry.route_rules), packs=dict(registry.packs),
            active_role_ids=set(registry.active_role_ids),
        )
        try:
            probe_registry.roles[role_id] = role
            probe_registry.skills.update({skill.id: skill for skill in clones})
            probe_registry.register_rules(tuple(rules))
            router = Router(probe_registry)
            for skill_id, examples in positive_examples_by_skill.items():
                custom_id = custom_skill_ids[source_skill_ids.index(skill_id)]
                for sample in examples:
                    decision = router.route(WorkItem(id="ROLE-CHECK", input=sample, goal=sample, deliverable=sample))
                    if decision.selected_role != role_id or custom_id not in decision.selected_skills:
                        return {"ok": False, "error": "POSITIVE_ROUTE_MISMATCH", "sample": sample}
            for sample in negative_examples:
                try:
                    decision = router.route(WorkItem(id="ROLE-CHECK", input=sample, goal=sample, deliverable=sample))
                except ValueError:
                    continue
                if decision.selected_role == role_id or any(step[0] == role_id for step in decision.workflow_steps):
                    return {"ok": False, "error": "NEGATIVE_ROUTE_MATCH", "sample": sample}
        except (KeyError, ValueError) as error:
            return {"ok": False, "error": str(error).split(":")[0]}

        evidence = {
            "source_roles": sorted(source_role_ids), "source_skills": source_skill_ids,
            "merged_skill_count": len(source_skill_ids),
            "role_count_reduction_for_bundle": max(0, len(source_role_ids) - 1),
            "positive_examples": positive_examples_by_skill,
            "negative_examples": negative_examples,
            "reviewer_separation_checked": True,
            "route_scope": "per_skill_alias",
        }
        try:
            registry.roles[role_id] = role
            registry.skills.update({skill.id: skill for skill in clones})
            registry.register_rules(tuple(rules))
        except (KeyError, ValueError) as error:
            registry.roles.pop(role_id, None)
            for skill in clones:
                registry.skills.pop(skill.id, None)
            return {"ok": False, "error": str(error).split(":")[0]}
        try:
            with _connection(self.path) as db:
                db.execute("INSERT INTO role_updates VALUES (?, ?, ?, ?, ?, 'applied', ?, ?)", (
                    update_id, industry, role.name, role.responsibility, role_id,
                    json.dumps(evidence, ensure_ascii=False), _now(),
                ))
                db.executemany("INSERT INTO role_update_skills VALUES (?, ?, ?, ?)", [
                    (update_id, source.owner_scope, source.id, clone.id)
                    for source, clone in zip(sources, clones)
                ])
                db.executemany("INSERT INTO role_update_aliases VALUES (?, ?, ?, ?)", [
                    (update_id, custom_id, alias, _norm(alias))
                    for custom_id, skill_id in zip(custom_skill_ids, source_skill_ids)
                    for alias in aliases_by_skill[skill_id]
                ])
                self._event(db, update_id, "applied", evidence)
        except sqlite3.Error:
            registry.route_rules[:] = [
                rule for rule in registry.route_rules if not rule.id.startswith(f"user-role.{update_id}.")
            ]
            registry.roles.pop(role_id, None)
            for skill in clones:
                registry.skills.pop(skill.id, None)
            return {"ok": False, "error": "ROLE_UPDATE_PERSISTENCE_FAILED"}
        return {
            "ok": True, "status": "applied", "update_id": update_id,
            "role_id": role_id, "suggested_name": role.name, "industry": industry,
            "source_roles": sorted(source_role_ids), "source_skills": source_skill_ids,
            "merged_skill_count": len(source_skill_ids),
            "role_count_reduction_for_bundle": evidence["role_count_reduction_for_bundle"],
            "reviewer_separation_checked": True,
            "scope": "local_only; registered skills reused; no new tools or permissions",
        }

    def load_into(self, registry: Registry) -> None:
        with _connection(self.path) as db:
            updates = db.execute("SELECT * FROM role_updates WHERE status='applied'").fetchall()
            base_registry = Registry(
                roles=dict(registry.roles), skills=dict(registry.skills),
                route_rules=[rule for rule in registry.route_rules if not rule.id.startswith("user-role.")],
                packs=dict(registry.packs), active_role_ids=set(registry.active_role_ids),
            )
            for row in updates:
                update_id, industry, name, responsibility, role_id, _, _, _ = row
                source_rows = db.execute(
                    "SELECT source_role_id, source_skill_id, custom_skill_id FROM role_update_skills WHERE update_id=?",
                    (update_id,),
                ).fetchall()
                if not source_rows or any(
                    source_role not in registry.roles or source_skill not in registry.skills
                    or registry.roles[source_role].status != "stable"
                    for source_role, source_skill, _ in source_rows
                ):
                    continue
                sources = [registry.skills[source_skill] for _, source_skill, _ in source_rows]
                clones = [SkillContract(
                    id=custom_id, owner_scope=role_id, purpose=source.purpose,
                    accepted_inputs=source.accepted_inputs, produced_outputs=source.produced_outputs,
                    required_capabilities=source.required_capabilities, validation=source.validation,
                    status=source.status,
                ) for (_, _, custom_id), source in zip(source_rows, sources)]
                source_roles = [registry.roles[source_role] for source_role, _, _ in source_rows]
                role = RoleContract(
                    id=role_id, industry=industry, name=name, responsibility=responsibility,
                    owned_outputs=tuple(output for source in sources for output in source.produced_outputs),
                    allowed_skills=tuple(skill.id for skill in clones),
                    forbidden_scope=tuple(dict.fromkeys(scope for source_role in source_roles for scope in source_role.forbidden_scope)),
                )
                aliases = db.execute(
                    "SELECT custom_skill_id, alias FROM role_update_aliases WHERE update_id=?",
                    (update_id,),
                ).fetchall()
                rules = []
                for index, (custom_id, alias) in enumerate(aliases):
                    clone = next((skill for skill in clones if skill.id == custom_id), None)
                    if clone is None:
                        continue
                    needle = _norm(alias)
                    rules.append(RouteRule(
                        id=f"user-role.{update_id}.loaded.{index}",
                        predicate=_industry_scoped_alias(needle, industry, base_registry), priority=250,
                        deliverable_type=outputs_by_skill(clone), industry=industry,
                        level="custom", role=role_id, skills=(custom_id,),
                        reason=f"用户本机核验的 AI 岗位组合，匹配能力：{clone.purpose}。",
                    ))
                registry.roles[role_id] = role
                registry.skills.update({skill.id: skill for skill in clones})
                registry.register_rules(tuple(rules))

    def list_updates(self) -> dict[str, Any]:
        with _connection(self.path) as db:
            db.row_factory = sqlite3.Row
            updates = [dict(row) for row in db.execute("SELECT * FROM role_updates ORDER BY created_at DESC")]
            for update in updates:
                update["evidence"] = json.loads(update.pop("evidence_json"))
                update["skills"] = [dict(row) for row in db.execute(
                    "SELECT source_role_id, source_skill_id, custom_skill_id FROM role_update_skills WHERE update_id=?",
                    (update["update_id"],),
                )]
                update["events"] = [dict(row) for row in db.execute(
                    "SELECT event, detail_json, created_at FROM role_update_events WHERE update_id=? ORDER BY created_at",
                    (update["update_id"],),
                )]
                for event in update["events"]:
                    event["detail"] = json.loads(event.pop("detail_json"))
        return {"ok": True, "updates": updates}

    def revoke(self, registry: Registry, update_id: str) -> dict[str, Any]:
        with _connection(self.path) as db:
            row = db.execute("SELECT role_id, status FROM role_updates WHERE update_id=?", (update_id,)).fetchone()
            if not row:
                return {"ok": False, "error": "UNKNOWN_ROLE_UPDATE"}
            role_id, status = row
            if status == "revoked":
                return {"ok": True, "status": "revoked", "role_id": role_id}
            custom_ids = [r[0] for r in db.execute(
                "SELECT custom_skill_id FROM role_update_skills WHERE update_id=?", (update_id,)
            )]
            db.execute("UPDATE role_updates SET status='revoked' WHERE update_id=?", (update_id,))
            self._event(db, update_id, "revoked", {"role_id": role_id})
        registry.route_rules[:] = [
            rule for rule in registry.route_rules if not rule.id.startswith(f"user-role.{update_id}.")
        ]
        registry.roles.pop(role_id, None)
        for custom_id in custom_ids:
            registry.skills.pop(custom_id, None)
        return {"ok": True, "status": "revoked", "role_id": role_id}

    @staticmethod
    def _event(db: sqlite3.Connection, update_id: str, event: str, detail: dict[str, Any]) -> None:
        db.execute("INSERT INTO role_update_events VALUES (?, ?, ?, ?, ?)", (
            uuid.uuid4().hex, update_id, event, json.dumps(detail, ensure_ascii=False), _now(),
        ))


def outputs_by_skill(skill: SkillContract) -> str:
    return skill.produced_outputs[0] if skill.produced_outputs else skill.id.rsplit(".", 1)[-1]
