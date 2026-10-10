"""Model port — Agent Ops calls a model directly, no AI host platform needed.

Where the model comes from, first match wins:

1. Environment: ``SAYELF_MODEL_ENDPOINT`` / ``SAYELF_MODEL_NAME`` /
   ``SAYELF_MODEL_API_KEY`` / ``SAYELF_MODEL_ALLOW_REMOTE=1`` (Sprint 05, unchanged).
2. ``<home>/model.json`` written by ``python -m sayelf_agent_ops.model_cli configure``.
   The file never holds a key, only the *name* of the environment variable
   that does (``api_key_env``).
3. Nothing configured → Agent Ops still runs: built-in skills work, every
   other skill returns an honestly marked placeholder.

Any OpenAI-compatible chat endpoint works. Presets cover common Chinese
providers and local runtimes; model names change over time, so the console of
each provider is the authority — ``--model`` overrides the default.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .openai_compatible import OpenAICompatibleProvider, ProviderError, is_local_endpoint

PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {"name": "DeepSeek", "endpoint": "https://api.deepseek.com/v1",
                 "model": "deepseek-chat", "api_key_env": "DEEPSEEK_API_KEY"},
    "qwen": {"name": "通义千问（阿里云百炼）", "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1",
             "model": "qwen-plus", "api_key_env": "DASHSCOPE_API_KEY"},
    "doubao": {"name": "豆包（火山方舟）", "endpoint": "https://ark.cn-beijing.volces.com/api/v3",
               "model": "", "api_key_env": "ARK_API_KEY"},
    "kimi": {"name": "Kimi（月之暗面）", "endpoint": "https://api.moonshot.cn/v1",
             "model": "", "api_key_env": "MOONSHOT_API_KEY"},
    "zhipu": {"name": "智谱 GLM", "endpoint": "https://open.bigmodel.cn/api/paas/v4",
              "model": "glm-4-flash", "api_key_env": "ZHIPUAI_API_KEY"},
    "ollama": {"name": "Ollama（本机）", "endpoint": "http://127.0.0.1:11434/v1",
               "model": "", "api_key_env": ""},
    "lmstudio": {"name": "LM Studio（本机）", "endpoint": "http://127.0.0.1:1234/v1",
                 "model": "", "api_key_env": ""},
}
CONFIG_KEYS = {"preset", "endpoint", "model", "api_key_env", "allow_remote", "generic_skills"}


class ModelConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ModelSetup:
    """What an entry needs to run skills on a model. Never carries the key."""

    provider: Any | None
    remote: bool
    consent: bool
    generic_skills: bool
    source: str  # "env" | "file" | "none"

    def describe(self) -> dict[str, Any]:
        return {
            "configured": self.provider is not None,
            "source": self.source,
            "model": getattr(self.provider, "model", None),
            "endpoint": getattr(self.provider, "endpoint", None),
            "remote": self.remote,
            "remote_allowed": self.consent,
            "generic_skills": self.generic_skills,
        }


def explain(error: Exception) -> str:
    """A model-config error in plain Chinese, for terminals and logs."""
    code, _, detail = str(error).partition(":")
    return {
        "MISSING_API_KEY": f"缺少密钥：请设置环境变量 {detail}，然后重开窗口",
        "MODEL_NOT_CONFIGURED": "模型地址或模型名为空",
        "MODEL_CONFIG_INVALID": "model.json 格式不对，可重新运行 configure",
        "UNKNOWN_PRESET": f"没有这个预设：{detail}",
        "MODEL_ENDPOINT_INVALID": "模型地址须以 http:// 或 https:// 开头",
        "MODEL_NAME_REQUIRED": "这个预设没有默认模型名，请用 --model 指定",
        "API_KEY_ENV_INVALID": "环境变量名只能用字母、数字和下划线",
        "REMOTE_ENDPOINT_MUST_USE_HTTPS": "远程模型地址必须用 https",
    }.get(code, str(error))


def config_path(home: Path) -> Path:
    return home / "model.json"


def read_config(home: Path) -> dict[str, Any] | None:
    path = config_path(home)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) - CONFIG_KEYS:
        raise ModelConfigError("MODEL_CONFIG_INVALID")
    return data


def write_config(home: Path, *, preset: str | None, endpoint: str | None, model: str | None,
                 api_key_env: str | None, allow_remote: bool, generic_skills: bool = True) -> dict[str, Any]:
    base = dict(PRESETS.get(preset or "", {}))
    if preset and not base:
        raise ModelConfigError(f"UNKNOWN_PRESET:{preset}")
    data = {
        "preset": preset or "",
        "endpoint": (endpoint or base.get("endpoint", "")).rstrip("/"),
        "model": model or base.get("model", ""),
        "api_key_env": api_key_env if api_key_env is not None else base.get("api_key_env", ""),
        "allow_remote": bool(allow_remote),
        "generic_skills": bool(generic_skills),
    }
    if not data["endpoint"].startswith(("http://", "https://")):
        raise ModelConfigError("MODEL_ENDPOINT_INVALID")
    if not data["model"]:
        raise ModelConfigError("MODEL_NAME_REQUIRED")
    if data["api_key_env"] and not data["api_key_env"].replace("_", "").isalnum():
        raise ModelConfigError("API_KEY_ENV_INVALID")
    if data["endpoint"].startswith("http://") and not is_local_endpoint(data["endpoint"]):
        raise ModelConfigError("REMOTE_ENDPOINT_MUST_USE_HTTPS")
    path = config_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def load_model(home: Path, environ: dict[str, str] | None = None) -> ModelSetup:
    env = os.environ if environ is None else environ
    endpoint = env.get("SAYELF_MODEL_ENDPOINT", "").strip()
    if endpoint:
        provider = OpenAICompatibleProvider(endpoint, env.get("SAYELF_MODEL_NAME", "").strip(),
                                            env.get("SAYELF_MODEL_API_KEY", ""))
        return ModelSetup(provider, not is_local_endpoint(endpoint),
                          env.get("SAYELF_MODEL_ALLOW_REMOTE") == "1",
                          env.get("SAYELF_MODEL_GENERIC_SKILLS", "1") != "0", "env")
    data = read_config(home)
    if not data:
        return ModelSetup(None, False, False, False, "none")
    key = env.get(data["api_key_env"], "") if data.get("api_key_env") else ""
    key = key or env.get("SAYELF_MODEL_API_KEY", "")
    try:
        provider = OpenAICompatibleProvider(data["endpoint"], data["model"], key)
    except ProviderError as error:
        # Configured but the key is missing: say so instead of silently using placeholders.
        hint = data.get("api_key_env") or "SAYELF_MODEL_API_KEY"
        code = "MISSING_API_KEY" if error.code == "MODEL_NOT_CONFIGURED" and data.get("model") else error.code
        raise ModelConfigError(f"{code}:{hint}") from None
    remote = not is_local_endpoint(data["endpoint"])
    return ModelSetup(provider, remote, bool(data.get("allow_remote")),
                      bool(data.get("generic_skills", True)), "file")


def model_handlers(setup: ModelSetup, registry: Any) -> tuple[dict[str, Any], Any | None]:
    """Skill handlers and the fallback for skills without a dedicated handler."""
    if setup.provider is None:
        return {}, None
    from ..skills.generic_llm import make_generic_handler
    from ..skills.video_llm import make_model_handlers

    handlers = make_model_handlers(setup.provider, remote=setup.remote, consent=setup.consent)
    fallback = (make_generic_handler(setup.provider, registry, remote=setup.remote, consent=setup.consent)
                if setup.generic_skills else None)
    return handlers, fallback
