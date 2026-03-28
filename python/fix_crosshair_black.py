from pathlib import Path

p = Path('python/launcher.py')
text = p.read_text(encoding='utf-8')

nl = '\r\n' if '\r\n' in text else '\n'

old = nl.join([
    '    def _setup_crosshair_panel(self):',
    '        """Setup the Crosshair overlay panel."""',
    '        # Lazy import to speed up startup - CrosshairWidget imports OpenGL which is slow',
    '        from CrosshairWidget import CrosshairWidget',
    '        self.crosshair_panel = CrosshairWidget()',
    '        self.crosshair_panel.setStyleSheet("""',
    '            QWidget#crosshairPanel {',
    '                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,',
    '                    stop:0 #5D8736, stop:0.33 #809D3C, stop:0.66 #A9C46C, stop:1 #F4FFC3);',
    '            }',
    '        """)',
    '        if hasattr(self, "_crosshair_placeholder"):',
    '            try:',
    '                self.content_stack.removeWidget(self._crosshair_placeholder)',
    '            except Exception:',
    '                pass',
    '            self._crosshair_placeholder.deleteLater()',
    '            delattr(self, "_crosshair_placeholder")',
    '        self.content_stack.insertWidget(3, self.crosshair_panel)',
    ''
])

new = nl.join([
    '    def _setup_crosshair_panel(self):',
    '        """Setup the Crosshair overlay panel."""',
    '        # Lazy import to speed up startup - CrosshairWidget imports OpenGL which is slow',
    '        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel',
    '        from CrosshairWidget import CrosshairWidget',
    '        crosshair_widget = CrosshairWidget()',
    '        crosshair_widget.setObjectName("crosshairWidget")',
    '',
    '        self.crosshair_panel = QWidget()',
    '        self.crosshair_panel.setObjectName("crosshairPanel")',
    '        layout = QVBoxLayout(self.crosshair_panel)',
    '        layout.setContentsMargins(20, 20, 20, 20)',
    '        layout.setSpacing(12)',
    '',
    '        header = QLabel("HELXAIR - Crosshair Overlay")',
    '        header.setStyleSheet("color: #e0e0e0; font-size: 20px; font-weight: 600;")',
    '        layout.addWidget(header)',
    '        layout.addWidget(crosshair_widget, 1)',
    '',
    '        self.crosshair_panel.setStyleSheet("""',
    '            QWidget#crosshairPanel {',
    '                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,',
    '                    stop:0 #1a1a1a, stop:1 #0a0a0a);',
    '            }',
    '        """)',
    '        if hasattr(self, "_crosshair_placeholder"):',
    '            try:',
    '                self.content_stack.removeWidget(self._crosshair_placeholder)',
    '            except Exception:',
    '                pass',
    '            self._crosshair_placeholder.deleteLater()',
    '            delattr(self, "_crosshair_placeholder")',
    '        self.content_stack.insertWidget(3, self.crosshair_panel)',
    ''
])

if old not in text:
    raise SystemExit('ERROR: crosshair setup block not found; no changes applied')

text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')
print('Updated _setup_crosshair_panel to wrap CrosshairWidget in a visible container')
