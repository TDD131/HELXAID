---
description: Update software version in python code and README.md
---

Follow these steps to update the HELXAID application version:

1. Ask the User for the newly desired version number (e.g., `4.11`), unless they already specified it in the prompt.
2. Update `README.md`:
   - Locate the `<img src="https://img.shields.io/badge/Version-v...` line and change it to the new version.
   - Example: `<img src="https://img.shields.io/badge/Version-v4.11-orange?style=for-the-badge" alt="Version">`
   - Add a new block under `## ✦ Changelog` for `### v[NEW_VERSION]` (e.g., `### v4.11`) right at the top. Ask the user what the changelog should include if it's not clear.
3. Update Python Source Code (`launcher.py`) — **There are THREE places that must ALL be updated in sync**:
   - **[1] `check_for_updates()` function** (search `CURRENT_VERSION = ` inside `def check_for_updates`): This is the version sent to the GitHub API comparison thread.
   - **[2] `_on_update_result()` function** (search `CURRENT_VERSION = ` inside `def _on_update_result`): This is the version displayed in the "Update Available" popup dialog. **This is a SEPARATE variable from [1] and is commonly missed!**
   - **[3] `open_quick_settings()` UI label** (search `version_label = QLabel("Version - ..."`): This is the version shown in the Quick Settings panel.
   - Use `grep/search` to locate the exact line numbers, as they shift over time. Do NOT assume hardcoded line numbers.
4. Commit the changes and Push directly to GitHub automatically:
   ```powershell
   git add .
   git commit -m "Update software version to [NEW_VERSION]"
   git push
   ```
5. Run standard verifications or inform the user that version update and push are complete!