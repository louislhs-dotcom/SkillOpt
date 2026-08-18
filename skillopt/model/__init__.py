"""ReflACT model API with runtime backend selection for the target path."""

from __future__ import annotations

from typing import Any

from skillopt.model import azure_openai as _openai
from skillopt.model import claude_backend as _claude
from skillopt.model import codex_backend as _codex
from skillopt.model import copilot_backend as _copilot
from skillopt.model import minimax_backend as _minimax
from skillopt.model import openai_compatible_backend as _openai_compat
from skillopt.model import qwen_backend as _qwen
from skillopt.model.backend_config import (  # noqa: F401
    configure_claude_code_exec,
    configure_codex_exec,
    configure_codex_exec_from_config,
    configure_copilot_chat,
    configure_copilot_exec,
    configure_cursor_exec,
    get_claude_code_exec_config,
    get_codex_exec_config,
    get_copilot_chat_config,
    get_copilot_exec_config,
    get_cursor_exec_config,
    get_optimizer_backend,
    get_target_backend,
    is_optimizer_chat_backend,
    is_target_chat_backend,
    is_target_exec_backend,
    set_optimizer_backend,
    set_target_backend,
)
from skillopt.model.azure_openai import configure_azure_openai  # noqa: F401
from skillopt.model.minimax_backend import configure_minimax_chat  # noqa: F401
from skillopt.model.qwen_backend import configure_qwen_chat  # noqa: F401
from skillopt.model.common import normalize_backend_name


def set_backend(name: str | None) -> str:
    """Backward-compatible global backend setter.

    Historically the codebase used one shared backend for both optimizer and
    target. Keep that entry point so older scripts continue to work, while
    mapping it onto the split optimizer/target backend model.
    """
    normalized = normalize_backend_name(name)
    if normalized in {"azure_openai", "openai_chat"}:
        set_optimizer_backend("openai_chat")
        set_target_backend("openai_chat")
        return "azure_openai"
    if normalized == "claude_chat":
        set_optimizer_backend("claude_chat")
        set_target_backend("claude_chat")
        return "claude_chat"
    if normalized in {"codex", "codex_exec"}:
        set_optimizer_backend("codex_exec")
        set_target_backend("codex_exec")
        return normalized
    if normalized == "claude_code_exec":
        set_optimizer_backend("openai_chat")
        set_target_backend(normalized)
        return normalized
    if normalized == "cursor_exec":
        set_optimizer_backend("openai_chat")
        set_target_backend("cursor_exec")
        return "cursor_exec"
    if normalized == "copilot_chat":
        # The CLI-authenticated backend drives both roles without a separate
        # provider API key; inference still uses the Copilot cloud service.
        set_optimizer_backend("copilot_chat")
        set_target_backend("copilot_chat")
        return "copilot_chat"
    if normalized == "copilot_exec":
        set_optimizer_backend("openai_chat")
        set_target_backend("copilot_exec")
        return "copilot_exec"
    if normalized == "qwen_chat":
        set_optimizer_backend("openai_chat")
        set_target_backend("qwen_chat")
        return "qwen_chat"
    if normalized == "minimax_chat":
        set_optimizer_backend("openai_chat")
        set_target_backend("minimax_chat")
        return "minimax_chat"
    if normalized == "openai_compatible":
        set_optimizer_backend("openai_compatible")
        set_target_backend("openai_compatible")
        return "openai_compatible"
    if normalized == "switchyard":
        set_optimizer_backend("switchyard")
        set_target_backend("switchyard")
        return "switchyard"
    raise ValueError(f"Unsupported legacy backend: {name!r}")


def get_backend_name() -> str:
    """Best-effort backward-compatible backend summary."""
    optimizer = get_optimizer_backend()
    target = get_target_backend()
    if optimizer == "claude_chat" and target == "claude_chat":
        return "claude_chat"
    if optimizer == "qwen_chat" and target == "qwen_chat":
        return "qwen_chat"
    if optimizer == "copilot_chat" and target == "copilot_chat":
        return "copilot_chat"
    if optimizer == "openai_chat" and target == "openai_chat":
        return "azure_openai"
    if optimizer == "codex_exec" and target == "codex_exec":
        return "codex"
    if optimizer == "openai_chat" and target == "qwen_chat":
        return "qwen_chat"
    if optimizer == "openai_chat" and target == "minimax_chat":
        return "minimax_chat"
    if optimizer == "openai_chat" and target == "cursor_exec":
        return "cursor_exec"
    if optimizer == "openai_chat" and target == "copilot_exec":
        return "copilot_exec"
    if optimizer == "openai_compatible" and target == "openai_compatible":
        return "openai_compatible"
    if optimizer == "switchyard" and target == "switchyard":
        return "switchyard"
    return f"{optimizer}+{target}"


