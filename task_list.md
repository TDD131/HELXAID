# Task: Final Fix for Shortcut Visibility (Ctrl+K+O)

- **Status**: 🟢 In Progress
- **Created**: 2026-03-28
- **Last Updated**: 2026-03-28

## 📋 Task Overview
The user wants the specific text `Ctrl+K+O` to appear in the menu on the right. Standard Qt `setShortcut` fails to display this simultaneous combination as it conflicts with the chord prefix. I will use a manual visual fix to achieve the requested look while maintaining stable functionality via a background chord handler.

## 🛠️ Implementation Checklist

### Phase 1: Manual Visual Fix
- [ ] Change `action_select_folder` label to include `\tCtrl+K+O` in `MusicPanelWidget.py`. [MusicPanelWidget.py](file:///d:/Software/tididi/Game%20Launcher/python/MusicPanelWidget.py).
- [ ] Remove `action_select_folder.setShortcut` to prevent Qt from adding its own text.

### Phase 2: Functional Chord Support
- [ ] Create a `QShortcut` for `QKeySequence("Ctrl+K, O")` in `MusicPanelWidget` initialized in `_connect_signals`.
- [ ] Connect its `activated` signal to `_browse_folder_direct`.

### Phase 3: Verification
- [ ] Verify: Menu text clearly says `Ctrl+K+O` on the right.
- [ ] Verify: Pressing `Ctrl+K` then `O` opens the folder dialog.
- [ ] Verify: Pressing `Ctrl+O` still opens the file dialog.

## 📝 Progress Logs
- **2026-03-28 19:05**: Implementing 'Visual Injection' strategy to force-display the requested shortcut text.
