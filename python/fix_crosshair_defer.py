"""Script to defer crosshair panel creation for faster startup."""
import re

with open('python/launcher.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the crosshair panel setup
old_text = '''        # Setup CPU control panel (panel 2)
        self._setup_cpu_panel()
        
        # Setup Crosshair panel (panel 3)
        self._setup_crosshair_panel()
        
        # Setup Macro panel (panel 4)
        # Initialized lazily when opened to reduce baseline RAM.'''

new_text = '''        # Setup CPU control panel (panel 2)
        self._setup_cpu_panel()
        
        # Setup Crosshair panel (panel 3) - deferred to reduce startup time
        # OpenGL/keyboard imports are heavy (~900ms), create placeholder instead
        self._crosshair_placeholder = QWidget()
        self._crosshair_placeholder.setObjectName("crosshairPlaceholder")
        self.content_stack.insertWidget(PanelIndex.CROSSHAIR, self._crosshair_placeholder)
        self.crosshair_panel = None
        
        # Setup Macro panel (panel 4)
        # Initialized lazily when opened to reduce baseline RAM.'''

if old_text in content:
    content = content.replace(old_text, new_text)
    with open('python/launcher.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('SUCCESS: Crosshair panel deferred')
else:
    print('ERROR: Pattern not found')
    # Debug: show what's around line 4462
    lines = content.split('\n')
    for i, line in enumerate(lines[4460:4475], start=4461):
        print(f'{i}: {repr(line)}')
