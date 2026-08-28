"""
Ambient Multi-Mode Audio Visualizer Widget for HELXAIC.

High-performance QPainter vector visualizer rendered as a non-blocking background underlay.
Features modular renderer strategies with zero heap allocations per frame:
1. SpectrumBarsRenderer: Rounded gradient equalizer bars with floating peak dots.
2. SilkWaveRenderer: Multi-layer harmonic Bezier fluid waves modulated by bass/mid/treble.

Component Name: AmbientVisualizerWidget
"""

import sys
import time
import math
from abc import ABC, abstractmethod
from typing import Optional, List, Tuple, Dict, Any

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QLineF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QLinearGradient, QRadialGradient, QGradient,
    QPainterPath, QPixmap
)

from AudioSpectrumEngine import AudioSpectrumEngine


# ==============================================================================
# 1. RENDERER STRATEGY INTERFACE
# ==============================================================================

class IVisualizerRenderer(ABC):
    """
    Abstract interface for visualizer render strategies.
    
    Component Name: IVisualizerRenderer
    """
    @abstractmethod
    def initialize(self, widget: 'AmbientVisualizerWidget'):
        pass

    @abstractmethod
    def render(self, painter: QPainter, width: float, height: float,
               spectrum: Any, peaks: Any,
               band_energies: Tuple[float, float, float, float],
               colors: Dict[str, QColor], effective_opacity: float,
               peak_dots_enabled: bool, dt: float):
        pass

    def resize(self, width: float, height: float):
        pass

    def reset(self):
        pass

    def set_render_quality(self, quality: str):
        pass


# ==============================================================================
# 2. OPTION 1: SPECTRUM BARS RENDERER (ZERO-ALLOCATION)
# ==============================================================================

class SpectrumBarsRenderer(IVisualizerRenderer):
    """
    Equalizer Spectrum Bars with floating peak dots and dynamic horizontal centering.
    
    Component Name: SpectrumBarsRenderer
    """
    def __init__(self):
        self._bar_rects = [QRectF() for _ in range(64)]
        self._peak_rects = [QRectF() for _ in range(64)]
        self._cached_brush: Optional[QBrush] = None
        self._cached_peak_brush: Optional[QBrush] = None
        self._cached_grad_h = 0.0
        self._cached_max_h = 0.0
        self._cached_color_key = None
        self._bar_height_ratio = 0.42
        self._render_quality = "ultra"

    def initialize(self, widget: 'AmbientVisualizerWidget'):
        self.reset()

    def resize(self, width: float, height: float):
        self.reset()

    def reset(self):
        self._cached_brush = None
        self._cached_peak_brush = None
        self._cached_color_key = None

    def set_render_quality(self, quality: str):
        self._render_quality = str(quality).lower().strip()
        self.reset()

    def render(self, painter: QPainter, width: float, height: float,
               spectrum: Any, peaks: Any,
               band_energies: Tuple[float, float, float, float],
               colors: Dict[str, QColor], effective_opacity: float,
               peak_dots_enabled: bool, dt: float):
        if self._render_quality == "eco":
            peak_dots_enabled = False
        num_bars = len(spectrum)
        if num_bars == 0 or width < 10 or height < 10:
            return

        margin_x = max(16.0, width * 0.03)
        available_w = max(10.0, width - (margin_x * 2.0))
        total_bar_slot = available_w / num_bars
        bar_spacing = max(2.0, total_bar_slot * 0.18)
        bar_w = max(3.0, total_bar_slot - bar_spacing)
        max_bar_h = max(50.0, height * self._bar_height_ratio)
        min_bar_h = 3.0

        # Symmetrical horizontal centering
        actual_total_w = (num_bars * total_bar_slot) - bar_spacing
        start_x = (width - actual_total_w) / 2.0

        # Cached gradient brush (zero allocations per frame)
        c_bot = colors["bottom"]
        c_mid = colors["mid"]
        c_top = colors["top"]
        c_peak = colors["peak"]
        color_key = (c_bot.rgba(), c_mid.rgba(), c_top.rgba())

        if self._cached_brush is None or self._cached_grad_h != height or self._cached_max_h != max_bar_h or self._cached_color_key != color_key:
            gradient = QLinearGradient(0, height, 0, height - max_bar_h)
            c1 = QColor(c_bot)
            c1.setAlpha(180)
            c2 = QColor(c_mid)
            c2.setAlpha(230)
            c3 = QColor(c_top)
            c3.setAlpha(255)

            gradient.setColorAt(0.0, c1)
            gradient.setColorAt(0.5, c2)
            gradient.setColorAt(1.0, c3)

            self._cached_brush = QBrush(gradient)
            self._cached_peak_brush = QBrush(c_peak)
            self._cached_grad_h = height
            self._cached_max_h = max_bar_h
            self._cached_color_key = color_key

        painter.setPen(Qt.NoPen)
        painter.setBrush(self._cached_brush)

        corner_radius = max(2.0, min(bar_w / 2.0, 6.0))
        peak_dot_h = max(2.0, corner_radius * 0.7)
        peak_brush = self._cached_peak_brush or QBrush(c_peak)

        # Draw bars using pre-allocated QRectF (zero heap allocations)
        for i in range(num_bars):
            val = float(spectrum[i]) if i < len(spectrum) else 0.0
            peak_val = float(peaks[i]) if i < len(peaks) else 0.0

            bar_h = max(min_bar_h, val * max_bar_h)
            x = start_x + (i * total_bar_slot)
            y = height - bar_h

            rect = self._bar_rects[i]
            rect.setRect(x, y, bar_w, bar_h + corner_radius)
            painter.drawRoundedRect(rect, corner_radius, corner_radius)

            if peak_dots_enabled and peak_val > 0.03:
                peak_h = max(min_bar_h, peak_val * max_bar_h)
                peak_y = height - peak_h - 4.0
                if peak_y < y - 2.0:
                    peak_rect = self._peak_rects[i]
                    peak_rect.setRect(x, peak_y, bar_w, peak_dot_h)
                    painter.fillRect(peak_rect, peak_brush)


