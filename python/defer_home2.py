"""Defer home panel creation to after window shows."""
import re

with open('python/launcher.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the section: after content_stack creation, before _setup_cpu_panel
# The home panel is created inline from "# Panel 0: Home" to before "# Setup CPU control panel"

# Split into lines
lines = content.split('\n')

# Find markers
home_start = None
home_end = None
cpu_setup_line = None

for i, line in enumerate(lines):
    if '# Panel 0: Home (Game Grid)' in line:
        home_start = i
    if home_start and '# Setup CPU control panel' in line:
        home_end = i
        break

print(f'Home panel section: lines {home_start+1} to {home_end+1}')

# Extract home panel code
home_code = lines[home_start:home_end]

# Create placeholder code
placeholder = [
    '        # Panel 0: Home (Game Grid) - deferred for faster startup',
    '        # Create placeholder, actual panel loaded after window shows',
    '        self._home_placeholder = QWidget()',
    '        self._home_placeholder.setObjectName("homePlaceholder")',
    '        self.content_stack.addWidget(self._home_placeholder)',
    '        self.home_panel = None',
    '',
    '        # Defer home panel creation',
    '        QTimer.singleShot(50, self._setup_home_panel)',
    '',
]

# Create the _setup_home_panel method
method = [
    '    def _setup_home_panel(self):',
    '        """Setup the home panel with game grid - deferred for faster startup."""',
]

# Add the home panel code with proper indentation
for line in home_code:
    if line.strip():
        method.append('    ' + line)
    else:
        method.append('')

# Find where to insert the method (before _setup_cpu_panel definition)
insert_point = None
for i, line in enumerate(lines):
    if 'def _setup_cpu_panel(self):' in line:
        insert_point = i
        break

# Build new content
new_lines = (
    lines[:home_start] +
    placeholder +
    lines[home_end:insert_point] +
    [''] +
    method +
    [''] +
    lines[insert_point:]
)

with open('python/launcher.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print(f'Created _setup_home_panel method with {len(method)} lines')
print('Done!')