def chat_optimizer(
    system: str,
    user: str,
    max_completion_tokens: int = 16384,
    retries: int = 5,
    stage: str = "optimizer",
    reasoning_effort: str | None = None,
    extra_body: dict[str, Any] | None = None,
    timeout: int | None = None,
) -> tuple[str, dict]:
    if get_optimizer_backend() == "claude_chat":
        return _claude.chat_optimizer(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            timeout=timeout,
        )
    if get_optimizer_backend() == "copilot_chat":
        return _copilot.chat_optimizer(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
    if get_optimizer_backend() == "qwen_chat":
        return _qwen.chat_optimizer(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
    if get_optimizer_backend() == "minimax_chat":
        return _minimax.chat_optimizer(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
    if get_optimizer_backend() == "openai_compatible":
        return _openai_compat.chat_optimizer(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            extra_body=extra_body,
            timeout=timeout,
        )
    if get_optimizer_backend() == "codex_exec":
        return _codex.chat_optimizer(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            timeout=timeout,
        )
    if get_optimizer_backend() == "switchyard":
        from skillopt.model.switchyard_backend import chat_optimizer_switchyard
        return chat_optimizer_switchyard(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
    return _openai.chat_optimizer(
        system=system,
        user=user,
        max_completion_tokens=max_completion_tokens,
        retries=retries,
        stage=stage,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
    )


def chat_target(
    system: str,
    user: str,
    max_completion_tokens: int = 16384,
    retries: int = 5,
    stage: str = "target",
    reasoning_effort: str | None = None,
    extra_body: dict[str, Any] | None = None,
    timeout: int | None = None,
) -> tuple[str, dict]:
    if get_target_backend() == "claude_chat":
        return _claude.chat_target(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            timeout=timeout,
        )
    if get_target_backend() == "qwen_chat":
        return _qwen.chat_target(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
    if get_target_backend() == "minimax_chat":
        return _minimax.chat_target(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
    if get_target_backend() == "openai_compatible":
        return _openai_compat.chat_target(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            extra_body=extra_body,
            timeout=timeout,
        )
    if get_target_backend() == "copilot_chat":
        return _copilot.chat_target(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
    if get_target_backend() == "switchyard":
        from skillopt.model.switchyard_backend import chat_target_switchyard
        return chat_target_switchyard(
            system=system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
    if not is_target_chat_backend():
        raise NotImplementedError(
            "chat_target is only supported with target_backend=openai_chat, claude_chat, qwen_chat, minimax_chat, "
            "copilot_chat, or openai_compatible. Exec backends are handled in environment-specific rollout code."
        )
    return _openai.chat_target(
        system=system,
        user=user,
        max_completion_tokens=max_completion_tokens,
        retries=retries,
        stage=stage,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
    )


def chat_optimizer_messages(
    messages: list[dict[str, Any]],
    max_completion_tokens: int = 16384,
    retries: int = 5,
    stage: str = "optimizer",
    reasoning_effort: str | None = None,
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    return_message: bool = False,
    timeout: int | None = None,
    extra_body: dict[str, Any] | None = None,
) -> tuple[Any, dict]:
    if get_optimizer_backend() == "copilot_chat":
        return _copilot.chat_optimizer_messages(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            tools=tools,
            tool_choice=tool_choice,
            return_message=return_message,
            timeout=timeout,
        )
    if get_optimizer_backend() == "claude_chat":
        return _claude.chat_optimizer_messages(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            tools=tools,
            tool_choice=tool_choice,
            return_message=return_message,
            timeout=timeout,
        )
    if get_optimizer_backend() == "qwen_chat":
        return _qwen.chat_optimizer_messages(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            tools=tools,
            tool_choice=tool_choice,
            return_message=return_message,
            timeout=timeout,
        )
    if get_optimizer_backend() == "minimax_chat":
        return _minimax.chat_target_messages(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            tools=tools,
            tool_choice=tool_choice,
            return_message=return_message,
            timeout=timeout,
        )
    if get_optimizer_backend() == "openai_compatible":
        return _openai_compat.chat_optimizer_messages(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            tools=tools,
            tool_choice=tool_choice,
            return_message=return_message,
            timeout=timeout,
            extra_body=extra_body,
        )
    if get_optimizer_backend() == "codex_exec":
        return _codex.chat_optimizer_messages(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            tools=tools,
            tool_choice=tool_choice,
            return_message=return_message,
            timeout=timeout,
        )
    if get_optimizer_backend() == "switchyard":
        from skillopt.model.switchyard_backend import chat_optimizer_switchyard
        return chat_optimizer_switchyard(
            system="",  # We don't have system separated here
            user="",  # We'll use messages directly
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
    return _openai.chat_optimizer_messages(
        messages=messages,
        max_completion_tokens=max_completion_tokens,
        retries=retries,
        stage=stage,
        reasoning_effort=reasoning_effort,
        tools=tools,
        tool_choice=tool_choice,
        return_message=return_message,
        timeout=timeout,
    )


def chat_target_messages(
    messages: list[dict[str, Any]],
    max_completion_tokens: int = 16384,
    retries: int = 5,
    stage: str = "target",
    reasoning_effort: str | None = None,
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    return_message: bool = False,
    timeout: int | None = None,
    extra_body: dict[str, Any] | None = None,
) -> tuple[Any, dict]:
    if get_target_backend() == "copilot_chat":
        return _copilot.chat_target_messages(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            tools=tools,
            tool_choice=tool_choice,
            return_message=return_message,
            timeout=timeout,
        )
    if get_target_backend() == "claude_chat":
        return _claude.chat_target_messages(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            tools=tools,
            tool_choice=tool_choice,
            return_message=return_message,
            timeout=timeout,
        )
    if get_target_backend() == "qwen_chat":
        return _qwen.chat_target_messages(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            tools=tools,
            tool_choice=tool_choice,
            return_message=return_message,
            timeout=timeout,
        )
    if get_target_backend() == "minimax_chat":
        return _minimax.chat_target_messages(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            tools=tools,
            tool_choice=tool_choice,
            return_message=return_message,
        )
    if get_target_backend() == "openai_compatible":
        return _openai_compat.chat_target_messages(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            tools=tools,
            tool_choice=tool_choice,
            return_message=return_message,
            timeout=timeout,
            extra_body=extra_body,
        )
    if get_target_backend() == "switchyard":
        from skillopt.model.switchyard_backend import chat_target_switchyard
        return chat_target_switchyard(
            system="",
            user="",
            max_completion_tokens=max_completion_tokens,
            retries=retries,
            stage=stage,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
    if not is_target_chat_backend():
        raise NotImplementedError(
            "chat_target_messages is only supported with target_backend=openai_chat, claude_chat, qwen_chat, "
            "minimax_chat, copilot_chat, or openai_compatible. Exec backends are handled in environment-specific "
            "rollout code."
        )
    return _openai.chat_target_messages(
        messages=messages,
        max_completion_tokens=max_completion_tokens,
        retries=retries,
        stage=stage,
        reasoning_effort=reasoning_effort,
        tools=tools,
        tool_choice=tool_choice,
        return_message=return_message,
        timeout=timeout,
    )


def chat_messages_with_deployment(
    deployment: str,
    messages: list[dict[str, Any]],
    max_completion_tokens: int = 16384,
    retries: int = 5,
    stage: str = "custom",
    reasoning_effort: str | None = None,
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    return_message: bool = False,
    timeout: int | None = None,
) -> tuple[Any, dict]:
    return _openai.chat_messages_with_deployment(
        deployment=deployment,
        messages=messages,
        max_completion_tokens=max_completion_tokens,
        retries=retries,
        stage=stage,
        reasoning_effort=reasoning_effort,
        tools=tools,
        tool_choice=tool_choice,
        return_message=return_message,
        timeout=timeout,
    )


def chat_with_deployment(
    deployment: str,
    system: str,
    user: str,
    max_completion_tokens: int = 16384,
    retries: int = 5,
    stage: str = "custom",
    reasoning_effort: str | None = None,
    timeout: int | None = None,
) -> tuple[str, dict]:
    return _openai.chat_with_deployment(
        deployment=deployment,
        system=system,
        user=user,
        max_completion_tokens=max_completion_tokens,
        retries=retries,
        stage=stage,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
    )


def get_token_summary() -> dict:
    return _openai_compat.get_token_summary()


def reset_token_tracker() -> None:
    _openai_compat.reset_token_tracker()


def set_reasoning_effort(effort: str | None) -> None:
    _openai_compat.set_reasoning_effort(effort)


def set_target_deployment(deployment: str) -> None:
    _openai_compat.set_target_deployment(deployment)
    _openai.set_target_deployment(deployment)


def set_optimizer_deployment(deployment: str) -> None:
    _openai_compat.set_optimizer_deployment(deployment)
    _openai.set_optimizer_deployment(deployment)