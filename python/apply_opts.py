"""Script to apply all startup optimizations correctly."""
import re

with open('python/launcher.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# ============================================
# 1. Remove CrosshairWidget import at module level
# ============================================
for i, line in enumerate(lines):
    if line.strip() == 'from CrosshairWidget import CrosshairWidget':
        lines[i] = '# CrosshairWidget imported lazily in _setup_crosshair_panel to speed up startup'
        print(f'Removed CrosshairWidget import at line {i+1}')
        break

# ============================================
# 2. Add lazy import in _setup_crosshair_panel
# ============================================
for i, line in enumerate(lines):
    if 'def _setup_crosshair_panel(self):' in line:
        # Find the line with self.crosshair_panel = CrosshairWidget()
        for j in range(i, min(i+10, len(lines))):
            if 'self.crosshair_panel = CrosshairWidget()' in lines[j]:
                # Insert lazy import before this line
                indent = '        '
                new_lines = [
                    f'{indent}# Lazy import to speed up startup - CrosshairWidget imports OpenGL which is slow',
                    f'{indent}from CrosshairWidget import CrosshairWidget',
                    f'{indent}self.crosshair_panel = CrosshairWidget()'
                ]
                lines[j] = '\n'.join(new_lines)
                print(f'Added lazy import in _setup_crosshair_panel at line {j+1}')
                break
        break

# ============================================
# 3. Defer refresh() call
# ============================================
for i, line in enumerate(lines):
    if 'self.update_grid_size()' in line and i > 4000:
        # Check if next line is self.refresh()
        if i+1 < len(lines) and 'self.refresh()' in lines[i+1]:
            lines[i+1] = '        # Defer refresh to after UI is shown - it takes ~1600ms\n        QTimer.singleShot(100, self.refresh)'
            print(f'Deferred refresh() call at line {i+2}')
            break

# ============================================
# 4. Defer crosshair panel creation
# ============================================
for i, line in enumerate(lines):
    if '# Setup Crosshair panel (panel 3)' in line and i+1 < len(lines) and 'self._setup_crosshair_panel()' in lines[i+1]:
        indent = '        '
        new_lines = [
            f'{indent}# Setup Crosshair panel (panel 3) - deferred to reduce startup time',
            f'{indent}# OpenGL/keyboard imports are heavy (~900ms), create placeholder instead',
            f'{indent}self._crosshair_placeholder = QWidget()',
            f'{indent}self._crosshair_placeholder.setObjectName("crosshairPlaceholder")',
            f'{indent}self.content_stack.insertWidget(PanelIndex.CROSSHAIR, self._crosshair_placeholder)',
            f'{indent}self.crosshair_panel = None'
        ]
        lines[i] = '\n'.join(new_lines)
        lines[i+1] = ''  # Clear the old line
        print(f'Deferred crosshair panel at line {i+1}')
        break

# Write back
new_content = '\n'.join(lines)
with open('python/launcher.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('\nAll optimizations applied!')
