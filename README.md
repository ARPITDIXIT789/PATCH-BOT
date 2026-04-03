# PATCH-BOT

Telegram bot for parsing offsets, detecting matching hooks from `hook.txt`, and generating `PATCH_LIB(...)` output.

## Features

- Parses plain offsets, patch lines, and hook-offset style input
- Matches only the hooks for offsets the user actually sends
- Shows hook preview and generated patch code
- Supports quick RET, RET0, and NOP conversions
- Loads bot settings from `.env`

## Setup

```powershell
pip install -r requirements.txt
```

Create `.env` in the project root:

```env
BOT_TOKEN=your-telegram-token
HOOK_FILE=hook.txt
LOG_LEVEL=INFO
```

## Run

```powershell
python bot.py
```

## Notes

- `hook.txt` should contain one clean hook block per offset.
- Every hook block should end with `HOOK_LIB(...)` or `HOOK_LIB_NO_ORIG(...)`.
- Runtime logs are written locally and ignored by git.
