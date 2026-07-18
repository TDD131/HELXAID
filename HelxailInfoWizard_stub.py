class HelxailInfoWizard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve
        from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QGraphicsOpacityEffect
        
        self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("WizardPanel")
        
        self.setStyleSheet('''
            QFrame#WizardPanel {
                background-color: rgba(15, 15, 15, 240);
                border: 2px solid #FF5B06;
                border-radius: 12px;
            }
            QWidget#TitleBar {
                background-color: rgba(0, 0, 0, 100);
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QLabel#Title {
                color: #FFFFFF;
                font-size: 14px;
                font-weight: bold;
                font-family: 'Inter', sans-serif;
            }
            QLabel#StepTitle {
                color: #FF5B06;
                font-size: 16px;
                font-weight: bold;
                font-family: 'Inter', sans-serif;
                margin-top: 10px;
            }
            QLabel#StepDesc {
                color: #E0E0E0;
                font-size: 13px;
                font-family: 'Inter', sans-serif;
                margin-top: 5px;
            }
            QPushButton#CloseBtn {
                background: transparent;
                color: #999999;
                font-size: 16px;
                font-weight: bold;
                border: none;
            }
            QPushButton#CloseBtn:hover { color: #FF5B06; }
            QPushButton.WizardBtn {
                background-color: rgba(255, 91, 6, 40);
                border: 1px solid #FF5B06;
                border-radius: 6px;
                color: white;
                font-family: 'Inter', sans-serif;
                font-size: 13px;
                padding: 6px 20px;
            }
            QPushButton.WizardBtn:hover { background-color: rgba(255, 91, 6, 80); }
            QPushButton.WizardBtn:disabled {
                background-color: rgba(100, 100, 100, 40);
                border: 1px solid #666666;
                color: #999999;
            }
        ''')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.title_bar = QWidget(self)
        self.title_bar.setObjectName("TitleBar")
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(15, 8, 15, 8)
        self.title_label = QLabel("HELXAIL First-Time Guide")
        self.title_label.setObjectName("Title")
        self.close_btn = QPushButton("?")
        self.close_btn.setObjectName("CloseBtn")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.clicked.connect(self.close_panel)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.close_btn)
        layout.addWidget(self.title_bar)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 15, 20, 20)
        
        self.step_title = QLabel()
        self.step_title.setObjectName("StepTitle")
        self.step_title.setWordWrap(True)
        content_layout.addWidget(self.step_title)
        
        self.step_desc = QLabel()
        self.step_desc.setObjectName("StepDesc")
        self.step_desc.setWordWrap(True)
        content_layout.addWidget(self.step_desc)
        content_layout.addStretch()
        
        btn_layout = QHBoxLayout()
        self.prev_btn = QPushButton("Previous")
        self.prev_btn.setProperty("class", "WizardBtn")
        self.prev_btn.clicked.connect(self.prev_step)
        
        self.next_btn = QPushButton("Next")
        self.next_btn.setProperty("class", "WizardBtn")
        self.next_btn.clicked.connect(self.next_step)
        
        btn_layout.addWidget(self.prev_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.next_btn)
        content_layout.addLayout(btn_layout)
        
        layout.addWidget(content_widget)
        
        self.steps = [
            {
                "title": "Step 1: Disable Memory Integrity",
                "desc": "Windows 11 blocks the RyzenAdj driver (inpoutx64.sys) by default. You MUST disable 'Memory Integrity' (Core Isolation) in Windows Settings and restart your PC for CPU Control to work."
            },
            {
                "title": "Step 2: Close Other Tuning Apps",
                "desc": "Apps like UXTU, Ryzen Controller, or AATU will compete for hardware access and cause silent driver crashes (like PawnIO.sys). Please close them completely before applying HELXAIL settings."
            },
            {
                "title": "Step 3: Install Background Service",
                "desc": "Click the Settings (?) icon on the top right, then click 'Install Service'. This unlocks the 'Zero-UAC' feature, allowing HELXAIL to adjust your CPU wattage automatically in the background without annoying Yes/No popups!"
            }
        ]
        self.current_step = 0
        self.update_ui()
        
        self._is_dragging = False
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(200)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    def update_ui(self):
        step = self.steps[self.current_step]
        self.step_title.setText(step["title"])
        self.step_desc.setText(step["desc"])
        self.title_label.setText(f"HELXAIL Guide ({self.current_step + 1}/{len(self.steps)})")
        
        self.prev_btn.setEnabled(self.current_step > 0)
        if self.current_step == len(self.steps) - 1:
            self.next_btn.setText("Finish")
        else:
            self.next_btn.setText("Next")
            
        self.prev_btn.style().unpolish(self.prev_btn)
        self.prev_btn.style().polish(self.prev_btn)

    def next_step(self):
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            self.update_ui()
        else:
            self.close_panel()
            
    def prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self.update_ui()

    def showEvent(self, event):
        super().showEvent(event)
        self.anim.start()

    def close_panel(self):
        from PySide6.QtCore import QPropertyAnimation
        self.anim.setDirection(QPropertyAnimation.Backward)
        self.anim.finished.connect(self.deleteLater)
        self.anim.start()

    def mousePressEvent(self, event):
        from PySide6.QtCore import Qt
        if event.button() == Qt.LeftButton and self.title_bar.geometry().contains(event.pos()):
            self._is_dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        from PySide6.QtCore import Qt, QPoint
        if self._is_dragging and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            if self.parent():
                parent_rect = self.parent().rect()
                new_x = max(0, min(new_pos.x(), parent_rect.width() - self.width()))
                new_y = max(0, min(new_pos.y(), parent_rect.height() - self.height()))
                new_pos = QPoint(new_x, new_y)
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        from PySide6.QtCore import Qt
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            event.accept()
