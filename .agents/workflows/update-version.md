---
description: Update software version in python code and README.md
---

Follow these steps to update the HELXAID application version:

1. Ask the User for the newly desired version number (e.g., `4.11`), unless they already specified it in the prompt.
2. Update `README.md`:
   - Locate the `<img src="https://img.shields.io/badge/Version-v...` line and change it to the new version.
   - Example: `<img src="https://img.shields.io/badge/Version-v4.11-orange?style=for-the-badge" alt="Version">`
   - Add a new block under `## ✦ Changelog` for `### v[NEW_VERSION]` (e.g., `### v4.11`) right at the top. Ask the user what the changelog should include if it's not clear.
3. Update Python Source Code (`launcher.py` or other files that define version):
   - Replace the `CURRENT_VERSION = "..."` definition in `launcher.py` (around lines 8291 and 8349).
   - Replace the `version_label = QLabel("Version - ...")` in the `open_quick_settings()` UI in `launcher.py` (around line 8068).
4. Commit the changes and Push directly to GitHub automatically:
   ```powershell
   git add .
   git commit -m "Update software version to [NEW_VERSION]"
   git push
   ```
5. Run standard verifications or inform the user that version update and push are complete!