"""Script to defer home panel creation for faster startup."""
import re

with open('python/launcher.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# Find the home panel section (lines 3735-4450, 0-indexed: 3734-4449)
# Start: "# Panel 0: Home (Game Grid)"
# End: before "self.update_grid_size()"

start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if '# Panel 0: Home (Game Grid)' in line:
        start_idx = i
    if start_idx and 'self.update_grid_size()' in line:
        end_idx = i
        break

print(f'Home panel section: lines {start_idx+1} to {end_idx+1}')

# Extract the home panel code (to be moved to a method)
home_panel_code = '\n'.join(lines[start_idx:end_idx])

# Create the new _setup_home_panel method
setup_method = '''    def _setup_home_panel(self):
        """Setup the home panel with game grid - deferred for faster startup."""
''' + '\n'.join('        ' + line if line.strip() else '' for line in home_panel_code.split('\n'))

# Replace the inline home panel code with placeholder + deferred call
placeholder_code = '''        # Panel 0: Home (Game Grid) - deferred for faster startup
        # Create placeholder first, actual panel loaded after window shows
        self._home_placeholder = QWidget()
        self._home_placeholder.setObjectName("homePlaceholder")
        self.content_stack.addWidget(self._home_placeholder)
        self.home_panel = None
        
        # Defer home panel creation
        QTimer.singleShot(50, self._setup_home_panel)
        
        '''

# Modify the content
new_lines = lines[:start_idx] + placeholder_code.split('\n') + lines[end_idx:]

# Find where to insert the new method (after _setup_crosshair_panel or similar)
insert_idx = None
for i, line in enumerate(new_lines):
    if 'def _setup_crosshair_panel(self):' in line:
        # Find the end of this method (next def at same indentation)
        for j in range(i+1, len(new_lines)):
            if new_lines[j].startswith('    def ') and not new_lines[j].startswith('    def _'):
                insert_idx = j
                break
        break

if insert_idx:
    # Insert the new method
    new_lines = new_lines[:insert_idx] + setup_method.split('\n') + [''] + new_lines[insert_idx:]
    print(f'Inserted _setup_home_panel method at line {insert_idx+1}')
else:
    print('ERROR: Could not find insertion point for _setup_home_panel')
    # Try to find end of __init__
    for i, line in enumerate(new_lines):
        if '[TIMING] GameLauncher.__init__ DONE' in line:
            print(f'Found timing marker at line {i+1}')

# Write back
new_content = '\n'.join(new_lines)
with open('python/launcher.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Done! Home panel creation deferred.')
