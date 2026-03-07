---
description: Upload and push project changes to GitHub
---
Follow these steps to upload the project to GitHub:

1. Check the current status of the repository:
```powershell
git status
```

2. Add all changes to the staging area:
```powershell
// turbo
git add .
```

3. Ask the user for a commit message. If no message is provided, ask the user what to put inside it or summarize the latest changes based on your memory.

4. Commit the changes:
```powershell
// turbo
git commit -m "<Commit Message>"
```

5. Push the changes to the remote repository:
```powershell
// turbo
git push
```
