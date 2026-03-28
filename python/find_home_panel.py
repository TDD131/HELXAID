"""Script to defer home panel creation for faster startup."""
import re

with open('python/launcher.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find where home panel setup starts and ends
# The home panel is created inline in __init__ after the sidebar
# We need to move it to a deferred method

# Find the section: after content_stack creation, before _setup_cpu_panel
# Look for the pattern where home panel widgets are added to content_stack

# The home panel is added at: self.content_stack.insertWidget(PanelIndex.HOME, self.home_panel)
# But it's created inline. Let's find where it starts.

# Pattern: After "self.content_stack = QStackedWidget()" there's sidebar creation
# Then home panel is created and added

# Find the line: "# ---- HOME PANEL ----" or similar
lines = content.split('\n')

# Find where home panel setup starts (after sidebar, before content_stack.addWidget for home)
start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if '# ---- HOME PANEL' in line or '# HOME PANEL' in line:
        start_idx = i
    if 'self.content_stack.insertWidget(PanelIndex.HOME' in line or 'self.content_stack.addWidget(self.home_panel' in line:
        end_idx = i
        break

if start_idx and end_idx:
    print(f'Found home panel section: lines {start_idx+1} to {end_idx+1}')
else:
    # Try another approach - find where games_scroll is created
    for i, line in enumerate(lines):
        if 'self.games_scroll = SmoothScrollArea()' in line:
            start_idx = i - 50  # Look backwards
            break
    
    print(f'Home panel creation starts around line {start_idx+1}')
    # Show context
    for i, line in enumerate(lines[start_idx:start_idx+10], start=start_idx+1):
        print(f'{i}: {line[:80]}')

print('\\nSearching for content_stack usage...')
for i, line in enumerate(lines):
    if 'content_stack' in line and ('insertWidget' in line or 'addWidget' in line):
        print(f'{i+1}: {line[:80]}')
