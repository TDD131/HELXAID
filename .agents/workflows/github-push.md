---
description: Upload and push project changes to GitHub
---
// turbo-all
Follow these steps to upload the project to GitHub:

1. Check the current git status:
```powershell
git status
```

2. Add all changes to the staging area:
```powershell
git add .
```

3. Ask the user for a commit message. If no message is provided, summarize the latest changes based on conversation context.

4. Commit the changes:
```powershell
git commit -m "<Commit Message>"
```

5. Push to remote WITHOUT force push (safe push only):
```powershell
git push
```

IMPORTANT RULES:
- NEVER use `git push -f` or `git push --force` unless the user explicitly asks for it.
- If `git push` is rejected due to remote changes, do `git pull --rebase` first, then push again.
- Do NOT wipe remote history.
