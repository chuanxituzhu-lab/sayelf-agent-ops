from ..models import SkillContract


def skill(
    skill_id: str,
    owner: str,
    purpose: str,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
) -> SkillContract:
    return SkillContract(
        id=skill_id,
        owner_scope=owner,
        purpose=purpose,
        accepted_inputs=inputs,
        produced_outputs=outputs,
        validation=("required-output-present",),
    )
