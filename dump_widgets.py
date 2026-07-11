import sys, win32gui, win32process, psutil
import PySide6.QtWidgets
app = PySide6.QtWidgets.QApplication.instance()
if app:
    with open('widget_dump.txt', 'w') as f:
        widgets = app.allWidgets()
        f.write(f'Total widgets: {len(widgets)}\n')
        from collections import Counter
        c = Counter([type(w).__name__ for w in widgets])
        for k,v in c.most_common():
            f.write(f'{k}: {v}\n')
