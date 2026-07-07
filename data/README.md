# Data Folder

## Purpose
A local landing spot for the Excel files this platform will eventually
import and clean.

| Folder | Purpose |
|---|---|
| `raw/` | Excel files exactly as received, untouched. Kept separate so the original source of truth is never overwritten by a cleaning bug. |
| `processed/` | Cleaned/standardized output produced from `raw/` files, once the cleaning use case exists. |

## Why these folders are (almost) empty in git
Files placed in `raw/` or `processed/` will contain real people's names,
emails, phone numbers, and employers — Personally Identifiable Information
(PII). Committing that to git would:
1. Leak private data to anyone with repository access.
2. Keep leaking it forever — git history keeps old file versions even after
   they're deleted.

So `.gitignore` (project root) excludes everything in these two folders
except a `.gitkeep` placeholder, which exists purely so git keeps the empty
folder structure itself under version control. When real files are added
locally, they stay on your machine (or your team's private storage) only.
