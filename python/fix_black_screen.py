from pathlib import Path

p = Path('python/launcher.py')
text = p.read_text(encoding='utf-8')

nl = '\r\n' if '\r\n' in text else '\n'

def repl_once(haystack: str, old: str, new: str) -> str:
    if old not in haystack:
        return haystack
    return haystack.replace(old, new, 1)

# 1) Ensure placeholders for indices 1..5 exist immediately after home_panel is added.
marker = (
    '        self.content_stack.addWidget(self.home_panel)' + nl +
    nl +
    nl
)

placeholder_block = (
    '        self.content_stack.addWidget(self.home_panel)' + nl +
    nl +
    nl +
    '        self._music_placeholder = QWidget()' + nl +
    '        self._music_placeholder.setObjectName("musicPlaceholder")' + nl +
    '        self.content_stack.addWidget(self._music_placeholder)' + nl +
    nl +
    '        self._cpu_placeholder = QWidget()' + nl +
    '        self._cpu_placeholder.setObjectName("cpuPlaceholder")' + nl +
    '        self.content_stack.addWidget(self._cpu_placeholder)' + nl +
    nl +
    '        self._crosshair_placeholder = QWidget()' + nl +
    '        self._crosshair_placeholder.setObjectName("crosshairPlaceholder")' + nl +
    '        self.content_stack.addWidget(self._crosshair_placeholder)' + nl +
    nl +
    '        self._macro_placeholder = QWidget()' + nl +
    '        self._macro_placeholder.setObjectName("macroPlaceholder")' + nl +
    '        self.content_stack.addWidget(self._macro_placeholder)' + nl +
    nl +
    '        self._hardware_placeholder = QWidget()' + nl +
    '        self._hardware_placeholder.setObjectName("hardwarePlaceholder")' + nl +
    '        self.content_stack.addWidget(self._hardware_placeholder)' + nl +
    nl +
    nl
)

if marker in text:
    window = text[text.find(marker):text.find(marker) + 1200]
    if 'musicPlaceholder' not in window and 'cpuPlaceholder' not in window and 'crosshairPlaceholder' not in window:
        text = repl_once(text, marker, placeholder_block)

# 2) Remove index-shifting placeholder insertions in __init__ (keep existing comment lines).
old_cpu_init = (
    '        # Setup CPU control panel (panel 2) - deferred' + nl +
    '        self._cpu_placeholder = QWidget()' + nl +
    '        self._cpu_placeholder.setObjectName("cpuPlaceholder")' + nl +
    '        self.content_stack.insertWidget(2, self._cpu_placeholder)' + nl +
    '        self.cpu_panel = None' + nl +
    '        QTimer.singleShot(200, self._setup_cpu_panel)' + nl
)
new_cpu_init = (
    '        # Setup CPU control panel (panel 2) - deferred' + nl +
    '        self.cpu_panel = None' + nl +
    '        QTimer.singleShot(200, self._setup_cpu_panel)' + nl
)
text = text.replace(old_cpu_init, new_cpu_init)

old_cross_init = (
    '        # Setup Crosshair panel (panel 3) - deferred to reduce startup time' + nl +
    '        # OpenGL/keyboard imports are heavy (~900ms), create placeholder instead' + nl +
    '        self._crosshair_placeholder = QWidget()' + nl +
    '        self._crosshair_placeholder.setObjectName("crosshairPlaceholder")' + nl +
    '        self.content_stack.insertWidget(3, self._crosshair_placeholder)' + nl +
    '        self.crosshair_panel = None' + nl
)
new_cross_init = (
    '        # Setup Crosshair panel (panel 3) - deferred to reduce startup time' + nl +
    '        # OpenGL/keyboard imports are heavy (~900ms), create placeholder instead' + nl +
    '        self.crosshair_panel = None' + nl
)
text = text.replace(old_cross_init, new_cross_init)

# 3) CPU panel: replace placeholder instead of addWidget.
old_cpu_prompt_add = (
    '            layout.addWidget(container)' + nl +
    '            self.content_stack.addWidget(self.cpu_panel)' + nl +
    '            return'
)
new_cpu_prompt_add = (
    '            layout.addWidget(container)' + nl +
    '            if hasattr(self, "_cpu_placeholder"):' + nl +
    '                try:' + nl +
    '                    self.content_stack.removeWidget(self._cpu_placeholder)' + nl +
    '                except Exception:' + nl +
    '                    pass' + nl +
    '                self._cpu_placeholder.deleteLater()' + nl +
    '                delattr(self, "_cpu_placeholder")' + nl +
    '            self.content_stack.insertWidget(2, self.cpu_panel)' + nl +
    '            return'
)
text = text.replace(old_cpu_prompt_add, new_cpu_prompt_add)

old_cpu_stack_add = (
    '        # Add to stack (will be added at end, use insertWidget for specific position)' + nl +
    '        if not hasattr(self, \'_cpu_panel_insert_index\'):' + nl +
    '            self.content_stack.addWidget(self.cpu_panel)' + nl +
    '        else:' + nl +
    '            self.content_stack.insertWidget(self._cpu_panel_insert_index, self.cpu_panel)' + nl +
    '            delattr(self, \'_cpu_panel_insert_index\')' + nl
)
new_cpu_stack_add = (
    '        # Add to stack (will be added at end, use insertWidget for specific position)' + nl +
    '        if hasattr(self, "_cpu_placeholder"):' + nl +
    '            try:' + nl +
    '                self.content_stack.removeWidget(self._cpu_placeholder)' + nl +
    '            except Exception:' + nl +
    '                pass' + nl +
    '            self._cpu_placeholder.deleteLater()' + nl +
    '            delattr(self, "_cpu_placeholder")' + nl +
    '        self.content_stack.insertWidget(2, self.cpu_panel)' + nl
)
text = text.replace(old_cpu_stack_add, new_cpu_stack_add)

# 4) Crosshair panel: replace placeholder instead of addWidget.
old_cross_add = '        self.content_stack.addWidget(self.crosshair_panel)'
new_cross_add = (
    '        if hasattr(self, "_crosshair_placeholder"):' + nl +
    '            try:' + nl +
    '                self.content_stack.removeWidget(self._crosshair_placeholder)' + nl +
    '            except Exception:' + nl +
    '                pass' + nl +
    '            self._crosshair_placeholder.deleteLater()' + nl +
    '            delattr(self, "_crosshair_placeholder")' + nl +
    '        self.content_stack.insertWidget(3, self.crosshair_panel)'
)
text = text.replace(old_cross_add, new_cross_add)

p.write_text(text, encoding='utf-8')
print('Applied content_stack placeholder/index fixes')
