#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
 IoT-Ready Structural Health Monitoring (SHM) Dashboard
=============================================================================
 Project     : IoT-Ready Structural Health Monitoring System Using MPU6050
               for Real-Time Tilt Detection
 Hardware    : Arduino Nano + MPU6050 + Red LED + Active Buzzer  (PROTOTYPE)
 Future      : ESP32 + WiFi + MQTT + Firebase + Cloud Dashboard + Mobile App
 Stack       : Python 3.11+, PySide6, PyQtGraph, PySerial
 Author      : Senior Embedded / IoT / Python Architecture Team
 Version     : 1.0.0

 DESCRIPTION
 -----------
 A production-style industrial SCADA-grade desktop dashboard that visualises
 real-time structural tilt data streamed from an Arduino Nano running an
 MPU6050 IMU. The application classifies structural risk into SAFE /
 WARNING / DANGER bands, animates a 2D building model, plots live roll/pitch
 telemetry, logs events, raises local alarms, and clearly documents the
 future migration path to an ESP32-based IoT/cloud architecture.

 This program is intentionally contained in a SINGLE FILE as requested,
 but is internally organised into clearly separated, documented, reusable
 classes (Serial I/O, Gauges, Building animation, Graphing, Event Log,
 Alarm Manager, Theming, Cards, Dialogs, Main Window) to keep the codebase
 maintainable and production-quality despite the single-file constraint.

 ARDUINO SERIAL CONTRACT (1 line every 100 ms, CSV, '\n' terminated):
     roll,pitch,temperature,maxTilt,status,alerts
 Example:
     15.23,4.15,31.5,18.7,WARNING,3

 NOTE: This is a structural TILT MONITORING & EARLY WARNING system.
       It is NOT a building-collapse prediction system.
=============================================================================
"""

from __future__ import annotations

import csv
import math
import os
import random
import sys
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Deque, Optional

try:
    import psutil  # optional - for memory usage telemetry
    _HAS_PSUTIL = True
except Exception:
    _HAS_PSUTIL = False

import serial
import serial.tools.list_ports as list_ports

import pyqtgraph as pg
from PySide6.QtCore import (
    Property, QAbstractAnimation, QEasingCurve, QObject, QPointF, QPropertyAnimation,
    QRectF, QSize, Qt, QThread, QTimer, Signal, Slot, QSequentialAnimationGroup
)
from PySide6.QtGui import (
    QAction, QBrush, QColor, QFont, QFontDatabase, QIcon, QLinearGradient,
    QPainter, QPainterPath, QPalette, QPen, QPixmap, QPolygonF, QRadialGradient,
    QTransform
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QGraphicsDropShadowEffect, QGraphicsObject, QGraphicsScene, QGraphicsView,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMenuBar, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QSplashScreen, QStatusBar, QStyle,
    QStyleFactory, QTabWidget, QToolBar, QVBoxLayout, QWidget
)

# =============================================================================
# SECTION 1 :: GLOBAL CONSTANTS, THEME & UTILITIES
# =============================================================================

APP_NAME = "Structural Health Monitor (SHM) — IoT Tilt Sentinel"
APP_VERSION = "1.0.0"
ORG_NAME = "SHM Embedded Systems Lab"

SAMPLE_INTERVAL_MS = 100                       # Arduino sends 1 line / 100ms
GRAPH_WINDOW_SECONDS = 60
MAX_GRAPH_POINTS = (GRAPH_WINDOW_SECONDS * 1000) // SAMPLE_INTERVAL_MS

TILT_WARNING_DEG = 10.0
TILT_DANGER_DEG = 20.0
RISK_DENOMINATOR_DEG = 45.0

DEFAULT_BAUD = 9600
BAUD_RATES = [9600, 19200, 38400, 57600, 115200]


class Theme:
    """Centralised colour palette & QSS stylesheet for the dark industrial theme."""

    BG_0 = "#0a0e14"          # window background
    BG_1 = "#0f1521"          # panel background
    BG_2 = "#151c2c"          # card background
    BG_GLASS = "rgba(255,255,255,12)"
    BORDER = "#23304a"
    ACCENT = "#00d4ff"
    ACCENT_2 = "#7c5cff"
    TEXT = "#e8edf7"
    TEXT_MUTED = "#8593b8"
    SAFE = "#1fdb6d"
    WARNING = "#ffc83d"
    DANGER = "#ff3b5c"
    SAFE_BG = "rgba(31,219,109,28)"
    WARNING_BG = "rgba(255,200,61,28)"
    DANGER_BG = "rgba(255,59,92,28)"

    FONT_FAMILY = "Segoe UI"

    @staticmethod
    def color_for_status(status: "TiltStatus") -> str:
        return {
            TiltStatus.SAFE: Theme.SAFE,
            TiltStatus.WARNING: Theme.WARNING,
            TiltStatus.DANGER: Theme.DANGER,
        }[status]

    @staticmethod
    def stylesheet() -> str:
        return f"""
        * {{
            font-family: '{Theme.FONT_FAMILY}';
            color: {Theme.TEXT};
        }}
        QMainWindow, QDialog {{
            background-color: {Theme.BG_0};
        }}
        QWidget#HeaderBar {{
            background-color: {Theme.BG_1};
            border-bottom: 1px solid {Theme.BORDER};
        }}
        QFrame.Card {{
            background-color: {Theme.BG_2};
            border: 1px solid {Theme.BORDER};
            border-radius: 14px;
        }}
        QFrame.Panel {{
            background-color: {Theme.BG_1};
            border: 1px solid {Theme.BORDER};
            border-radius: 16px;
        }}
        QLabel.CardTitle {{
            color: {Theme.TEXT_MUTED};
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 1px;
        }}
        QLabel.CardValue {{
            color: {Theme.TEXT};
            font-size: 26px;
            font-weight: 700;
        }}
        QLabel.SectionTitle {{
            color: {Theme.ACCENT};
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 1px;
            padding: 4px 0px;
        }}
        QPushButton {{
            background-color: {Theme.BG_2};
            border: 1px solid {Theme.BORDER};
            border-radius: 8px;
            padding: 7px 14px;
            color: {Theme.TEXT};
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {Theme.ACCENT};
            color: #04141c;
            border-color: {Theme.ACCENT};
        }}
        QPushButton:pressed {{
            background-color: {Theme.ACCENT_2};
        }}
        QComboBox, QSpinBox {{
            background-color: {Theme.BG_2};
            border: 1px solid {Theme.BORDER};
            border-radius: 6px;
            padding: 4px 8px;
            min-height: 22px;
        }}
        QListWidget {{
            background-color: {Theme.BG_1};
            border: 1px solid {Theme.BORDER};
            border-radius: 10px;
            padding: 4px;
        }}
        QProgressBar {{
            background-color: {Theme.BG_1};
            border: 1px solid {Theme.BORDER};
            border-radius: 8px;
            text-align: center;
            color: {Theme.TEXT};
            font-weight: 700;
            height: 18px;
        }}
        QProgressBar::chunk {{
            border-radius: 8px;
        }}
        QStatusBar {{
            background-color: {Theme.BG_1};
            border-top: 1px solid {Theme.BORDER};
            color: {Theme.TEXT_MUTED};
        }}
        QToolBar {{
            background-color: {Theme.BG_1};
            border-bottom: 1px solid {Theme.BORDER};
            spacing: 6px;
            padding: 4px;
        }}
        QMenuBar {{
            background-color: {Theme.BG_1};
            color: {Theme.TEXT};
        }}
        QMenuBar::item:selected {{
            background-color: {Theme.ACCENT};
            color: #04141c;
        }}
        QMenu {{
            background-color: {Theme.BG_2};
            border: 1px solid {Theme.BORDER};
            color: {Theme.TEXT};
        }}
        QMenu::item:selected {{
            background-color: {Theme.ACCENT};
            color: #04141c;
        }}
        QScrollArea {{
            border: none;
            background: transparent;
        }}
        QTabWidget::pane {{
            border: 1px solid {Theme.BORDER};
            border-radius: 10px;
        }}
        QTabBar::tab {{
            background: {Theme.BG_2};
            padding: 8px 16px;
            border: 1px solid {Theme.BORDER};
            border-bottom: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        }}
        QTabBar::tab:selected {{
            background: {Theme.ACCENT};
            color: #04141c;
        }}
        QGroupBox {{
            border: 1px solid {Theme.BORDER};
            border-radius: 10px;
            margin-top: 10px;
            padding-top: 12px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            color: {Theme.ACCENT};
        }}
        """


class TiltStatus(Enum):
    """Structural risk classification bands."""
    SAFE = "SAFE"
    WARNING = "WARNING"
    DANGER = "DANGER"

    @staticmethod
    def classify(tilt_deg: float) -> "TiltStatus":
        """Classify an absolute tilt magnitude (deg) into a risk band."""
        mag = abs(tilt_deg)
        if mag >= TILT_DANGER_DEG:
            return TiltStatus.DANGER
        if mag >= TILT_WARNING_DEG:
            return TiltStatus.WARNING
        return TiltStatus.SAFE

    @staticmethod
    def from_string(s: str) -> "TiltStatus":
        try:
            return TiltStatus(s.strip().upper())
        except Exception:
            return TiltStatus.SAFE


def compute_risk(max_tilt_deg: float) -> float:
    """Risk(%) = min((maxTilt / 45) * 100, 100)."""
    return min((abs(max_tilt_deg) / RISK_DENOMINATOR_DEG) * 100.0, 100.0)


def compute_health(risk_pct: float) -> float:
    """Structural Health(%) = 100 - Risk."""
    return max(0.0, 100.0 - risk_pct)


def add_drop_shadow(widget: QWidget, blur: int = 28, alpha: int = 140,
                     color: str = "#000000", dx: int = 0, dy: int = 6) -> None:
    """Attach a professional drop-shadow effect to any widget."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    qc = QColor(color)
    qc.setAlpha(alpha)
    shadow.setColor(qc)
    shadow.setOffset(dx, dy)
    widget.setGraphicsEffect(shadow)


