"""Apply startup optimizations to launcher.py"""
import re

with open('python/launcher.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove CrosshairWidget module-level import
content = content.replace(
    'from CrosshairWidget import CrosshairWidget',
    '# CrosshairWidget imported lazily in _setup_crosshair_panel to speed up startup'
)

# 2. Add lazy import in _setup_crosshair_panel
content = content.replace(
    '    def _setup_crosshair_panel(self):\n        """Setup the Crosshair overlay panel."""\n        self.crosshair_panel = CrosshairWidget()',
    '''    def _setup_crosshair_panel(self):
        """Setup the Crosshair overlay panel."""
        # Lazy import to speed up startup - CrosshairWidget imports OpenGL which is slow
        from CrosshairWidget import CrosshairWidget
        self.crosshair_panel = CrosshairWidget()'''
)

# 3. Defer crosshair panel creation in __init__
# Find and replace the inline crosshair setup with placeholder
old_crosshair = '''        # Setup Crosshair panel (panel 3)
        self._setup_crosshair_panel()'''
new_crosshair = '''        # Setup Crosshair panel (panel 3) - deferred to reduce startup time
        # OpenGL/keyboard imports are heavy (~900ms), create placeholder instead
        self._crosshair_placeholder = QWidget()
        self._crosshair_placeholder.setObjectName("crosshairPlaceholder")
        self.content_stack.insertWidget(3, self._crosshair_placeholder)
        self.crosshair_panel = None'''
content = content.replace(old_crosshair, new_crosshair)

# 4. Defer refresh() call
old_refresh = '''        self.update_grid_size()
        self.refresh()'''
new_refresh = '''        self.update_grid_size()
        # Defer refresh to after UI is shown - it takes ~1600ms
        QTimer.singleShot(100, self.refresh)'''
content = content.replace(old_refresh, new_refresh)

with open('python/launcher.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Optimizations applied successfully!')
