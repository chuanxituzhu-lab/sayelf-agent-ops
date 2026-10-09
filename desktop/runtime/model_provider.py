"""Compatibility re-export: the adapter now lives in the kernel so the desktop
app, the MCP server and any other entry share one implementation."""
from sayelf_agent_ops.providers.openai_compatible import (  # noqa: F401
    ADAPTER_ID,
    ADAPTER_VERSION,
    OpenAICompatibleProvider,
    ProviderError,
    is_local_endpoint,
)