@dataclass
class TelemetryFrame:
    """One parsed sample from the Arduino serial stream."""
    roll: float = 0.0
    pitch: float = 0.0
    temperature: float = 0.0
    max_tilt: float = 0.0
    status: TiltStatus = TiltStatus.SAFE
    alerts: int = 0
    timestamp: float = field(default_factory=time.time)


# =============================================================================
# SECTION 2 :: SERIAL MANAGER (Background Thread, Auto-Detect, Auto-Reconnect)
# =============================================================================

class SerialManager(QThread):
    """
    Background worker thread responsible for all Arduino communication.

    Responsibilities
    -----------------
    * Auto-detect a connected Arduino (or use a user-selected COM port).
    * Continuously read CSV telemetry lines without blocking the GUI thread.
    * Gracefully ignore malformed / corrupted packets (never crash).
    * Automatically attempt reconnection if the link drops.
    * Fall back to an on-board SIMULATION MODE generator when no hardware
      is present, so the dashboard remains fully demonstrable.

    Signals
    -------
    frameReceived(TelemetryFrame) : a successfully parsed telemetry sample
    connectionStateChanged(str)   : "CONNECTED" | "DISCONNECTED" | "RECONNECTING" | "SIMULATION"
    portInfoChanged(str, int)     : (port_name, baud_rate)
    """

    frameReceived = Signal(object)
    connectionStateChanged = Signal(str)
    portInfoChanged = Signal(str, int)

    def __init__(self, baud_rate: int = DEFAULT_BAUD, port: Optional[str] = None,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self._baud = baud_rate
        self._requested_port = port
        self._running = True
        self._simulate = False
        self._ser: Optional[serial.Serial] = None
        self._sim_t = 0.0
        self._sim_phase = 0

    # ---- Public control API -------------------------------------------------
    def set_port(self, port: Optional[str]) -> None:
        """Set a specific port. If we were in simulation, exit it to try this port."""
        self._requested_port = port
        if port is not None:
            self._simulate = False  # exit simulation mode to attempt real connection

    def set_baud(self, baud: int) -> None:
        self._baud = baud

    def stop(self) -> None:
        self._running = False
        self._close_port()
        self.wait(2000)

    # ---- Internal helpers -----------------------------------------------------
    @staticmethod
    def _autodetect_port() -> Optional[str]:
        """Scan available COM ports and guess which one is the Arduino.
        On Linux, Arduino Nano (CH340) typically appears as /dev/ttyUSB0.
        Arduino Uno/Mega (ATmega16U2) appears as /dev/ttyACM0.
        """
        import glob
        candidates = list(list_ports.comports())

        # Priority 1: known Arduino descriptors
        for p in candidates:
            desc = (p.description or "").lower()
            vid_pid = f"{p.vid}:{p.pid}" if p.vid else ""
            if any(k in desc for k in (
                "arduino", "ch340", "ch341", "usb-serial", "usb serial",
                "wch", "ftdi", "cp210", "prolific", "usb2.0-serial", "usb2.0 serial"
            )):
                return p.device

        # Priority 2: on Linux, directly try common Arduino device paths
        linux_patterns = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0", "/dev/ttyACM1"]
        for path in linux_patterns:
            if os.path.exists(path):
                return path

        # Priority 3: any ttyUSB or ttyACM found via glob
        for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
            matches = glob.glob(pattern)
            if matches:
                return sorted(matches)[0]

        # Priority 4: fall back to first listed port
        return candidates[0].device if candidates else None

    def _open_port(self) -> bool:
        port = self._requested_port or self._autodetect_port()
        if not port:
            return False
        try:
            self._ser = serial.Serial(port, self._baud, timeout=1.0)
            self._requested_port = port
            self.portInfoChanged.emit(port, self._baud)
            return True
        except Exception:
            self._ser = None
            return False

    def _close_port(self) -> None:
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except Exception:
            pass
        self._ser = None

    def _parse_line(self, raw: str) -> Optional[TelemetryFrame]:
        """Parse 'roll,pitch,temperature,maxTilt,status,alerts'. Ignore junk."""
        try:
            parts = [p.strip() for p in raw.strip().split(",")]
            if len(parts) != 6:
                return None
            roll, pitch, temp, max_tilt, status_s, alerts = parts
            return TelemetryFrame(
                roll=float(roll),
                pitch=float(pitch),
                temperature=float(temp),
                max_tilt=float(max_tilt),
                status=TiltStatus.from_string(status_s),
                alerts=int(float(alerts)),
            )
        except (ValueError, IndexError):
            return None  # corrupted / malformed packet -> silently ignored

    def _generate_simulated_frame(self) -> TelemetryFrame:
        """Synthesize plausible telemetry when no hardware is connected."""
        self._sim_t += 0.1
        self._sim_phase += 1
        base_roll = 6.0 * math.sin(self._sim_t * 0.35)
        base_pitch = 4.0 * math.sin(self._sim_t * 0.22 + 1.2)
        noise_r = random.uniform(-0.6, 0.6)
        noise_p = random.uniform(-0.6, 0.6)
        # Occasionally inject a simulated excursion into WARNING/DANGER
        if self._sim_phase % 260 == 0:
            base_roll += random.choice([14.0, 22.0, -22.0])
        roll = base_roll + noise_r
        pitch = base_pitch + noise_p
        temp = 30.0 + 2.5 * math.sin(self._sim_t * 0.05) + random.uniform(-0.2, 0.2)
        max_tilt = max(abs(roll), abs(pitch))
        status = TiltStatus.classify(max_tilt)
        return TelemetryFrame(roll, pitch, temp, max_tilt, status, alerts=0)

    # ---- QThread main loop -----------------------------------------------------
    def run(self) -> None:
        last_attempt = 0.0
        last_hw_retry = 0.0       # periodic hardware retry even while simulating
        connected_once = False
        while self._running:
            try:
                if self._simulate:
                    # Even in simulation, retry for real hardware every 5 seconds
                    now = time.time()
                    if now - last_hw_retry >= 5.0:
                        last_hw_retry = now
                        if self._open_port():
                            self._simulate = False
                            connected_once = True
                            self.connectionStateChanged.emit("CONNECTED")
                            continue
                    frame = self._generate_simulated_frame()
                    self.frameReceived.emit(frame)
                    self.msleep(SAMPLE_INTERVAL_MS)
                    continue

                ser = self._ser
                if ser is None or not ser.is_open:
                    now = time.time()
                    if now - last_attempt < 2.0:
                        self.msleep(100)
                        continue
                    last_attempt = now
                    self.connectionStateChanged.emit(
                        "RECONNECTING" if connected_once else "DISCONNECTED")
                    if self._open_port():
                        connected_once = True
                        self.connectionStateChanged.emit("CONNECTED")
                    else:
                        # No hardware found at all -> switch to simulation so the
                        # dashboard stays fully functional for demo purposes.
                        if not connected_once:
                            self._simulate = True
                            self.connectionStateChanged.emit("SIMULATION")
                        continue

                ser = self._ser  # re-read after possible (re)connect
                if ser is None or not self._running:
                    continue
                raw = ser.readline().decode("utf-8", errors="ignore")
                if not raw:
                    continue
                frame = self._parse_line(raw)
                if frame is not None:
                    self.frameReceived.emit(frame)
            except (serial.SerialException, OSError, TypeError, AttributeError):
                # Covers dropped connections, closed file descriptors, and
                # any race between a concurrent stop()/close() and a read.
                self._close_port()
                if self._running:
                    self.connectionStateChanged.emit("RECONNECTING")
            except Exception:
                # Absolute safety net: never let an unexpected error crash
                # the background thread (and therefore the application).
                traceback.print_exc()
                self.msleep(200)
                continue


# =============================================================================
# SECTION 3 :: CIRCULAR GAUGE WIDGET (Roll / Pitch / Risk)
# =============================================================================

class RoundGauge(QWidget):
    """
    A custom-painted circular analogue gauge with an animated needle,
    colour-coded arc zones and a digital readout — used for Roll, Pitch
    and Risk Level visualisation.
    """

    def __init__(self, title: str, unit: str, min_val: float, max_val: float,
                 zones: list[tuple[float, float, str]], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._title = title
        self._unit = unit
        self._min = min_val
        self._max = max_val
        self._zones = zones  # list of (start, end, color_hex) in gauge units
        self._value = 0.0
        self._display_value = 0.0
        self.setMinimumSize(180, 200)
        self._anim = QPropertyAnimation(self, b"value")
        self._anim.setDuration(350)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def getValue(self) -> float:
        return self._display_value

    def setValue(self, v: float) -> None:
        self._display_value = v
        self.update()

    value = Property(float, getValue, setValue)

    def set_target(self, target: float) -> None:
        target = max(self._min, min(self._max, target))
        self._anim.stop()
        self._anim.setStartValue(self._display_value)
        self._anim.setEndValue(target)
        self._anim.start()
        self._value = target

    def _zone_color(self, val: float) -> QColor:
        for s, e, color in self._zones:
            if s <= abs(val) <= e:
                return QColor(color)
        return QColor(self._zones[-1][2]) if self._zones else QColor(Theme.ACCENT)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height() - 28)
        cx, cy = self.width() / 2, side / 2 + 6
        radius = side / 2 - 10

        # --- Background ring ---
        bg_pen = QPen(QColor(Theme.BORDER))
        bg_pen.setWidth(10)
        bg_pen.setCapStyle(Qt.RoundCap)
        p.setPen(bg_pen)
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        start_angle = 225
        span_angle = -270
        p.drawArc(rect, start_angle * 16, span_angle * 16)

        # --- Colour zone arcs ---
        full_range = self._max - self._min
        for s, e, color in self._zones:
            # Map zone onto both + / - sides symmetrically for roll/pitch style gauges
            frac_s = (s - self._min) / full_range
            frac_e = (e - self._min) / full_range
            a_start = start_angle - frac_s * (-span_angle)
            a_span = -(frac_e - frac_s) * (-span_angle)
            zone_pen = QPen(QColor(color))
            zone_pen.setWidth(10)
            zone_pen.setCapStyle(Qt.FlatCap)
            p.setPen(zone_pen)
            p.drawArc(rect, int(a_start * 16), int(a_span * 16))

        # --- Needle ---
        frac = (max(self._min, min(self._max, self._display_value)) - self._min) / full_range
        angle_deg = start_angle - frac * (-span_angle)
        angle_rad = math.radians(angle_deg)
        needle_len = radius - 14
        nx = cx + needle_len * math.cos(angle_rad)
        ny = cy - needle_len * math.sin(angle_rad)
        needle_color = self._zone_color(self._display_value)
        p.setPen(QPen(needle_color, 3))
        p.drawLine(QPointF(cx, cy), QPointF(nx, ny))
        p.setBrush(QBrush(needle_color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), 6, 6)

        # --- Digital readout ---
        p.setPen(QColor(Theme.TEXT))
        font = QFont(Theme.FONT_FAMILY, 15, QFont.Bold)
        p.setFont(font)
        txt = f"{self._display_value:.1f}{self._unit}"
        p.drawText(QRectF(0, cy + radius * 0.30, self.width(), 30), Qt.AlignCenter, txt)

        # --- Title ---
        p.setPen(QColor(Theme.TEXT_MUTED))
        p.setFont(QFont(Theme.FONT_FAMILY, 9, QFont.DemiBold))
        p.drawText(QRectF(0, self.height() - 20, self.width(), 18), Qt.AlignCenter,
                    self._title.upper())
        p.end()


# =============================================================================
# SECTION 4 :: 2D ANIMATED BUILDING VISUALISATION (QGraphicsObject)
# =============================================================================

class BuildingItem(QGraphicsObject):
    """
    A QGraphicsObject representing the monitored structure.

    Exposes Qt's built-in `rotation` property (inherited) so its tilt can be
    smoothly animated with QPropertyAnimation, plus a custom `shakeOffset`
    property used to produce a danger-state shake animation.
    """

    def __init__(self):
        super().__init__()
        self._color = QColor(Theme.SAFE)
        self._shake = 0.0
        self.setTransformOriginPoint(0, 0)  # rotate around the building's base

    def boundingRect(self) -> QRectF:
        return QRectF(-70, -220, 140, 230)

    def getShake(self) -> float:
        return self._shake

    def setShake(self, v: float) -> None:
        self._shake = v
        self.setX(v)

    shakeOffset = Property(float, getShake, setShake)

    def set_status_color(self, color: QColor) -> None:
        self._color = color
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: N802
        painter.setRenderHint(QPainter.Antialiasing)

        # Building body with subtle vertical gradient for a "glass" feel.
        body_rect = QRectF(-60, -200, 120, 200)
        grad = QLinearGradient(body_rect.topLeft(), body_rect.bottomRight())
        base = self._color
        grad.setColorAt(0.0, base.lighter(135))
        grad.setColorAt(1.0, base.darker(140))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor(Theme.BORDER), 2))
        painter.drawRoundedRect(body_rect, 6, 6)

        # Windows grid
        painter.setBrush(QBrush(QColor(255, 255, 255, 60)))
        painter.setPen(Qt.NoPen)
        rows, cols = 6, 4
        margin_x, margin_y = 14, 14
        win_w = (body_rect.width() - margin_x * 2) / cols - 6
        win_h = (body_rect.height() - margin_y * 2) / rows - 6
        for r in range(rows):
            for c in range(cols):
                wx = body_rect.left() + margin_x + c * (win_w + 6)
                wy = body_rect.top() + margin_y + r * (win_h + 6)
                painter.drawRect(QRectF(wx, wy, win_w, win_h))

        # Rooftop antenna / sensor mast (represents the MPU6050 mount point)
        painter.setPen(QPen(QColor(Theme.TEXT_MUTED), 3))
        painter.drawLine(QPointF(0, -200), QPointF(0, -222))
        painter.setBrush(QBrush(QColor(Theme.ACCENT)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(0, -224), 4, 4)

        # Foundation base
        painter.setBrush(QBrush(QColor(Theme.BORDER)))
        painter.drawRoundedRect(QRectF(-72, 0, 144, 10), 3, 3)


class BuildingWidget(QGraphicsView):
    """
    QGraphicsView host for the animated 2D building model.

    * Rotates the building according to live Roll angle (smooth animation).
    * Recolours the structure (green/yellow/red) per TiltStatus.
    * Plays a shake animation while in DANGER.
    * Shows a warning glyph above the building when not SAFE.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("background: transparent;")
        self.setMinimumHeight(320)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.setSceneRect(-160, -260, 320, 300)

        # Ground line
        ground = self._scene.addLine(-150, 10, 150, 10, QPen(QColor(Theme.BORDER), 2))
        ground.setZValue(-1)

        self._building = BuildingItem()
        self._building.setPos(0, 10)
        self._scene.addItem(self._building)

        self._warning_text = self._scene.addText("\u26A0", QFont(Theme.FONT_FAMILY, 28, QFont.Bold))
        self._warning_text.setDefaultTextColor(QColor(Theme.WARNING))
        self._warning_text.setPos(-14, -260)
        self._warning_text.setVisible(False)

        self._rot_anim = QPropertyAnimation(self._building, b"rotation")
        self._rot_anim.setDuration(400)
        self._rot_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._shake_anim: Optional[QSequentialAnimationGroup] = None

    def update_state(self, roll_deg: float, pitch_deg: float, status: TiltStatus) -> None:
        # Use roll for left-right tilt (primary 2D axis visible in a front-view building).
        # Clamp to ±45° so the building doesn't flip completely off screen.
        target_rotation = max(-45.0, min(45.0, roll_deg))
        self._rot_anim.stop()
        self._rot_anim.setStartValue(self._building.rotation())
        self._rot_anim.setEndValue(target_rotation)
        self._rot_anim.start()

        color_map = {
            TiltStatus.SAFE: QColor(Theme.SAFE),
            TiltStatus.WARNING: QColor(Theme.WARNING),
            TiltStatus.DANGER: QColor(Theme.DANGER),
        }
        self._building.set_status_color(color_map[status])
        self._warning_text.setVisible(status != TiltStatus.SAFE)
        if status != TiltStatus.SAFE:
            glyph_color = Theme.DANGER if status == TiltStatus.DANGER else Theme.WARNING
            self._warning_text.setDefaultTextColor(QColor(glyph_color))

        if status == TiltStatus.DANGER:
            self._start_shake()
        else:
            self._stop_shake()

    def _start_shake(self) -> None:
        if self._shake_anim is not None and self._shake_anim.state() == QAbstractAnimation.Running:
            return
        group = QSequentialAnimationGroup(self)
        for target in (-6, 6, -4, 4, 0):
            a = QPropertyAnimation(self._building, b"shakeOffset")
            a.setDuration(60)
            a.setStartValue(self._building.shakeOffset)
            a.setEndValue(target)
            group.addAnimation(a)
        group.setLoopCount(-1)  # loop while in danger
        self._shake_anim = group
        group.start()

    def _stop_shake(self) -> None:
        if self._shake_anim is not None:
            self._shake_anim.stop()
            self._shake_anim = None
            self._building.setShake(0.0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)


# =============================================================================
# SECTION 5 :: LIVE SCROLLING GRAPH (PyQtGraph)
# =============================================================================

class GraphWidget(QWidget):
    """Real-time, auto-scrolling Roll/Pitch plot for the last 60 seconds."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True, background=None, foreground=Theme.TEXT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        title = QLabel("LIVE TELEMETRY — ROLL & PITCH (60s WINDOW)")
        title.setProperty("class", "SectionTitle")
        title.setObjectName("SectionTitle")
        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self._toggle_pause)
        reset_zoom_btn = QPushButton("🔍 Reset Zoom")
        reset_zoom_btn.clicked.connect(self.reset_zoom)
        toolbar.addWidget(title)
        toolbar.addStretch()
        toolbar.addWidget(self.pause_btn)
        toolbar.addWidget(reset_zoom_btn)
        layout.addLayout(toolbar)

        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("left", "Angle (deg)")
        self.plot.setLabel("bottom", "Time (s)")
        self.plot.setBackground(Theme.BG_2)
        self.plot.addLegend(offset=(10, 10))
        self.plot.setMouseEnabled(x=True, y=True)  # zoom / pan enabled

        self.roll_curve = self.plot.plot(pen=pg.mkPen(Theme.ACCENT, width=2), name="Roll")
        self.pitch_curve = self.plot.plot(pen=pg.mkPen(Theme.ACCENT_2, width=2), name="Pitch")
        layout.addWidget(self.plot)

        self._t: Deque[float] = deque(maxlen=MAX_GRAPH_POINTS)
        self._roll: Deque[float] = deque(maxlen=MAX_GRAPH_POINTS)
        self._pitch: Deque[float] = deque(maxlen=MAX_GRAPH_POINTS)
        self._t0 = time.time()
        self._paused = False

    def _toggle_pause(self, checked: bool) -> None:
        self._paused = checked
        self.pause_btn.setText("▶ Resume" if checked else "⏸ Pause")

    def reset_zoom(self) -> None:
        self.plot.enableAutoRange()

    def add_sample(self, roll: float, pitch: float) -> None:
        if self._paused:
            return
        now = time.time() - self._t0
        self._t.append(now)
        self._roll.append(roll)
        self._pitch.append(pitch)
        self.roll_curve.setData(list(self._t), list(self._roll))
        self.pitch_curve.setData(list(self._t), list(self._pitch))
        if now > GRAPH_WINDOW_SECONDS:
            self.plot.setXRange(now - GRAPH_WINDOW_SECONDS, now, padding=0)

    def export_image(self, path: str) -> None:
        exporter = pg.exporters.ImageExporter(self.plot.plotItem)
        exporter.export(path)


