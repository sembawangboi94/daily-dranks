# Daily Dranks Telegram Bot

Minimal Telegram water-tracking bot using `python-telegram-bot` (v22+) + SQLite.

## Features
- `/start` onboarding + **Open Panel** button
- `/w` opens quick panel (`+150`, `+250`, `+500`, custom prompt)
- `/w <ml>` logs custom amount
- `/leaderboard` shows today's totals in the current group (chat-scoped)
- `/undo` removes your last entry in this chat
- Safety: one allowed group only, configured by `/setup <ADMIN_CODE>`
- Singapore timezone support (`TZ=Asia/Singapore`)

## Files
- `bot.py` - Telegram bot and handlers
- `db.py` - SQLite storage and queries
- `requirements.txt`
- `.env.example`

## Setup
1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create `.env` from `.env.example` and fill values:
   - `BOT_TOKEN`
   - `ADMIN_CODE`
   - optional: `DB_PATH`, `TZ`
4. Start bot:
   ```bash
   python bot.py
   ```

## First-time use
1. Add bot to your target Telegram group.
2. In that group, run:
   ```
   /setup <ADMIN_CODE>
   ```
   This locks bot usage to that single group chat id.
3. In group, set your goal:
   ```
   /goal 2000
   ```
4. Log water:
   - `/w` to open panel
   - `/w 300` to log custom amount

## Notes for always-on macOS
- Keep the bot alive with `tmux`, `screen`, or a LaunchAgent (`launchd`).
- SQLite is stored at `DB_PATH` (default `water.db`) in the current directory.
