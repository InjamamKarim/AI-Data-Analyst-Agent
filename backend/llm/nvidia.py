"""OpenAI-compatible client pinned to NVIDIA's free API host."""

from __future__ import annotations

from backend.config import assert_free_endpoint, estimate_tokens, get_settings

MISSING_KEY_MESSAGE = (
    "NVIDIA_API_KEY is empty. Add your free key from https://build.nvidia.com/settings "
    "to the NVIDIA_API_KEY line in .env. The next question picks it up without a code change. "
    "No paid API is configured, and no model is loaded on this machine. "
    "Demo mode can still answer the 50 sample questions."
)


class MissingAPIKeyError(RuntimeError):
    """Raised when a live turn is requested before the NVIDIA key is set."""


def complete(system: str, user: str) -> tuple[str, int]:
    settings = get_settings()
    if not settings.nvidia_configured:
        raise MissingAPIKeyError(MISSING_KEY_MESSAGE)
    assert_free_endpoint(settings.nvidia_base_url, settings.nvidia_allow_hosts)
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    # api_key and base_url are passed explicitly so a stray OPENAI_API_KEY
    # in the shell cannot redirect this call to a paid provider.
    llm = ChatOpenAI(
        model=settings.nvidia_model,
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
        temperature=settings.nvidia_temperature,
        max_tokens=settings.nvidia_max_tokens,
        timeout=90,
    )
    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = response.content
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    usage = getattr(response, "usage_metadata", None) or {}
    tokens = usage.get("total_tokens") or (
        estimate_tokens(system) + estimate_tokens(user) + estimate_tokens(str(content))
    )
    return str(content), int(tokens)