# =============================================================================
# SECTION 6 :: EVENT LOG
# =============================================================================

class EventLogger(QWidget):
    """Scrollable, colour-coded, timestamped structural event log."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("EVENT LOG")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)
        self._records: list[tuple[str, str]] = []

    def add_event(self, status: TiltStatus) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"  {ts}   {status.value}")
        color = Theme.color_for_status(status)
        item.setForeground(QColor(color))
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        self.list_widget.insertItem(0, item)  # newest on top
        self._records.append((ts, status.value))
        if self.list_widget.count() > 500:
            self.list_widget.takeItem(self.list_widget.count() - 1)

    def export_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "status"])
            writer.writerows(self._records)


# =============================================================================
# SECTION 7 :: ALARM MANAGER (Toast Popup + Flashing Border + Beep)
# =============================================================================

class AlarmToast(QFrame):
    """A self-dismissing, non-blocking 'toast' alarm banner (no modal popups)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("AlarmToast")
        self.setStyleSheet(f"""
            QFrame#AlarmToast {{
                background-color: {Theme.DANGER};
                border-radius: 10px;
            }}
        """)
        layout = QHBoxLayout(self)
        self.label = QLabel("⚠ Excessive Structural Tilt Detected")
        self.label.setStyleSheet("color: #1a0306; font-weight: 800; font-size: 13px;")
        layout.addWidget(self.label)
        add_drop_shadow(self, blur=30, alpha=180, color=Theme.DANGER)
        self.setFixedHeight(44)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_for(self, ms: int = 3500) -> None:
        self.show()
        self.raise_()
        self._timer.start(ms)


