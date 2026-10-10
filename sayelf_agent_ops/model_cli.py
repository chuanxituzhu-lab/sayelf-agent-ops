"""Model port setup — no AI host platform required.

  python -m sayelf_agent_ops.model_cli presets
  python -m sayelf_agent_ops.model_cli configure --preset deepseek --allow-remote
  python -m sayelf_agent_ops.model_cli configure --preset ollama --model qwen2.5:7b
  python -m sayelf_agent_ops.model_cli configure --endpoint https://… --model … --api-key-env MY_KEY --allow-remote
  python -m sayelf_agent_ops.model_cli show
  python -m sayelf_agent_ops.model_cli test

The key is never written to disk: set it as an environment variable whose
name is shown by ``presets`` (for example DEEPSEEK_API_KEY).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .providers.config import (PRESETS, ModelConfigError, config_path, explain, load_model, read_config,
                               write_config)
from .service import default_home


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sayelf-model", description="Sayelf Agent Ops 模型接口")
    parser.add_argument("--home", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("presets", help="列出预设")
    p = sub.add_parser("configure", help="写入模型配置（不含密钥）")
    p.add_argument("--preset", choices=sorted(PRESETS))
    p.add_argument("--endpoint")
    p.add_argument("--model")
    p.add_argument("--api-key-env", help="存放密钥的环境变量名")
    p.add_argument("--allow-remote", action="store_true", help="允许把工作内容发给非本机模型")
    p.add_argument("--no-generic-skills", action="store_true", help="只用专门技能，其余仍为占位")
    sub.add_parser("show", help="显示当前生效的模型")
    sub.add_parser("test", help="真实调用一次模型，确认能通")
    args = parser.parse_args(argv)
    home = args.home or default_home()

    if args.command == "presets":
        for key, p in PRESETS.items():
            model = p["model"] or "（需用 --model 指定）"
            env = p["api_key_env"] or "不需要"
            print(f"{key:9} {p['name']}\n          地址 {p['endpoint']}\n          模型 {model}    密钥环境变量 {env}")
        return 0

    if args.command == "configure":
        if not args.preset and not args.endpoint:
            print("请给出 --preset 或 --endpoint。", file=sys.stderr)
            return 2
        try:
            data = write_config(home, preset=args.preset, endpoint=args.endpoint, model=args.model,
                                api_key_env=args.api_key_env, allow_remote=args.allow_remote,
                                generic_skills=not args.no_generic_skills)
        except ModelConfigError as error:
            print(f"未保存：{explain(error)}", file=sys.stderr)
            return 2
        print(f"已保存：{config_path(home)}")
        if data["api_key_env"]:
            print(f"下一步：把密钥放进环境变量 {data['api_key_env']}（PowerShell：setx {data['api_key_env']} \"你的密钥\"，然后重开窗口）。")
        if not data["allow_remote"] and data["endpoint"].startswith("https://"):
            print("注意：没加 --allow-remote，远程模型不会被调用。")
        return 0

    try:
        setup = load_model(home)
    except ModelConfigError as error:
        print(f"模型配置有问题：{explain(error)}", file=sys.stderr)
        return 3
    desc = setup.describe()
    if args.command == "show":
        if not desc["configured"]:
            print("未配置模型。Agent Ops 仍可运行：内置技能可用，其余技能返回如实标记的占位产出。")
            return 0
        print(f"来源：{'环境变量' if desc['source'] == 'env' else config_path(home)}")
        print(f"模型：{desc['model']}\n地址：{desc['endpoint']}\n位置：{'远程' if desc['remote'] else '本机'}")
        print(f"远程调用：{'已允许' if desc['remote_allowed'] else '未允许'}\n通用技能执行：{'开' if desc['generic_skills'] else '关'}")
        cfg = read_config(home)
        if cfg and desc["source"] == "env":
            print("（环境变量优先，model.json 当前未生效）")
        return 0

    # test
    if not desc["configured"]:
        print("未配置模型。", file=sys.stderr)
        return 3
    if desc["remote"] and not desc["remote_allowed"]:
        print("远程调用未允许：重新 configure 时加 --allow-remote。", file=sys.stderr)
        return 4
    try:
        reply = setup.provider.complete_json('只返回 JSON：{"ok": true, "model": "你的模型名"}', {"ping": "sayelf"})
    except Exception as error:
        print(f"调用失败：{getattr(error, 'code', 'MODEL_CALL_FAILED')}", file=sys.stderr)
        return 1
    print(f"连通：{reply}")
    usage = getattr(setup.provider, "last_usage", None)
    if usage:
        print(f"用量：{usage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
