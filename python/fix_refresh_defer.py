"""Script to defer refresh() call for faster startup."""
import re

with open('python/launcher.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the refresh call in __init__
old_text = '''        self.update_grid_size()
        self.refresh()
        
        # Re-apply theme now that games_container exists (for background image)'''

new_text = '''        self.update_grid_size()
        # Defer refresh to after UI is shown - it's slow (~1600ms)
        QTimer.singleShot(100, self.refresh)
        
        # Re-apply theme now that games_container exists (for background image)'''

if old_text in content:
    content = content.replace(old_text, new_text)
    with open('python/launcher.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('SUCCESS: refresh() deferred')
else:
    print('ERROR: Pattern not found')
    # Debug
    lines = content.split('\n')
    for i, line in enumerate(lines[4445:4455], start=4446):
        print(f'{i}: {repr(line)}')
