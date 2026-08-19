# Prompt Note (addendum to core guidance)

Behavioral addendum tuned by SkillOpt. The core system prompt is fixed and must
not be edited here — only this note is optimized. Keep it short, concrete, and
evidence-backed.

When running a project's Python code or tests, use that project's own
environment (.venv/bin/python, uv run) rather than the agent's global
interpreter — a pre-set PYTHONPATH can shadow the project's dependencies.
