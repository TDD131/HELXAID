"""Script to defer home panel creation for faster startup."""
import re

with open('python/launcher.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# Find the home panel section (lines 3673-4380, 0-indexed: 3672-4379)
start_idx = 3672  # Line with "# Panel 0: Home"
end_idx = 4379    # Line before "# Setup CPU control panel"

# Extract the home panel code
home_panel_lines = lines[start_idx:end_idx]

# Create the deferred method with proper indentation
method_lines = [
    '    def _setup_home_panel(self):',
    '        """Setup the home panel with game grid - deferred for faster startup."""',
]

for line in home_panel_lines:
    # Add proper indentation (method body needs 8 spaces, not 4)
    if line.strip():
        method_lines.append('    ' + line)
    else:
        method_lines.append('')

# Find where to insert the method (before _setup_cpu_panel)
insert_idx = None
for i, line in enumerate(lines):
    if 'def _setup_cpu_panel(self):' in line:
        insert_idx = i
        break

# Create placeholder code for __init__
placeholder_lines = [
    '        # Panel 0: Home (Game Grid) - deferred for faster startup',
    '        # Create placeholder, actual panel loaded after window shows',
    '        self._home_placeholder = QWidget()',
    '        self._home_placeholder.setObjectName("homePlaceholder")',
    '        self.content_stack.addWidget(self._home_placeholder)',
    '        self.home_panel = None',
    '',
    '        # Defer home panel creation to after window is shown',
    '        QTimer.singleShot(50, self._setup_home_panel)',
    '',
]

# Build new content
new_lines = (
    lines[:start_idx] + 
    placeholder_lines + 
    lines[end_idx:insert_idx-1] +  # Skip the blank line before _setup_cpu_panel
    method_lines + 
    [''] + 
    lines[insert_idx-1:]
)

# Write back
new_content = '\n'.join(new_lines)
with open('python/launcher.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f'Extracted {len(home_panel_lines)} lines to _setup_home_panel method')
print(f'Inserted method at line {start_idx + len(placeholder_lines) + (end_idx - start_idx)}')
print('Done!')
