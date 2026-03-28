"""Defer CPU panel setup."""
with open('python/launcher.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Defer CPU panel setup
old = '        # Setup CPU control panel (panel 2)\n        self._setup_cpu_panel()'
new = '''        # Setup CPU control panel (panel 2) - deferred
        self._cpu_placeholder = QWidget()
        self._cpu_placeholder.setObjectName("cpuPlaceholder")
        self.content_stack.insertWidget(2, self._cpu_placeholder)
        self.cpu_panel = None
        QTimer.singleShot(200, self._setup_cpu_panel)'''

if old in content:
    content = content.replace(old, new)
    with open('python/launcher.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Deferred CPU panel setup')
else:
    print('Pattern not found')