class AlarmManager(QObject):
    """
    Tracks DANGER state transitions and orchestrates all local alarm effects:
    flashing card border, toast popup, and an audible system beep.
    Automatically silences itself once the structure returns to SAFE.
    """

    dangerEntered = Signal()
    dangerExited = Signal()

    def __init__(self, toast: AlarmToast, flash_targets: list[QFrame], parent=None):
        super().__init__(parent)
        self._toast = toast
        self._flash_targets = flash_targets
        self._in_danger = False
        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(280)
        self._flash_timer.timeout.connect(self._flash_step)
        self._flash_on = False

    def evaluate(self, status: TiltStatus) -> None:
        if status == TiltStatus.DANGER and not self._in_danger:
            self._in_danger = True
            self.dangerEntered.emit()
            self._toast.show_for(4000)
            QApplication.beep()
            self._flash_timer.start()
        elif status != TiltStatus.DANGER and self._in_danger:
            self._in_danger = False
            self.dangerExited.emit()
            self._flash_timer.stop()
            for w in self._flash_targets:
                w.setStyleSheet(self._base_style(w))

    def _base_style(self, w: QFrame) -> str:
        return f"""
            QFrame {{
                background-color: {Theme.BG_2};
                border: 1px solid {Theme.BORDER};
                border-radius: 14px;
            }}
        """

    def _flash_step(self) -> None:
        self._flash_on = not self._flash_on
        border = Theme.DANGER if self._flash_on else Theme.BORDER
        for w in self._flash_targets:
            w.setStyleSheet(f"""
                QFrame {{
                    background-color: {Theme.BG_2};
                    border: 2px solid {border};
                    border-radius: 14px;
                }}
            """)


# =============================================================================
# SECTION 8 :: REUSABLE CARD WIDGETS
# =============================================================================

