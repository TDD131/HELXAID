import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog

from VideoPlayerWidget import VideoPlayerWidget


def main():
    app = QApplication(sys.argv)

    w = VideoPlayerWidget()
    w.resize(1100, 620)
    w.setWindowTitle("Video Subtitle Overlay Test")
    w.show()

    video_path, _ = QFileDialog.getOpenFileName(
        w,
        "Pick a video file",
        "",
        "Video Files (*.mp4 *.mkv *.webm *.avi *.mov);;All Files (*.*)",
    )
    if not video_path:
        return 0

    w.play_file(video_path)

    def force_overlay_text():
        w.subtitle_label.setText("OVERLAY TEST\nIf you can read this, overlay works")
        w.subtitle_label.setVisible(True)
        w.subtitle_label.raise_()

    QTimer.singleShot(1200, force_overlay_text)

    def pick_subtitle_file():
        sub_path, _ = QFileDialog.getOpenFileName(
            w,
            "Pick a subtitle file (optional)",
            os.path.dirname(video_path),
            "Subtitles (*.srt *.vtt *.ass *.ssa);;All Files (*.*)",
        )
        if sub_path:
            w.set_subtitle_file(sub_path)

    QTimer.singleShot(2500, pick_subtitle_file)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
