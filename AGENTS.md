# sayelf-agent-ops（交付物路由与执行内核）

本目录的权威指令是同目录下的 SKILL.md。收到「Agent Ops / 一人公司 / 交付物路由 / 岗位路由 / 谁来干 / 人工裁决 / Human Gate / 独立审核」，或需要判断任务该由哪个岗位与技能完成时，先读取 SKILL.md 并按其执行。构建纪律仍以 D:\Codex\skills\sayelf-base\SKILL.md 为唯一底座。

开发本仓库时：`python -m unittest discover -s evals -v` 必须全绿；`evals/test_solo_invariants.py` 的四条 Solo 不变式任何一条失败都不得合入。
