"""Env-specific analyst prompt resolution.

Regression guard for the webintel optimizer stall: with no
``skillopt/envs/webintel/prompts/analyst_error.md`` the adapter fell back to
the growth-prone generic prompt (which lists ``append`` / ``insert_after``
first), so every proposed edit grew the skill and was killed by the
no-growth veto.

The same gap existed on the SUCCESS side (no env-specific
``analyst_success.md``), which stalled the run again at step 4: the generic
success prompt lists ``append`` / ``insert_after`` first and has no no-growth
rule, so the success analyst produced 3 growing ``insert_after`` edits that
were vetoed.
"""
import pytest

from skillopt.envs.hermes_prompt.adapter import HermesPromptAdapter
from skillopt.envs.webintel.adapter import WebIntelAdapter
from skillopt.gradient.reflect import _resolve_prompt
from skillopt.prompts import load_prompt


def _brevity_constrained(prompt: str) -> bool:
    return (
        "THE SKILL MUST NOT GROW" in prompt
        and "NEVER use `op: append` or `op: insert_after`" in prompt
        and "NO `append`, NO `insert_after`" in prompt
    )


@pytest.mark.parametrize("env", ["webintel", "hermes_prompt"])
@pytest.mark.parametrize("name", ["analyst_error", "analyst_success"])
def test_env_analyst_prompt_is_brevity_constrained(env, name):
    prompt = load_prompt(name, env=env)
    assert _brevity_constrained(prompt), f"{env} {name}.md lost its no-growth rule"


@pytest.mark.parametrize("adapter_cls", [WebIntelAdapter, HermesPromptAdapter])
@pytest.mark.parametrize("hook,name", [
    ("get_error_minibatch_prompt", "analyst_error"),
    ("get_success_minibatch_prompt", "analyst_success"),
])
def test_adapter_resolves_its_env_analyst_prompt(adapter_cls, hook, name):
    """The adapter hooks feeding ``run_minibatch_reflect`` must return the
    env-specific prompt, and ``_resolve_prompt`` must pass it through."""
    adapter = adapter_cls.__new__(adapter_cls)  # no I/O-heavy __init__
    resolved = getattr(adapter, hook)()
    assert resolved is not None
    assert _brevity_constrained(resolved)
    # This is exactly how reflect.py consumes it (error_system=/success_system=).
    assert _resolve_prompt(resolved, name, "patch") == resolved


@pytest.mark.parametrize("name", ["analyst_error", "analyst_success"])
def test_generic_analyst_prompt_still_permits_growth_ops(name):
    """Other envs rely on the generic prompts — they must stay unchanged."""
    generic = load_prompt(name)
    assert '"op": "append"' in generic
    assert '"op": "insert_after"' in generic
    assert not _brevity_constrained(generic)