class StatCard(QFrame):
    """A reusable rounded, drop-shadowed industrial 'stat card'."""

    def __init__(self, icon: str, title: str, unit: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("class", "Card")
        self.setObjectName("Card")
        self.setStyleSheet(f"""
            QFrame#Card {{
                background-color: {Theme.BG_2};
                border: 1px solid {Theme.BORDER};
                border-radius: 14px;
            }}
        """)
        add_drop_shadow(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        top = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 20px;")
        title_lbl = QLabel(title.upper())
        title_lbl.setObjectName("CardTitle")
        title_lbl.setStyleSheet(f"color:{Theme.TEXT_MUTED}; font-size:11px; font-weight:600; letter-spacing:1px;")
        top.addWidget(icon_lbl)
        top.addWidget(title_lbl)
        top.addStretch()
        layout.addLayout(top)

        self.value_lbl = QLabel("--")
        self.value_lbl.setStyleSheet(f"color:{Theme.TEXT}; font-size:26px; font-weight:700;")
        layout.addWidget(self.value_lbl)

        self.unit = unit
        self.sub_lbl = QLabel("")
        self.sub_lbl.setStyleSheet(f"color:{Theme.TEXT_MUTED}; font-size:11px;")
        layout.addWidget(self.sub_lbl)

    def set_value(self, value: str, sub: str = "", color: Optional[str] = None) -> None:
        self.value_lbl.setText(f"{value}{self.unit}")
        if color:
            self.value_lbl.setStyleSheet(f"color:{color}; font-size:26px; font-weight:700;")
        self.sub_lbl.setText(sub)


class HealthCard(QFrame):
    """Structural Health card: large percentage + colour-coded progress bar."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setStyleSheet(f"""
            QFrame#Card {{
                background-color: {Theme.BG_2};
                border: 1px solid {Theme.BORDER};
                border-radius: 14px;
            }}
        """)
        add_drop_shadow(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        title = QLabel("🏗  STRUCTURAL HEALTH")
        title.setStyleSheet(f"color:{Theme.TEXT_MUTED}; font-size:11px; font-weight:600; letter-spacing:1px;")
        layout.addWidget(title)
        self.pct_lbl = QLabel("100%")
        self.pct_lbl.setStyleSheet(f"color:{Theme.SAFE}; font-size:34px; font-weight:800;")
        layout.addWidget(self.pct_lbl)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)
        self.status_lbl = QLabel("HEALTHY")
        self.status_lbl.setStyleSheet(f"color:{Theme.SAFE}; font-weight:700; font-size:12px;")
        layout.addWidget(self.status_lbl)

    def update_health(self, health_pct: float) -> None:
        if health_pct >= 80:
            color, label = Theme.SAFE, "HEALTHY"
        elif health_pct >= 55:
            color, label = Theme.WARNING, "MODERATE"
        else:
            color, label = Theme.DANGER, "CRITICAL"
        self.pct_lbl.setText(f"{health_pct:.0f}%")
        self.pct_lbl.setStyleSheet(f"color:{color}; font-size:34px; font-weight:800;")
        self.status_lbl.setText(label)
        self.status_lbl.setStyleSheet(f"color:{color}; font-weight:700; font-size:12px;")
        self.bar.setValue(int(health_pct))
        self.bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Theme.BG_1};
                border: 1px solid {Theme.BORDER};
                border-radius: 8px;
                height: 16px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 8px;
            }}
        """)


# =============================================================================
# SECTION 9 :: SPLASH SCREEN
# =============================================================================

class SplashScreenWidget(QWidget):
    """Frameless animated splash screen shown while the app initialises."""

    finished = Signal()

    STEPS = [
        "Initializing Sensor (MPU6050)...",
        "Calibrating Tilt Baseline...",
        "Initializing Serial Manager...",
        "Loading Dashboard Components...",
        "Loading Complete.",
    ]

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(560, 360)
        self.setAttribute(Qt.WA_TranslucentBackground)

        container = QFrame(self)
        container.setGeometry(0, 0, 560, 360)
        container.setStyleSheet(f"""
            background-color: {Theme.BG_1};
            border: 1px solid {Theme.ACCENT};
            border-radius: 18px;
        """)
        add_drop_shadow(container, blur=40, alpha=200, color=Theme.ACCENT)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 36, 40, 30)
        layout.addStretch()

        logo = QLabel("🏢")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("font-size: 58px;")
        layout.addWidget(logo)

        title = QLabel(APP_NAME)
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet(f"color:{Theme.TEXT}; font-size:18px; font-weight:800;")
        layout.addWidget(title)

        subtitle = QLabel("Arduino Nano + MPU6050 Prototype  •  ESP32-Ready IoT Architecture")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"color:{Theme.ACCENT}; font-size:11px; font-weight:600;")
        layout.addWidget(subtitle)

        layout.addSpacing(18)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(f"""
            QProgressBar {{ background-color:{Theme.BG_2}; border-radius:6px; height:8px; }}
            QProgressBar::chunk {{ background-color:{Theme.ACCENT}; border-radius:6px; }}
        """)
        layout.addWidget(self.progress)

        self.status_lbl = QLabel(self.STEPS[0])
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setStyleSheet(f"color:{Theme.TEXT_MUTED}; font-size:11px; margin-top:6px;")
        layout.addWidget(self.status_lbl)
        layout.addStretch()

        self._step_index = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(550)

    def _advance(self) -> None:
        self._step_index += 1
        pct = int((self._step_index / len(self.STEPS)) * 100)
        self.progress.setValue(min(pct, 100))
        if self._step_index < len(self.STEPS):
            self.status_lbl.setText(self.STEPS[self._step_index])
        else:
            self._timer.stop()
            self._fade_out()

    def _fade_out(self) -> None:
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(450)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._on_faded)
        self._fade_anim.start()

    def _on_faded(self) -> None:
        self.close()
        self.finished.emit()


# =============================================================================
# SECTION 10 :: SETTINGS & ABOUT DIALOGS
# =============================================================================