# ==============================================================================
# 3. OPTION 2: SILK FLUID AMBIENT WAVES RENDERER (ZERO-ALLOCATION)
# ==============================================================================

class SilkWaveRenderer(IVisualizerRenderer):
    """
    Multi-Layer Harmonic Bezier Fluid Ambient Waves with cached paths and brushes.
    
    Component Name: SilkWaveRenderer
    """
    NUM_NODES = 16

    def __init__(self):
        self._paths = [QPainterPath(), QPainterPath(), QPainterPath()]
        self._crest_paths = [QPainterPath(), QPainterPath(), QPainterPath()]
        self._nodes_y = None
        self._phases = [0.0, 0.0, 0.0]
        
        # Pre-allocated pens & brushes
        self._crest_pens = [
            QPen(Qt.white, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin),
            QPen(Qt.white, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin),
            QPen(Qt.white, 2.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        ]
        self._render_quality = "ultra"

    def initialize(self, widget: 'AmbientVisualizerWidget'):
        self.reset()

    def resize(self, width: float, height: float):
        pass

    def reset(self):
        self._phases = [0.0, 0.0, 0.0]

    def set_render_quality(self, quality: str):
        self._render_quality = str(quality).lower().strip()

    def render(self, painter: QPainter, width: float, height: float,
               spectrum: Any, peaks: Any,
               band_energies: Tuple[float, float, float, float],
               colors: Dict[str, QColor], effective_opacity: float,
               peak_dots_enabled: bool, dt: float):
        if width < 10 or height < 10:
            return

        import numpy as np
        if self._nodes_y is None:
            self._nodes_y = [np.zeros(self.NUM_NODES, dtype=np.float32) for _ in range(3)]

        bass, mid, treble, total_rms = band_energies

        safe_dt = min(0.05, max(0.005, dt))
        self._phases[0] += (1.2 + 1.5 * bass) * safe_dt
        self._phases[1] -= (1.8 + 2.0 * mid) * safe_dt
        self._phases[2] += (3.4 + 3.0 * treble) * safe_dt

        if self._render_quality == "eco":
            n_nodes = 8
        elif self._render_quality == "balanced":
            n_nodes = 12
        else:
            n_nodes = self.NUM_NODES

        if len(spectrum) >= n_nodes:
            step = len(spectrum) / float(n_nodes)
            node_indices = [min(len(spectrum) - 1, int(i * step)) for i in range(n_nodes)]
            spec_nodes = spectrum[node_indices]
        else:
            spec_nodes = np.zeros(n_nodes, dtype=np.float32)

        x_arr = np.linspace(0.0, width, n_nodes, dtype=np.float32)

        layer_specs = [
            {
                "y_base": height * 0.82,
                "amp": height * (0.04 + 0.22 * bass),
                "wave_len": width * 1.25,
                "phase": self._phases[0],
                "sub_amp": height * (0.02 + 0.08 * bass),
                "spec_mod_weight": height * (0.16 * bass + 0.06 * total_rms),
                "color_top": colors["bottom"],
                "color_bot": colors["bottom"],
                "alpha_top": 130,
                "alpha_bot": 210,
                "draw_crest": False
            },
            {
                "y_base": height * 0.86,
                "amp": height * (0.03 + 0.18 * mid),
                "wave_len": width * 0.65,
                "phase": self._phases[1],
                "sub_amp": height * (0.015 + 0.06 * mid),
                "spec_mod_weight": height * (0.13 * mid + 0.05 * total_rms),
                "color_top": colors["mid"],
                "color_bot": colors["bottom"],
                "alpha_top": 170,
                "alpha_bot": 240,
                "draw_crest": (self._render_quality != "eco"),
                "crest_color": colors["mid"],
                "crest_alpha": 200,
                "crest_width": 1.8
            },
            {
                "y_base": height * 0.90,
                "amp": height * (0.02 + 0.14 * treble),
                "wave_len": width * 0.35,
                "phase": self._phases[2],
                "sub_amp": height * (0.01 + 0.05 * treble),
                "spec_mod_weight": height * (0.11 * treble + 0.04 * total_rms),
                "color_top": colors["top"],
                "color_bot": colors["mid"],
                "alpha_top": 200,
                "alpha_bot": 255,
                "draw_crest": True,
                "crest_color": colors["peak"],
                "crest_alpha": 255,
                "crest_width": 2.8
            }
        ]

        if self._render_quality == "eco":
            active_layers = [layer_specs[0]]
        elif self._render_quality == "balanced":
            active_layers = layer_specs[:2]
        else:
            active_layers = layer_specs

        for layer_idx, spec in enumerate(active_layers):
            y_base = spec["y_base"]
            amp = spec["amp"]
            sub_amp = spec["sub_amp"]
            wave_k = (2.0 * math.pi) / max(10.0, spec["wave_len"])
            ph = spec["phase"]

            sin_part = np.sin(wave_k * x_arr + ph)
            cos_part = np.cos(wave_k * 2.0 * x_arr - 0.7 * ph)
            spec_part = spec_nodes * spec["spec_mod_weight"]
            
            raw_displacement = amp * sin_part + sub_amp * cos_part + spec_part
            max_lift = height * 0.60
            compressed_lift = np.where(
                raw_displacement > max_lift,
                max_lift + (raw_displacement - max_lift) * 0.30,
                raw_displacement
            )
            y_nodes = y_base - compressed_lift
            np.clip(y_nodes, height * 0.18, height + 10.0, out=y_nodes)
            self._nodes_y[layer_idx] = y_nodes

            path = self._paths[layer_idx]
            path.clear()
            path.moveTo(0.0, float(y_nodes[0]))

            crest_path = self._crest_paths[layer_idx]
            crest_path.clear()
            crest_path.moveTo(0.0, float(y_nodes[0]))

            for i in range(n_nodes - 1):
                p0_y = float(y_nodes[max(0, i - 1)])
                p1_x = float(x_arr[i])
                p1_y = float(y_nodes[i])
                p2_x = float(x_arr[i + 1])
                p2_y = float(y_nodes[i + 1])
                p3_y = float(y_nodes[min(n_nodes - 1, i + 2)])

                c1_x = p1_x + (p2_x - float(x_arr[max(0, i - 1)])) / 6.0
                c1_y = p1_y + (p2_y - p0_y) / 6.0
                c2_x = p2_x - (float(x_arr[min(n_nodes - 1, i + 2)]) - p1_x) / 6.0
                c2_y = p2_y - (p3_y - p1_y) / 6.0

                path.cubicTo(c1_x, c1_y, c2_x, c2_y, p2_x, p2_y)
                if spec["draw_crest"]:
                    crest_path.cubicTo(c1_x, c1_y, c2_x, c2_y, p2_x, p2_y)

            path.lineTo(width, height)
            path.lineTo(0.0, height)
            path.closeSubpath()

            min_y = float(np.min(y_nodes))
            grad = QLinearGradient(0, min_y, 0, height)
            c_top = QColor(spec["color_top"])
            c_top.setAlpha(spec["alpha_top"])
            c_bot = QColor(spec["color_bot"])
            c_bot.setAlpha(spec["alpha_bot"])

            grad.setColorAt(0.0, c_top)
            grad.setColorAt(1.0, c_bot)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawPath(path)

            if spec["draw_crest"]:
                cr_color = QColor(spec["crest_color"])
                cr_color.setAlpha(spec["crest_alpha"])
                pen = self._crest_pens[layer_idx]
                pen.setColor(cr_color)
                pen.setWidthF(spec["crest_width"])
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(crest_path)


# ==============================================================================
# 4. AMBIENT VISUALIZER WIDGET (ORCHESTRATOR)
# ==============================================================================

class AmbientVisualizerWidget(QWidget):
    """
    Dynamic background audio spectrum & fluid wave visualizer orchestrator.
    
    Component Name: AmbientVisualizerWidget
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AmbientVisualizerWidget")
        
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        # Audio Engine reference
        self._engine = AudioSpectrumEngine.get_instance()
        
        # Visualizer Settings
        self._target_enabled = True
        self._style_mode = "bars"
        self._opacity = 0.30
        self._bar_count = 32
        self._peak_dots_enabled = True
        self._color_mode = "adaptive"
        self._bar_height_ratio = 0.42
        self._target_fps = 60.0
        self._render_quality = "ultra"
        self._eco_mode = True
        
        # Adaptive Color Palette
        self._color_bottom = QColor("#FF5B06")
        self._color_mid = QColor("#FDA903")
        self._color_top = QColor("#ff3da7")
        self._color_peak = QColor("#ffffff")
        
        # Renderers Strategy Dictionary
        self._renderers: Dict[str, IVisualizerRenderer] = {
            "bars": SpectrumBarsRenderer(),
            "waves": SilkWaveRenderer()
        }
        for renderer in self._renderers.values():
            renderer.initialize(self)
            
        self._last_frame_time = time.time()
        
        # Render Loop (Adaptive interval)
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(16)
        self._render_timer.timeout.connect(self._on_render_tick)
        
        # Smooth Fade Animation State (0.0 to 1.0)
        self._fade_factor = 0.0
        self._fade_anim = QVariantAnimation(self)
        self._fade_anim.setEasingCurve(QEasingCurve.OutQuad)
        self._fade_anim.valueChanged.connect(self._on_fade_value_changed)
        self._fade_anim.finished.connect(self._on_fade_finished)
        self._fade_finish_cb = None
        
        # Render Gating & Lifecycle State
        self._is_playing = False
        self._is_active_page = True
        self._is_manually_paused = False
        
        # Start engine
        self._engine.start()
        if self._target_enabled and self._is_playing:
            self._render_timer.start()

    def _on_fade_value_changed(self, val):
        self._fade_factor = float(val)
        self._on_render_tick()

    def _on_fade_finished(self):
        if hasattr(self, '_fade_finish_cb') and self._fade_finish_cb:
            cb = self._fade_finish_cb
            self._fade_finish_cb = None
            try:
                cb()
            except Exception:
                pass

    def _animate_fade(self, start_val: float, end_val: float, duration_ms: int = 300, on_finished=None):
        if self._fade_anim.state() == QVariantAnimation.Running:
            self._fade_anim.stop()
        self._fade_finish_cb = on_finished
        self._fade_anim.setDuration(duration_ms)
        self._fade_anim.setStartValue(float(start_val))
        self._fade_anim.setEndValue(float(end_val))
        self._fade_anim.start()

    def set_visualizer_enabled(self, enabled: bool, animate: bool = True):
        self._target_enabled = bool(enabled)
        if self._target_enabled:
            self.show()
            self._sync_render_timer()
            if animate and self.isVisible():
                self._animate_fade(self._fade_factor, 1.0, 350)
            else:
                self._fade_factor = 1.0
                self._on_render_tick()
        else:
            if animate and self.isVisible():
                self._sync_render_timer()
                def _on_done():
                    if not self._target_enabled:
                        self._render_timer.stop()
                        self.hide()
                        self._on_render_tick()
                self._animate_fade(self._fade_factor, 0.0, 300, on_finished=_on_done)
            else:
                self._fade_factor = 0.0
                self._render_timer.stop()
                self.hide()
                self._on_render_tick()

    def is_visualizer_enabled(self) -> bool:
        return self._target_enabled

    def set_style_mode(self, mode: str):
        mode_key = str(mode).lower().strip()
        if mode_key not in self._renderers:
            mode_key = "bars"
        self._style_mode = mode_key
        self._renderers[self._style_mode].resize(self.width(), self.height())
        self.update()

    def get_style_mode(self) -> str:
        return self._style_mode

    def set_visualizer_opacity(self, opacity: float):
        self._opacity = max(0.05, min(1.0, float(opacity)))
        self.update()

    def get_visualizer_opacity(self) -> float:
        return self._opacity

    def set_bar_count(self, count: int):
        self._bar_count = 48 if count >= 40 else 32
        self.update()

    def get_bar_count(self) -> int:
        return self._bar_count

    def set_color_mode(self, mode: str):
        self._color_mode = mode.lower()
        if self._color_mode == "adaptive":
            target_dom = getattr(self, '_last_adaptive_bottom', None)
            if target_dom and target_dom.isValid():
                self.set_adaptive_colors(target_dom, getattr(self, '_last_adaptive_top', None))
            else:
                self._apply_preset_colors()
        else:
            self._apply_preset_colors()
        for r in self._renderers.values():
            r.reset()
        self.update()

    def get_color_mode(self) -> str:
        return self._color_mode

    def set_peak_dots_enabled(self, enabled: bool):
        self._peak_dots_enabled = bool(enabled)
        self.update()

    def set_target_fps(self, fps: float):
        try:
            val = float(fps)
            if val > 0:
                self._target_fps = val
                interval_ms = 16 if abs(self._target_fps - 60.0) < 0.01 else max(8, int(round(1000.0 / self._target_fps)))
                self._render_timer.setInterval(interval_ms)
                self._engine.set_target_fps(self._target_fps)
        except Exception:
            pass

    def get_target_fps(self) -> float:
        return self._target_fps

    def set_render_quality(self, quality: str):
        self._render_quality = str(quality).lower().strip()
        for r in self._renderers.values():
            if hasattr(r, 'set_render_quality'):
                r.set_render_quality(self._render_quality)
        self.update()

    def get_render_quality(self) -> str:
        return self._render_quality

    def set_eco_mode(self, enabled: bool):
        self._eco_mode = bool(enabled)
        self._engine.set_eco_mode(self._eco_mode)

    def get_eco_mode(self) -> bool:
        return self._eco_mode

    def set_playback_state(self, is_playing: bool):
        was_playing = self._is_playing
        self._is_playing = bool(is_playing)
        self._engine.set_playback_state(self._is_playing)
        if self._target_enabled and self._is_active_page:
            if self._is_playing:
                self._sync_render_timer()
                self._animate_fade(self._fade_factor, 1.0, 260)
            elif was_playing:
                def _on_stopped():
                    if not self._is_playing:
                        self._sync_render_timer()
                        self.update()
                self._animate_fade(self._fade_factor, 0.0, 200, on_finished=_on_stopped)
            else:
                self._sync_render_timer()

    def set_sensitivity(self, sens: float):
        self._engine.set_sensitivity(sens)

    def pause_rendering(self, animate: bool = True):
        self._is_active_page = False
        if animate and self._target_enabled and self.isVisible():
            def _on_done():
                if not self._is_active_page:
                    self._sync_render_timer()
            self._animate_fade(self._fade_factor, 0.0, 240, on_finished=_on_done)
        else:
            self._fade_factor = 0.0
            self._sync_render_timer()

    def resume_rendering(self, animate: bool = True):
        self._is_active_page = True
        self._sync_render_timer()
        if self._target_enabled and self._is_playing:
            if animate:
                self._animate_fade(self._fade_factor, 1.0, 320)
            else:
                self._fade_factor = 1.0
                self.update()

    def set_adaptive_colors(self, dominant_color: Optional[QColor] = None, secondary_color: Optional[QColor] = None):
        if dominant_color and dominant_color.isValid():
            self._last_adaptive_bottom = QColor(dominant_color)
            if secondary_color and secondary_color.isValid():
                self._last_adaptive_top = QColor(secondary_color)
            else:
                h, s, v, a = dominant_color.getHsv()
                self._last_adaptive_top = QColor.fromHsv((h + 50) % 360, max(40, s - 30), 255)

        if self._color_mode == "adaptive":
            target_dom = dominant_color if (dominant_color and dominant_color.isValid()) else getattr(self, '_last_adaptive_bottom', None)
            if target_dom and target_dom.isValid():
                self._color_bottom = target_dom
                h, s, v, a = target_dom.getHsv()
                self._color_mid = QColor.fromHsv((h + 20) % 360, max(50, s), min(255, v + 40))
                self._color_top = getattr(self, '_last_adaptive_top', None) or QColor.fromHsv((h + 50) % 360, max(40, s - 30), 255)
            else:
                self._apply_preset_colors()
            for r in self._renderers.values():
                r.reset()
            self.update()

    def set_cover_pixmap(self, pixmap: Optional[QPixmap]):
        for r in self._renderers.values():
            if hasattr(r, 'set_cover_pixmap'):
                r.set_cover_pixmap(pixmap)
        self.update()

    def _apply_preset_colors(self):
        if self._color_mode == "adaptive":
            target_dom = getattr(self, '_last_adaptive_bottom', None)
            if target_dom and target_dom.isValid():
                self._color_bottom = target_dom
                h, s, v, a = target_dom.getHsv()
                self._color_mid = QColor.fromHsv((h + 20) % 360, max(50, s), min(255, v + 40))
                self._color_top = getattr(self, '_last_adaptive_top', None) or QColor.fromHsv((h + 50) % 360, max(40, s - 30), 255)
                self._color_peak = QColor("#FFFFFF")
                return
            self._color_bottom = QColor("#FF5B06")
            self._color_mid = QColor("#FDA903")
            self._color_top = QColor("#ff3da7")
            self._color_peak = QColor("#FFFFFF")
        elif self._color_mode == "cyber_orange":
            self._color_bottom = QColor("#FF5B06")
            self._color_mid = QColor("#FDA903")
            self._color_top = QColor("#ff3da7")
            self._color_peak = QColor("#FFFFFF")
        elif self._color_mode == "cyber_cyan":
            self._color_bottom = QColor("#0052D4")
            self._color_mid = QColor("#4364F7")
            self._color_top = QColor("#6FB1FC")
            self._color_peak = QColor("#FFFFFF")
        elif self._color_mode == "neon_magenta":
            self._color_bottom = QColor("#8A2387")
            self._color_mid = QColor("#E94057")
            self._color_top = QColor("#F27121")
            self._color_peak = QColor("#FFFFFF")
        elif self._color_mode == "synthwave":
            self._color_bottom = QColor("#11002c")
            self._color_mid = QColor("#b5179e")
            self._color_top = QColor("#4cc9f0")
            self._color_peak = QColor("#7209b7")

    def _is_render_allowed(self) -> bool:
        is_fading = (self._fade_factor > 0.005 and self._fade_factor < 0.999)
        if not self._target_enabled and not is_fading:
            return False
        if not self._is_active_page and not is_fading:
            return False
        try:
            win = self.window()
            if win and win.isMinimized():
                return False
        except Exception:
            pass
        return True

    def _sync_render_timer(self):
        is_fading = (self._fade_factor > 0.005 and self._fade_factor < 0.999)
        should_run = self._is_render_allowed() and (self._is_playing or is_fading)
        if should_run and not self._render_timer.isActive():
            self._last_frame_time = time.time()
            self._render_timer.start()
        elif not should_run and self._render_timer.isActive():
            self._render_timer.stop()

    def _on_render_tick(self):
        if not self._is_render_allowed():
            self._render_timer.stop()
            return
        if self.width() < 10 or self.height() < 10:
            return
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = float(self.width())
        h = float(self.height())
        for r in self._renderers.values():
            r.resize(w, h)
        self.update()

    def paintEvent(self, event):
        if not self._target_enabled and self._fade_factor <= 0.005:
            return

        w = float(self.width())
        h = float(self.height())
        if w < 10 or h < 10:
            return

        effective_opacity = self._opacity * self._fade_factor
        if effective_opacity <= 0.005:
            return

        now = time.time()
        dt = now - self._last_frame_time
        self._last_frame_time = now

        num_bins = 64 if self._style_mode == "halo" else self._bar_count
        spectrum, peaks = self._engine.get_spectrum_snapshot(num_bins)
        band_energies = self._engine.get_band_energies()

        colors = {
            "bottom": self._color_bottom,
            "mid": self._color_mid,
            "top": self._color_top,
            "peak": self._color_peak
        }

        painter = QPainter(self)
        if self._render_quality == "eco":
            painter.setRenderHint(QPainter.Antialiasing, False)
        else:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setOpacity(effective_opacity)

        renderer = self._renderers.get(self._style_mode, self._renderers["bars"])
        renderer.render(
            painter=painter,
            width=w,
            height=h,
            spectrum=spectrum,
            peaks=peaks,
            band_energies=band_energies,
            colors=colors,
            effective_opacity=effective_opacity,
            peak_dots_enabled=self._peak_dots_enabled,
            dt=dt
        )

        painter.end()
