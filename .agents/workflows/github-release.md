---
description: Create a GitHub Release and upload the HELXAID portable exe as asset via browser
---

This workflow creates a new GitHub Release for HELXAID and uploads the built portable exe as a downloadable asset directly through the GitHub website.

## Prerequisites
- `dist/HELXAID.exe` must already exist (run `/build` first)

## Steps

1. Ask the user for the release version tag (e.g. `v4.8`) and a short release title/description. If not provided, use the current app version and summarize recent changes.

2. Open GitHub Releases page in the browser and create a new release:
   - Navigate to: https://github.com/TDD131/HELXAID/releases/new
   - Fill in the **Tag version** field (e.g. `v4.8`)
   - Fill in the **Release title** (e.g. `HELXAID v4.8`)
   - Fill in the **Description** with a changelog summary
   - Upload the file as an asset:
     - `D:\Software\tididi\Game Launcher\dist\HELXAID.exe` (Portable)
   - Click **Publish release**

3. Report the release URL back to the user.

## Notes
- Tag must be a new unique version tag (e.g. `v4.8`, `v4.9`), don't reuse existing tags.
- Mark as **Pre-release** if this is a beta/test build.
- The browser agent will handle the file upload interaction on the GitHub page.
