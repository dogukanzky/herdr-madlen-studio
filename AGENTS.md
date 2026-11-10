# Madlen Studio distribution

This is a portable Herdr theme, not the user's Herdr home.

- Read README.md before changing installation or UI behavior.
- Never copy runtime state, transcripts, database files, screenshots of real sessions,
  tokens, settings.json, machine configuration or backup directories into this repository.
- Source of truth: theme/. Do not overwrite the maintainer's live installation while testing.
- Tests: `python3 -m unittest discover -s tests`,
  `python3 -m unittest discover -s theme/mods/madlen-chat -p 'test_*.py'`,
  `node test-chat-state.cjs` (Node is only a development dependency).
- `extras/outputs/` is optional, local macOS source; do not execute its installer during
  a theme-only install. Do not change or replace a user's existing outputs-browser mod.
- Chat must bind to the selected process on its actual machine. Never guess a conversation by folder or time.
- Keep the installer transactional for theme files and preserve unrelated files and sessions.
