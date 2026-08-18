# NotebookLM Agent Skill

You are an agent using Google NotebookLM CLI to complete research and content tasks.

## Core Commands
- `notebooklm create "Title"` — create notebook
- `notebooklm source add "URL|file"` — add source
- `notebooklm ask "question"` — chat with sources
- `notebooklm generate audio|video|report|quiz|flashcards|slide-deck|infographic|mind-map|data-table "prompt"`
- `notebooklm download <type> ./output.ext`
- `notebooklm source list --json` — check source status
- `notebooklm artifact list` — check artifact status
- `notebooklm source add-research "query" --mode deep --no-wait` — deep research

## Key Rules
- Wait for sources to be READY before generation (check with `source list --json`)
- Use `-n <notebook_id>` for parallel safety
- Use `--json` for machine-readable output
- Use `--prompt-file` for long prompts
- Use `--save-as-note` to save chat answers as notes
- Audio/video generation: 10-45 min, use subagent pattern
- Rate limiting: retry after 5-10 min if generation fails
- Use `source add-research --mode deep` for comprehensive web research (15-30 min)
- Use `source fulltext <id>` to get indexed content
- Use `generate report --format study-guide --append "instructions"` for custom reports
- Use `generate report --format custom "PROMPT"` for fully custom reports
- Use `--language` flag or `notebooklm language set` for non-English output

## Workflow Patterns
1. Research → Podcast: create → add sources → wait → generate audio → download
2. Document Analysis: create → add sources → ask questions → save notes
3. Deep Research: create → add-research deep → wait → ask → generate report
4. Study Materials: create → add sources → generate quiz/flashcards → download

## Error Handling
- Auth expired → `notebooklm login` or `notebooklm auth refresh`
- Rate limited → wait 5-10 min, retry once
- Generation failed → check `artifact list`, retry later
- Source not ready → `source wait <id>` or check `source list`
