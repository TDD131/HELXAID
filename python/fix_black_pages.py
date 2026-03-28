from pathlib import Path

p = Path('python/launcher.py')
text = p.read_text(encoding='utf-8')

nl = '\r\n' if '\r\n' in text else '\n'

changed = False

def replace_all(old: str, new: str) -> None:
    global text, changed
    if old in text:
        text = text.replace(old, new)
        changed = True

# Fix Music panel: must replace placeholder at index 1 instead of appending
old_music_add = '        self.content_stack.addWidget(self.music_panel)'
new_music_add = (
    '        if hasattr(self, "_music_placeholder"):' + nl +
    '            try:' + nl +
    '                self.content_stack.removeWidget(self._music_placeholder)' + nl +
    '            except Exception:' + nl +
    '                pass' + nl +
    '            self._music_placeholder.deleteLater()' + nl +
    '            delattr(self, "_music_placeholder")' + nl +
    '        self.content_stack.insertWidget(1, self.music_panel)'
)
replace_all(old_music_add, new_music_add)

# Fix Macro panel: replace placeholder at index 4 instead of appending
old_macro_add_1 = '            self.content_stack.addWidget(self.macro_panel)'
new_macro_add = (
    '            if hasattr(self, "_macro_placeholder"):' + nl +
    '                try:' + nl +
    '                    self.content_stack.removeWidget(self._macro_placeholder)' + nl +
    '                except Exception:' + nl +
    '                    pass' + nl +
    '                self._macro_placeholder.deleteLater()' + nl +
    '                delattr(self, "_macro_placeholder")' + nl +
    '            self.content_stack.insertWidget(4, self.macro_panel)'
)
replace_all(old_macro_add_1, new_macro_add)

old_macro_add_2 = '            self.content_stack.addWidget(self.macro_panel)'
replace_all(old_macro_add_2, new_macro_add)

# Fix Hardware panel: replace placeholder at index 5 instead of appending
old_hw_add = '            self.content_stack.addWidget(self.hardware_panel)'
new_hw_add = (
    '            if hasattr(self, "_hardware_placeholder"):' + nl +
    '                try:' + nl +
    '                    self.content_stack.removeWidget(self._hardware_placeholder)' + nl +
    '                except Exception:' + nl +
    '                    pass' + nl +
    '                self._hardware_placeholder.deleteLater()' + nl +
    '                delattr(self, "_hardware_placeholder")' + nl +
    '            self.content_stack.insertWidget(5, self.hardware_panel)'
)
replace_all(old_hw_add, new_hw_add)

if changed:
    p.write_text(text, encoding='utf-8')
    print('Applied placeholder replacement fixes for Music/Macro/Hardware panels')
else:
    print('No changes applied (patterns not found)')