class SettingsDialog(QDialog):
    """Configuration dialog: COM port, baud rate, graph refresh, resets, export."""

    def __init__(self, serial_mgr: SerialManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        self._serial_mgr = serial_mgr

        layout = QVBoxLayout(self)

        conn_box = QGroupBox("Connection")
        form = QGridLayout(conn_box)
        form.addWidget(QLabel("COM Port:"), 0, 0)
        self.port_combo = QComboBox()
        self._refresh_ports()
        form.addWidget(self.port_combo, 0, 1)
        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedWidth(36)
        refresh_btn.clicked.connect(self._refresh_ports)
        form.addWidget(refresh_btn, 0, 2)

        form.addWidget(QLabel("Baud Rate:"), 1, 0)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems([str(b) for b in BAUD_RATES])
        self.baud_combo.setCurrentText(str(DEFAULT_BAUD))
        form.addWidget(self.baud_combo, 1, 1)
        layout.addWidget(conn_box)

        disp_box = QGroupBox("Display")
        disp_form = QGridLayout(disp_box)
        disp_form.addWidget(QLabel("Theme:"), 0, 0)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark (Industrial)", "Light"])
        disp_form.addWidget(self.theme_combo, 0, 1)
        disp_form.addWidget(QLabel("Graph Refresh (ms):"), 1, 0)
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(50, 2000)
        self.refresh_spin.setValue(SAMPLE_INTERVAL_MS)
        disp_form.addWidget(self.refresh_spin, 1, 1)
        layout.addWidget(disp_box)

        reset_box = QGroupBox("Resets & Export")
        reset_layout = QHBoxLayout(reset_box)
        self.reset_tilt_btn = QPushButton("Reset Max Tilt")
        self.reset_alerts_btn = QPushButton("Reset Alerts")
        self.export_btn = QPushButton("Export Data...")
        reset_layout.addWidget(self.reset_tilt_btn)
        reset_layout.addWidget(self.reset_alerts_btn)
        reset_layout.addWidget(self.export_btn)
        layout.addWidget(reset_box)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._apply_and_close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _refresh_ports(self) -> None:
        self.port_combo.clear()
        self.port_combo.addItem("Auto-Detect")
        for p in list_ports.comports():
            self.port_combo.addItem(p.device)

    def _apply_and_close(self) -> None:
        port = self.port_combo.currentText()
        self._serial_mgr.set_port(None if port == "Auto-Detect" else port)
        self._serial_mgr.set_baud(int(self.baud_combo.currentText()))
        self.accept()


class AboutDialog(QDialog):
    """Static 'About' dialog with project, tech stack and hardware summary."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("About")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)

        title = QLabel(APP_NAME)
        title.setStyleSheet(f"color:{Theme.ACCENT}; font-size:16px; font-weight:800;")
        layout.addWidget(title)
        layout.addWidget(QLabel(f"Version: {APP_VERSION}"))
        layout.addWidget(QLabel(f"Developer: {ORG_NAME}"))

        layout.addWidget(self._section("Technology Stack",
            "Python 3.11+, PySide6, PyQtGraph, PySerial, Qt Graphics View"))
        layout.addWidget(self._section("Prototype Hardware",
            "Arduino Nano, MPU6050 IMU, Red LED, Active Buzzer"))
        layout.addWidget(self._section("Future Scope",
            "ESP32, WiFi, MQTT, Firebase, Cloud Dashboard, Mobile Push Notifications, "
            "Email/SMS Alerts, OTA Firmware Updates, Predictive Analytics (R&D)"))

        notice = QLabel("This system performs structural TILT MONITORING & early warning.\n"
                         "It is NOT a building-collapse prediction system.")
        notice.setWordWrap(True)
        notice.setStyleSheet(f"color:{Theme.WARNING}; font-style: italic; margin-top:8px;")
        layout.addWidget(notice)

        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)

    @staticmethod
    def _section(title: str, body: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 6, 0, 0)
        t = QLabel(title)
        t.setStyleSheet(f"color:{Theme.TEXT}; font-weight:700;")
        b = QLabel(body)
        b.setWordWrap(True)
        b.setStyleSheet(f"color:{Theme.TEXT_MUTED};")
        v.addWidget(t)
        v.addWidget(b)
        return w


# =============================================================================
# SECTION 11 :: MAIN DASHBOARD WINDOW
# =============================================================================

class MainWindow(QMainWindow):
    """The primary application window assembling every dashboard component."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1600, 980)

        # ---- State -------------------------------------------------------
        self._start_time = time.time()
        self._prev_status = TiltStatus.SAFE
        self._danger_alert_count = 0
        self._local_max_tilt = 0.0
        self._connection_state = "DISCONNECTED"
        self._frame_count_for_fps = 0
        self._last_fps_calc = time.time()
        self._app_fps = 0.0
        self._last_packet_time = time.time()
        self._refresh_rate_hz = 0.0

        # ---- Serial backend ------------------------------------------------
        self.serial_mgr = SerialManager()
        self.serial_mgr.frameReceived.connect(self._on_frame)
        self.serial_mgr.connectionStateChanged.connect(self._on_connection_state)
        self.serial_mgr.portInfoChanged.connect(self._on_port_info)
        self._current_port = "—"
        self._current_baud = DEFAULT_BAUD

        self._build_menu_and_toolbar()
        self._build_header()
        self._build_central_area()
        self._build_status_bar()

        # ---- Timers ----------------------------------------------------
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)

        self.serial_mgr.start()

    # -------------------------------------------------------------------
    # MENU / TOOLBAR
    # -------------------------------------------------------------------
    def _build_menu_and_toolbar(self) -> None:
        menubar: QMenuBar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        export_menu = QMenu("Export", self)
        export_csv_act = QAction("Export Event Log (CSV)", self)
        export_csv_act.triggered.connect(self._export_csv)
        export_graph_act = QAction("Export Graph Image", self)
        export_graph_act.triggered.connect(self._export_graph)
        export_menu.addAction(export_csv_act)
        export_menu.addAction(export_graph_act)
        file_menu.addMenu(export_menu)

        screenshot_act = QAction("Screenshot", self)
        screenshot_act.triggered.connect(self._take_screenshot)
        file_menu.addAction(screenshot_act)
        file_menu.addSeparator()
        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        view_menu = menubar.addMenu("&View")
        reset_zoom_act = QAction("Reset Zoom (Graph)", self)
        reset_zoom_act.triggered.connect(lambda: self.graph_widget.reset_zoom())
        view_menu.addAction(reset_zoom_act)

        settings_menu = menubar.addMenu("&Settings")
        open_settings_act = QAction("Preferences...", self)
        open_settings_act.triggered.connect(self._open_settings)
        settings_menu.addAction(open_settings_act)

        help_menu = menubar.addMenu("&Help")
        about_act = QAction("About", self)
        about_act.triggered.connect(self._open_about)
        help_menu.addAction(about_act)

        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        style = self.style()
        reset_tilt_act = QAction(style.standardIcon(QStyle.SP_BrowserReload), "Reset Max Tilt", self)
        reset_tilt_act.triggered.connect(self._reset_max_tilt)
        reset_alerts_act = QAction(style.standardIcon(QStyle.SP_DialogResetButton), "Reset Alerts", self)
        reset_alerts_act.triggered.connect(self._reset_alerts)
        screenshot_tb_act = QAction(style.standardIcon(QStyle.SP_DriveFDIcon), "Screenshot", self)
        screenshot_tb_act.triggered.connect(self._take_screenshot)
        settings_tb_act = QAction(style.standardIcon(QStyle.SP_FileDialogDetailedView), "Settings", self)
        settings_tb_act.triggered.connect(self._open_settings)
        about_tb_act = QAction(style.standardIcon(QStyle.SP_MessageBoxInformation), "About", self)
        about_tb_act.triggered.connect(self._open_about)

        toolbar.addAction(reset_tilt_act)
        toolbar.addAction(reset_alerts_act)
        toolbar.addSeparator()
        toolbar.addAction(screenshot_tb_act)
        toolbar.addAction(settings_tb_act)
        toolbar.addSeparator()
        toolbar.addAction(about_tb_act)

    # -------------------------------------------------------------------
    # HEADER
    # -------------------------------------------------------------------
    def _build_header(self) -> None:
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(86)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 8, 20, 8)

        title_box = QVBoxLayout()
        name_lbl = QLabel("🏢  " + APP_NAME)
        name_lbl.setStyleSheet(f"color:{Theme.TEXT}; font-size:16px; font-weight:800;")
        sub_lbl = QLabel("Controller: Arduino Nano  •  Sensor: MPU6050  •  Future: ESP32 IoT  "
                          "(ARDUINO PROTOTYPE — ESP32-MIGRATION READY)")
        sub_lbl.setStyleSheet(f"color:{Theme.ACCENT}; font-size:11px; font-weight:600;")
        title_box.addWidget(name_lbl)
        title_box.addWidget(sub_lbl)
        layout.addLayout(title_box)
        layout.addStretch()

        # Date / Time
        dt_box = QVBoxLayout()
        self.date_lbl = QLabel()
        self.date_lbl.setStyleSheet(f"color:{Theme.TEXT_MUTED}; font-size:11px;")
        self.time_lbl = QLabel()
        self.time_lbl.setStyleSheet(f"color:{Theme.TEXT}; font-size:16px; font-weight:700;")
        self.time_lbl.setAlignment(Qt.AlignRight)
        dt_box.addWidget(self.date_lbl, alignment=Qt.AlignRight)
        dt_box.addWidget(self.time_lbl, alignment=Qt.AlignRight)
        layout.addLayout(dt_box)
        layout.addSpacing(24)

        # Connection status pill
        self.conn_pill = QLabel("●  DISCONNECTED")
        self.conn_pill.setStyleSheet(f"""
            background-color: {Theme.DANGER_BG}; color:{Theme.DANGER};
            border-radius: 10px; padding: 6px 14px; font-weight: 700; font-size: 11px;
        """)
        layout.addWidget(self.conn_pill, alignment=Qt.AlignVCenter)

        # Force Connect button — lets user quickly pick and connect a port
        self.force_connect_btn = QPushButton("🔌 Connect Arduino")
        self.force_connect_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.ACCENT}; color: #04141c;
                border-radius: 8px; padding: 6px 12px; font-weight: 700; font-size: 11px;
                border: none;
            }}
            QPushButton:hover {{ background-color: #00aacc; }}
        """)
        self.force_connect_btn.clicked.connect(self._force_connect_dialog)
        layout.addWidget(self.force_connect_btn, alignment=Qt.AlignVCenter)

        self.setMenuWidget(None)
        central_holder = QWidget()
        central_layout = QVBoxLayout(central_holder)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(header)
        self._header_container = central_holder
        self._tick_clock()

    # -------------------------------------------------------------------
    # CENTRAL AREA
    # -------------------------------------------------------------------
    def _build_central_area(self) -> None:
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(self._header_container)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 14, 18, 14)
        content_layout.setSpacing(14)

        # Alarm toast (floats logically at top of content area)
        self.alarm_toast = AlarmToast(content)
        content_layout.addWidget(self.alarm_toast)

        # ---- Row 1: Stat Cards ----
        cards_row = QGridLayout()
        cards_row.setSpacing(14)
        self.card_roll = StatCard("📐", "Roll", "°")
        self.card_pitch = StatCard("📏", "Pitch", "°")
        self.card_max_tilt = StatCard("📈", "Maximum Tilt", "°")
        self.card_temp = StatCard("🌡️", "Temperature", "°C")
        self.card_risk = StatCard("⚠️", "Risk Level", "%")
        self.card_alerts = StatCard("🚨", "Alert Counter", "")
        self.card_duration = StatCard("⏱️", "Monitoring Duration", "")
        self.card_system = StatCard("🛰️", "System Status", "")

        cards = [self.card_roll, self.card_pitch, self.card_max_tilt, self.card_temp,
                 self.card_risk, self.card_alerts, self.card_duration, self.card_system]
        for i, c in enumerate(cards):
            cards_row.addWidget(c, i // 4, i % 4)
        content_layout.addLayout(cards_row)

        # ---- Row 2: Building + Gauges + Health ----
        row2 = QHBoxLayout()
        row2.setSpacing(14)

        building_panel = self._panel("STRUCTURAL VISUALISATION (LIVE TILT MODEL)")
        self.building_widget = BuildingWidget()
        building_panel.layout().addWidget(self.building_widget)
        row2.addWidget(building_panel, 2)

        gauges_panel = self._panel("ORIENTATION & RISK GAUGES")
        gauges_layout = QHBoxLayout()
        zones_rp = [(0, TILT_WARNING_DEG, Theme.SAFE),
                    (TILT_WARNING_DEG, TILT_DANGER_DEG, Theme.WARNING),
                    (TILT_DANGER_DEG, 90, Theme.DANGER)]
        self.roll_gauge = RoundGauge("Roll", "°", -90, 90, zones_rp)
        self.pitch_gauge = RoundGauge("Pitch", "°", -90, 90, zones_rp)
        zones_risk = [(0, 40, Theme.SAFE), (40, 65, Theme.WARNING), (65, 100, Theme.DANGER)]
        self.risk_gauge = RoundGauge("Risk", "%", 0, 100, zones_risk)
        gauges_layout.addWidget(self.roll_gauge)
        gauges_layout.addWidget(self.pitch_gauge)
        gauges_layout.addWidget(self.risk_gauge)
        gauges_panel.layout().addLayout(gauges_layout)
        self.health_card = HealthCard()
        gauges_panel.layout().addWidget(self.health_card)
        row2.addWidget(gauges_panel, 2)

        content_layout.addLayout(row2)

        # ---- Row 3: Graph + Event Log ----
        row3 = QHBoxLayout()
        row3.setSpacing(14)
        graph_panel = self._panel(None)
        self.graph_widget = GraphWidget()
        graph_panel.layout().addWidget(self.graph_widget)
        row3.addWidget(graph_panel, 3)

        log_panel = self._panel(None)
        self.event_logger = EventLogger()
        log_panel.layout().addWidget(self.event_logger)
        row3.addWidget(log_panel, 1)
        content_layout.addLayout(row3)

        # ---- Row 4: LED/Buzzer + System Health + Future ESP32 ----
        row4 = QHBoxLayout()
        row4.setSpacing(14)

        io_panel = self._panel("LOCAL ALARM HARDWARE STATUS")
        io_layout = QHBoxLayout()
        self.led_lbl = QLabel("🔴 LED: OFF")
        self.led_lbl.setStyleSheet(f"color:{Theme.TEXT_MUTED}; font-weight:700; font-size:13px;")
        self.buzzer_lbl = QLabel("🔇 BUZZER: OFF")
        self.buzzer_lbl.setStyleSheet(f"color:{Theme.TEXT_MUTED}; font-weight:700; font-size:13px;")
        io_layout.addWidget(self.led_lbl)
        io_layout.addWidget(self.buzzer_lbl)
        io_panel.layout().addLayout(io_layout)
        row4.addWidget(io_panel, 1)

        sys_panel = self._panel("SYSTEM HEALTH")
        sys_grid = QGridLayout()
        self.lbl_sensor_status = QLabel("Sensor Status: --")
        self.lbl_comm_status = QLabel("Communication: --")
        self.lbl_refresh_rate = QLabel("Data Refresh Rate: -- Hz")
        self.lbl_memory = QLabel("Memory Usage: --")
        self.lbl_fps = QLabel("Application FPS: --")
        self.lbl_monitoring = QLabel("Monitoring Status: ACTIVE")
        for i, lbl in enumerate([self.lbl_sensor_status, self.lbl_comm_status, self.lbl_refresh_rate,
                                  self.lbl_memory, self.lbl_fps, self.lbl_monitoring]):
            lbl.setStyleSheet(f"color:{Theme.TEXT_MUTED}; font-size:12px;")
            sys_grid.addWidget(lbl, i // 2, i % 2)
        sys_panel.layout().addLayout(sys_grid)
        row4.addWidget(sys_panel, 1)

        future_panel = self._panel("FUTURE ESP32 IoT ENHANCEMENTS (NOT YET IMPLEMENTED)")
        future_grid = QGridLayout()
        future_items = ["📶 WiFi", "📡 MQTT", "🔥 Firebase", "☁️ Cloud Dashboard",
                         "📱 Mobile App", "✉️ Email Alerts", "💬 SMS Alerts",
                         "🔄 OTA Firmware Update", "🤖 Predictive Analytics (R&D)"]
        for i, item in enumerate(future_items):
            lbl = QLabel(f"{item}  —  Planned")
            lbl.setStyleSheet(f"color:{Theme.TEXT_MUTED}; font-size:11px;")
            future_grid.addWidget(lbl, i // 3, i % 3)
        future_panel.layout().addLayout(future_grid)
        row4.addWidget(future_panel, 1)

        content_layout.addLayout(row4)
        content_layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)
        self.setCentralWidget(outer)

        # Alarm manager wires the flashing border targets together.
        self.alarm_manager = AlarmManager(self.alarm_toast, [self.card_risk, self.card_alerts])

    @staticmethod
    def _panel(title: Optional[str]) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setStyleSheet(f"""
            QFrame#Panel {{
                background-color: {Theme.BG_1};
                border: 1px solid {Theme.BORDER};
                border-radius: 16px;
            }}
        """)
        add_drop_shadow(panel, blur=20, alpha=110)
        v = QVBoxLayout(panel)
        v.setContentsMargins(16, 14, 16, 14)
        if title:
            t = QLabel(title)
            t.setStyleSheet(f"color:{Theme.ACCENT}; font-size:12px; font-weight:700; letter-spacing:1px;")
            v.addWidget(t)
        return panel

    # -------------------------------------------------------------------
    # STATUS BAR
    # -------------------------------------------------------------------
    def _build_status_bar(self) -> None:
        sb: QStatusBar = self.statusBar()
        self.sb_conn = QLabel("DISCONNECTED")
        self.sb_port = QLabel("Port: —")
        self.sb_baud = QLabel(f"Baud: {DEFAULT_BAUD}")
        self.sb_freq = QLabel("Sampling: 100ms (10Hz)")
        for w in (self.sb_conn, self.sb_port, self.sb_baud, self.sb_freq):
            w.setStyleSheet(f"color:{Theme.TEXT_MUTED}; padding: 0 10px;")
            sb.addPermanentWidget(w)

    # -------------------------------------------------------------------
    # SLOTS — Serial Events
    # -------------------------------------------------------------------
    @Slot(object)
    def _on_frame(self, frame: TelemetryFrame) -> None:
        now = time.time()
        # Refresh-rate telemetry (Hz)
        dt = now - self._last_packet_time
        self._last_packet_time = now
        if dt > 0:
            self._refresh_rate_hz = 1.0 / dt

        status = frame.status  # trust Arduino classification; Python re-validates below
        # Re-classify from the Python side for consistency with dashboard thresholds
        tilt_mag = max(abs(frame.roll), abs(frame.pitch))
        status = TiltStatus.classify(tilt_mag)
        self._local_max_tilt = max(self._local_max_tilt, abs(frame.roll), abs(frame.pitch), frame.max_tilt)
        risk = compute_risk(self._local_max_tilt)
        health = compute_health(risk)

        # --- Update Cards ---
        status_color = Theme.color_for_status(status)
        self.card_roll.set_value(f"{frame.roll:.1f}", sub=f"Pitch: {frame.pitch:.1f}°")
        self.card_pitch.set_value(f"{frame.pitch:.1f}", sub=f"Roll: {frame.roll:.1f}°")
        self.card_max_tilt.set_value(f"{self._local_max_tilt:.1f}", sub=f"Risk: {risk:.0f}%")
        self.card_temp.set_value(f"{frame.temperature:.1f}", sub="MPU6050 on-die °C")
        self.card_risk.set_value(f"{risk:.0f}", sub=f"Health: {health:.0f}%", color=status_color)
        self.card_system.set_value(status.value, sub=self._connection_state, color=status_color)
        elapsed = now - self._start_time
        h, rem = divmod(int(elapsed), 3600)
        m, s = divmod(rem, 60)
        self.card_duration.set_value(f"{h:02d}:{m:02d}:{s:02d}")

        # --- Alert counter: only increment on SAFE/WARNING -> DANGER edge ---
        if status == TiltStatus.DANGER and self._prev_status != TiltStatus.DANGER:
            self._danger_alert_count += 1
        # Merge with Arduino-reported alert count (take the higher value)
        display_alerts = max(self._danger_alert_count, frame.alerts)
        self.card_alerts.set_value(str(display_alerts), color=Theme.DANGER if display_alerts else None)

        # --- Gauges ---
        self.roll_gauge.set_target(frame.roll)
        self.pitch_gauge.set_target(frame.pitch)
        self.risk_gauge.set_target(risk)
        self.health_card.update_health(health)

        # --- Building visualisation ---
        self.building_widget.update_state(frame.roll, frame.pitch, status)

        # --- Graph ---
        self.graph_widget.add_sample(frame.roll, frame.pitch)

        # --- Event log on status change ---
        if status != self._prev_status:
            self.event_logger.add_event(status)

        # --- Alarm manager ---
        self.alarm_manager.evaluate(status)

        # --- LED / Buzzer indicators (mirrors Arduino's local hardware state exactly) ---
        # Arduino: LED ON for WARNING or DANGER; BUZZER (tone) ON for DANGER only
        led_on = (status == TiltStatus.WARNING or status == TiltStatus.DANGER)
        buzzer_on = (status == TiltStatus.DANGER)
        led_color = Theme.WARNING if status == TiltStatus.WARNING else (Theme.DANGER if led_on else Theme.TEXT_MUTED)
        self.led_lbl.setText(f"{'🔴' if led_on else '⚪'} LED: {'ON' if led_on else 'OFF'}")
        self.led_lbl.setStyleSheet(f"color:{led_color}; font-weight:700; font-size:13px;")
        self.buzzer_lbl.setText(f"{'🔊' if buzzer_on else '🔇'} BUZZER: {'ACTIVE (2kHz tone)' if buzzer_on else 'OFF'}")
        self.buzzer_lbl.setStyleSheet(f"color:{Theme.DANGER if buzzer_on else Theme.TEXT_MUTED}; font-weight:700; font-size:13px;")

        # --- System health panel ---
        sensor_ok = self._connection_state in ("CONNECTED", "SIMULATION")
        sensor_color = Theme.SAFE if sensor_ok else Theme.DANGER
        sensor_text = "OK ✓" if sensor_ok else "NO DATA ✗"
        self.lbl_sensor_status.setText(f"Sensor Status: {sensor_text}")
        self.lbl_sensor_status.setStyleSheet(f"color:{sensor_color}; font-size:12px; font-weight:700;")
        comm_color = {
            "CONNECTED": Theme.SAFE,
            "SIMULATION": Theme.ACCENT_2,
            "RECONNECTING": Theme.WARNING,
            "DISCONNECTED": Theme.DANGER,
        }.get(self._connection_state, Theme.TEXT_MUTED)
        self.lbl_comm_status.setText(f"Communication: {self._connection_state}")
        self.lbl_comm_status.setStyleSheet(f"color:{comm_color}; font-size:12px; font-weight:700;")
        self.lbl_refresh_rate.setText(f"Data Refresh Rate: {self._refresh_rate_hz:.1f} Hz")
        self.lbl_memory.setText(f"Memory Usage: {self._memory_usage_str()}")
        self.lbl_fps.setText(f"Application FPS: {self._app_fps:.0f}")
        monitoring_color = Theme.SAFE if sensor_ok else Theme.WARNING
        self.lbl_monitoring.setText("Monitoring Status: ACTIVE" if sensor_ok else "Monitoring Status: WAITING FOR DATA")
        self.lbl_monitoring.setStyleSheet(f"color:{monitoring_color}; font-size:12px; font-weight:700;")

        self._prev_status = status
        self._frame_count_for_fps += 1
        if now - self._last_fps_calc >= 1.0:
            self._app_fps = self._frame_count_for_fps / (now - self._last_fps_calc)
            self._frame_count_for_fps = 0
            self._last_fps_calc = now

    @staticmethod
    def _status_color(status: TiltStatus) -> str:
        return Theme.color_for_status(status)

    @staticmethod
    def _memory_usage_str() -> str:
        if _HAS_PSUTIL:
            try:
                mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
                return f"{mb:.1f} MB"
            except Exception:
                return "N/A"
        return "N/A (psutil not installed)"

    @Slot(str)
    def _on_connection_state(self, state: str) -> None:
        self._connection_state = state
        colors = {
            "CONNECTED": (Theme.SAFE, Theme.SAFE_BG),
            "DISCONNECTED": (Theme.DANGER, Theme.DANGER_BG),
            "RECONNECTING": (Theme.WARNING, Theme.WARNING_BG),
            "SIMULATION": (Theme.ACCENT_2, "rgba(124,92,255,28)"),
        }
        color, bg = colors.get(state, (Theme.TEXT_MUTED, Theme.BG_2))
        label = "SIMULATION MODE" if state == "SIMULATION" else state
        self.conn_pill.setText(f"●  {label}")
        self.conn_pill.setStyleSheet(f"""
            background-color: {bg}; color:{color};
            border-radius: 10px; padding: 6px 14px; font-weight: 700; font-size: 11px;
        """)
        self.sb_conn.setText(label)
        # Show the connect button when not actually connected to hardware
        is_hw_connected = (state == "CONNECTED")
        self.force_connect_btn.setVisible(not is_hw_connected)
        self.force_connect_btn.setText(
            "🔌 Connect Arduino" if state in ("DISCONNECTED", "SIMULATION") else "⟳ Reconnecting..."
        )

    @Slot(str, int)
    def _on_port_info(self, port: str, baud: int) -> None:
        self._current_port = port
        self._current_baud = baud
        self.sb_port.setText(f"Port: {port}")
        self.sb_baud.setText(f"Baud: {baud}")

    # -------------------------------------------------------------------
    # SLOTS — UI Actions
    # -------------------------------------------------------------------
    def _tick_clock(self) -> None:
        now = datetime.now()
        self.date_lbl.setText(now.strftime("%A, %d %B %Y"))
        self.time_lbl.setText(now.strftime("%H:%M:%S"))

    def _reset_max_tilt(self) -> None:
        self._local_max_tilt = 0.0
        self.card_max_tilt.set_value("0.0")

    def _reset_alerts(self) -> None:
        self._danger_alert_count = 0
        self.card_alerts.set_value("0")

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Event Log", "event_log.csv", "CSV Files (*.csv)")
        if path:
            try:
                self.event_logger.export_csv(path)
                QMessageBox.information(self, "Export Complete", f"Event log exported to:\n{path}")
            except Exception as e:
                QMessageBox.warning(self, "Export Failed", str(e))

    def _export_graph(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Graph", "graph.png", "PNG Files (*.png)")
        if path:
            try:
                self.graph_widget.export_image(path)
                QMessageBox.information(self, "Export Complete", f"Graph exported to:\n{path}")
            except Exception as e:
                QMessageBox.warning(self, "Export Failed", str(e))

    def _take_screenshot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Screenshot", "dashboard_screenshot.png", "PNG Files (*.png)")
        if path:
            pixmap = self.grab()
            pixmap.save(path, "PNG")
            QMessageBox.information(self, "Screenshot Saved", f"Saved to:\n{path}")

    def _force_connect_dialog(self) -> None:
        """Show a quick port-picker dialog and immediately attempt connection."""
        from PySide6.QtWidgets import QInputDialog
        import glob

        # Gather all candidates
        ports = ["Auto-Detect"]
        for p in list_ports.comports():
            ports.append(f"{p.device}  ({p.description})")
        # Also add Linux-style paths directly
        for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
            for path in sorted(glob.glob(pattern)):
                entry = f"{path}  (direct)"
                if not any(path in x for x in ports):
                    ports.append(entry)

        choice, ok = QInputDialog.getItem(
            self, "Connect Arduino",
            "Select the port your Arduino Nano is connected to\n"
            "(On Linux it's usually /dev/ttyUSB0 for CH340):",
            ports, 0, False
        )
        if not ok:
            return

        # Extract just the device path
        port = None if choice == "Auto-Detect" else choice.split("  ")[0].strip()

        # Exit simulation and force reconnect
        self.serial_mgr._simulate = False
        self.serial_mgr._close_port()
        self.serial_mgr.set_port(port)
        self._on_connection_state("RECONNECTING")

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.serial_mgr, self)
        dlg.reset_tilt_btn.clicked.connect(self._reset_max_tilt)
        dlg.reset_alerts_btn.clicked.connect(self._reset_alerts)
        dlg.export_btn.clicked.connect(self._export_csv)
        dlg.exec()

    def _open_about(self) -> None:
        AboutDialog(self).exec()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.serial_mgr.stop()
        super().closeEvent(event)


# =============================================================================
# SECTION 12 :: APPLICATION ENTRY POINT
# =============================================================================

def main() -> int:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(Theme.stylesheet())

    window = MainWindow()

    splash = SplashScreenWidget()
    screen_geo = app.primaryScreen().geometry()
    splash.move(
        screen_geo.center().x() - splash.width() // 2,
        screen_geo.center().y() - splash.height() // 2,
    )

    def show_main():
        window.showMaximized()

    splash.finished.connect(show_main)
    splash.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
