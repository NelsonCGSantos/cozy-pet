import sys
import math
import random
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QWidget,
)

# Pixel pet layout
SCALE = 8
GRID_W = 32
GRID_H = 38
CHROME_H = 22
MARGIN = 16
FOOTER_PAD = SCALE * 10
OUTER_W = GRID_W * SCALE + MARGIN * 2
OUTER_H = GRID_H * SCALE + MARGIN * 2 + CHROME_H + FOOTER_PAD
RADIUS = 18

# Timing
FRAME_MS = 120
BLINK_INTERVAL = (3000, 6200)
BLINK_DURATION = 280
STEP_INTERVAL = 700
PALETTE = {
    "bg_top": QColor(30, 30, 42),
    "bg_bottom": QColor(18, 18, 26),
    "shell": QColor(64, 64, 84),
    "screen": QColor(210, 232, 210),
    "shadow": QColor(0, 0, 0, 120),
    "pet_body": QColor(116, 188, 232),
    "pet_accent": QColor(82, 152, 208),
    "pet_face": QColor(26, 42, 60),
    "pet_bathroom": QColor(228, 92, 96),
    "pet_hungry": QColor(240, 178, 66),
    "pet_sleepy": QColor(172, 180, 240),
    "pet_highlight": QColor(236, 244, 252),
    "pet_cheek": QColor(255, 150, 170),
    "meter_bg": QColor(188, 204, 188),
    "meter_border": QColor(100, 120, 100),
    "meter_hunger": QColor(232, 112, 120),
    "meter_bathroom": QColor(120, 200, 236),
    "meter_sleep": QColor(184, 160, 232),
    "button_food": QColor(240, 206, 120),
    "button_sleep": QColor(160, 180, 240),
    "button_bathroom": QColor(180, 220, 180),
}

HUNGER_DECAY_PER_SEC = 0.08
BATHROOM_DECAY_PER_SEC = 0.05
REST_DECAY_PER_SEC = 0.03
ACTION_BOOST = 55


class TopChrome(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(CHROME_H)

        self.btn = QPushButton("✕", self)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setFixedSize(18, 18)
        self.btn.move(OUTER_W - MARGIN - self.btn.width(), (CHROME_H - self.btn.height()) // 2)
        self.btn.setStyleSheet(
            """
            QPushButton { border: none; color: #f4f4f4; background: rgba(255,255,255,45); border-radius: 9px; }
            QPushButton:hover { background: rgba(255,255,255,80); }
            QPushButton:pressed { background: rgba(255,255,255,100); }
            """
        )

        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self._opacity = 0.0
        self.effect.setOpacity(self._opacity)
        self.setVisible(False)

        self._target = 0.0
        self._fade = QTimer(self)
        self._fade.setInterval(16)
        self._fade.timeout.connect(self._tick)

    def _tick(self):
        step = 0.12 if self._target > self._opacity else -0.12
        self._opacity = max(0.0, min(1.0, self._opacity + step))
        self.effect.setOpacity(self._opacity)
        self.setVisible(self._opacity > 0.01)
        if abs(self._opacity - self._target) < 0.02:
            self._fade.stop()
            self._opacity = self._target
            self.effect.setOpacity(self._opacity)
            self.setVisible(self._opacity > 0.01)

    def set_target(self, value: float):
        self._target = max(0.0, min(1.0, value))
        self._fade.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar = QRectF(0, 0, OUTER_W, CHROME_H)
        p.setBrush(QColor(28, 30, 38, 220))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(bar, RADIUS, RADIUS)


class PixelPetWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pixel Pal")
        self.setFixedSize(OUTER_W, OUTER_H)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.chrome = TopChrome(self)
        self.chrome.move(0, 0)
        self.chrome.btn.clicked.connect(QApplication.instance().quit)

        self._drag = None
        self.start_time = datetime.now()

        self.blink_active = False
        self.blink_elapsed = 0
        self.next_blink = self._rand(*BLINK_INTERVAL)

        self.step_phase = 0
        self.step_timer = 0

        self.hunger = 100.0
        self.bathroom = 100.0
        self.rest = 100.0

        self.button_regions: dict[str, QRectF] = {}

        self.anim = QTimer(self)
        self.anim.setInterval(FRAME_MS)
        self.anim.timeout.connect(self.on_tick)
        self.anim.start()

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 24, screen.bottom() - self.height() - 52)

    # --- helpers ---
    def _rand(self, low: int, high: int) -> int:
        return random.randint(low, high)

    def expression(self) -> str:
        if self.hunger <= 20:
            return "hungry"
        if self.bathroom <= 20:
            return "bathroom"
        if self.rest <= 25:
            return "sleepy"
        return "default"

    # --- events ---
    def enterEvent(self, _):
        self.chrome.set_target(1.0)

    def leaveEvent(self, _):
        self.chrome.set_target(0.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            pos = e.position()
            for name, rect in self.button_regions.items():
                if rect.contains(pos):
                    if name == "food":
                        self.feed_pet()
                    elif name == "sleep":
                        self.rest_pet()
                    elif name == "potty":
                        self.potty_pet()
                    return
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _):
        self._drag = None

    # --- loop ---
    def on_tick(self):
        dt = FRAME_MS
        seconds = dt / 1000.0
        if self.blink_active:
            self.blink_elapsed += dt
            if self.blink_elapsed >= BLINK_DURATION:
                self.blink_active = False
                self.blink_elapsed = 0
                self.next_blink = self._rand(*BLINK_INTERVAL)
        else:
            self.next_blink -= dt
            if self.next_blink <= 0:
                self.blink_active = True
                self.blink_elapsed = 0

        self.step_timer += dt
        if self.step_timer >= STEP_INTERVAL:
            self.step_timer = 0
            self.step_phase = (self.step_phase + 1) % 4

        self._decay_meters(seconds)
        self.update()

    def _decay_meters(self, seconds: float):
        self.hunger = max(0.0, self.hunger - HUNGER_DECAY_PER_SEC * seconds)
        self.bathroom = max(0.0, self.bathroom - BATHROOM_DECAY_PER_SEC * seconds)
        self.rest = max(0.0, self.rest - REST_DECAY_PER_SEC * seconds)

    def feed_pet(self):
        self.hunger = min(100.0, self.hunger + ACTION_BOOST)
        self.bathroom = max(0.0, self.bathroom - 12.0)

    def rest_pet(self):
        self.rest = min(100.0, self.rest + ACTION_BOOST)
        self.hunger = max(0.0, self.hunger - 8.0)

    def potty_pet(self):
        self.bathroom = min(100.0, self.bathroom + ACTION_BOOST)
        self.rest = max(0.0, self.rest - 5.0)

    def eye_open(self) -> float:
        if not self.blink_active:
            return 1.0
        progress = min(1.0, self.blink_elapsed / max(1, BLINK_DURATION))
        return max(0.0, 1.0 - math.sin(progress * math.pi))

    # --- painting ---
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # bezel
        panel = QRectF(0, 0, OUTER_W, OUTER_H)
        p.setPen(Qt.PenStyle.NoPen)
        for offset in range(5):
            alpha = 80 - offset * 12
            if alpha <= 0:
                continue
            p.setBrush(QColor(0, 0, 0, alpha))
            inset = panel.adjusted(offset, offset, -offset, -offset)
            p.drawRoundedRect(inset, RADIUS, RADIUS)

        inner = panel.adjusted(2, 2, -2, -2)
        grad = QLinearGradient(inner.topLeft(), inner.bottomRight())
        grad.setColorAt(0.0, PALETTE["bg_top"])
        grad.setColorAt(1.0, PALETTE["bg_bottom"])
        p.setBrush(grad)
        p.drawRoundedRect(inner, RADIUS - 2, RADIUS - 2)

        shell = QRectF(MARGIN / 2, CHROME_H + MARGIN / 2, OUTER_W - MARGIN, OUTER_H - CHROME_H - MARGIN)
        p.setBrush(PALETTE["shell"])
        p.drawRoundedRect(shell, 14, 14)

        screen = QRectF(MARGIN, CHROME_H + MARGIN, GRID_W * SCALE, GRID_H * SCALE)
        p.setBrush(PALETTE["screen"])
        p.drawRoundedRect(screen, 8, 8)

        self._draw_meters(p, screen)
        self._draw_pet(p, screen)
        self._draw_buttons(p, screen)

    def _draw_meters(self, p: QPainter, screen: QRectF):
        bar_width = screen.width() - SCALE * 4
        bar_height = max(4.0, SCALE * 1.4)
        start_x = screen.left() + SCALE * 2
        start_y = screen.top() + SCALE * 1.2
        spacing = SCALE * 1.8
        meters = [
            ("H", self.hunger / 100.0, PALETTE["meter_hunger"]),
            ("B", self.bathroom / 100.0, PALETTE["meter_bathroom"]),
            ("Z", self.rest / 100.0, PALETTE["meter_sleep"]),
        ]
        p.save()
        label_font = p.font()
        label_font.setBold(True)
        label_font.setPointSizeF(max(label_font.pointSizeF(), SCALE * 2.3))
        p.setFont(label_font)
        for idx, (label, ratio, color) in enumerate(meters):
            y = start_y + idx * (bar_height + spacing)
            frame = QRectF(start_x, y, bar_width, bar_height)
            p.setPen(QPen(PALETTE["meter_border"], 1.2))
            p.setBrush(PALETTE["meter_bg"])
            radius = max(3.0, SCALE * 1.0)
            p.drawRoundedRect(frame, radius, radius)
            usable_ratio = max(0.0, min(1.0, ratio))
            fill = QRectF(
                frame.left() + SCALE * 0.7,
                frame.top() + bar_height * 0.25,
                (frame.width() - SCALE * 1.4) * usable_ratio,
                bar_height * 0.5,
            )
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(fill, radius * 0.8, radius * 0.8)
            p.setPen(QPen(PALETTE["meter_border"], 1.6))
            outline_font = QFont(label_font)
            outline_font.setPointSizeF(label_font.pointSizeF() + 1.2)
            p.setFont(outline_font)
            outline_rect = frame.adjusted(-SCALE * 1.7, -SCALE * 0.6, -SCALE, SCALE * 0.2)
            p.drawText(outline_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
            p.setPen(QPen(QColor(255, 255, 255), 0))
            p.setFont(label_font)
            p.drawText(outline_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
        p.restore()

    def _draw_buttons(self, p: QPainter, screen: QRectF):
        base_y = screen.bottom() + SCALE * 2
        btn_w = SCALE * 9
        btn_h = SCALE * 6
        spacing = SCALE * 2
        total_width = btn_w * 3 + spacing * 2
        start_x = screen.left() + (screen.width() - total_width) / 2
        labels = [
            ("food", "FEED", PALETTE["button_food"]),
            ("sleep", "REST", PALETTE["button_sleep"]),
            ("potty", "POTTY", PALETTE["button_bathroom"]),
        ]

        self.button_regions = {}
        font = p.font()
        font.setFamily("Chicago")
        font.setPointSizeF(max(font.pointSizeF(), SCALE * 1.4))
        font.setBold(True)
        p.setFont(font)

        for idx, (name, label, color) in enumerate(labels):
            rect = QRectF(
                start_x + idx * (btn_w + spacing),
                base_y,
                btn_w,
                btn_h,
            )
            self.button_regions[name] = rect
            p.setBrush(color)
            p.setPen(QPen(QColor(40, 40, 60), 2))
            p.drawRoundedRect(rect, SCALE, SCALE)
            icon = rect.adjusted(SCALE * 1.2, SCALE * 0.8, -SCALE * 1.2, -SCALE * 2.2)
            p.setPen(Qt.PenStyle.NoPen)
            if name == "food":
                plate = QRectF(icon.left(), icon.bottom() - SCALE * 1.2, icon.width(), SCALE * 1.1)
                p.setBrush(QColor(230, 238, 240))
                p.drawRoundedRect(plate, SCALE * 0.6, SCALE * 0.6)
                p.setBrush(QColor(255, 200, 120))
                fruit = QRectF(icon.center().x() - SCALE * 1.2, icon.top(), SCALE * 2.4, icon.height() - SCALE * 0.8)
                p.drawEllipse(fruit)
                stem = QPainterPath()
                stem.moveTo(fruit.center().x(), fruit.top())
                stem.quadTo(fruit.center().x() + SCALE * 0.6, fruit.top() - SCALE * 0.8, fruit.center().x() + SCALE * 0.4, fruit.top() - SCALE * 0.2)
                p.setBrush(QColor(120, 200, 120))
                p.drawPath(stem)
            elif name == "sleep":
                moon = QPainterPath()
                center = icon.center()
                radius = min(icon.width(), icon.height()) / 2
                moon.addEllipse(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2))
                cut = QPainterPath()
                cut.addEllipse(QRectF(center.x() - radius * 0.2, center.y() - radius, radius * 2, radius * 2))
                moon = moon.subtracted(cut)
                p.setBrush(QColor(210, 220, 255))
                p.drawPath(moon)
                p.setBrush(QColor(170, 188, 250))
                star = QPainterPath()
                star.moveTo(center.x(), icon.top())
                star.lineTo(center.x() + SCALE * 0.8, icon.top() + SCALE * 1.4)
                star.lineTo(center.x(), icon.top() + SCALE * 1.6)
                star.lineTo(center.x() - SCALE * 0.8, icon.top() + SCALE * 1.4)
                star.closeSubpath()
                p.drawPath(star)
            else:  # potty
                bowl = QRectF(icon.left(), icon.top() + SCALE * 0.8, icon.width(), icon.height() - SCALE * 0.8)
                p.setBrush(QColor(210, 234, 220))
                p.drawRoundedRect(bowl, SCALE * 0.8, SCALE * 0.8)
                seat = QRectF(icon.left() + SCALE * 0.6, icon.top(), icon.width() - SCALE * 1.2, SCALE * 1.6)
                p.setBrush(QColor(240, 250, 240))
                p.drawRoundedRect(seat, SCALE * 0.6, SCALE * 0.6)
                handle = QRectF(bowl.right() - SCALE * 1.4, bowl.top() - SCALE * 0.6, SCALE * 0.8, SCALE * 1.4)
                p.setBrush(QColor(180, 216, 190))
                p.drawRoundedRect(handle, SCALE * 0.3, SCALE * 0.3)

            text_rect = rect.adjusted(0, btn_h / 2.0, 0, 0)
            p.setPen(QPen(QColor(40, 40, 60), 2))
            p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)

    def _draw_pet(self, p: QPainter, screen: QRectF):
        grid_left = int(screen.left() + SCALE * 2)
        grid_top = int(screen.top() + SCALE * 8)

        body_color = PALETTE["pet_body"]
        accent = PALETTE["pet_accent"]
        face_color = PALETTE["pet_face"]
        expr = self.expression()

        if expr == "bathroom":
            body_color = PALETTE["pet_bathroom"]
        elif expr == "hungry":
            body_color = PALETTE["pet_hungry"]
        elif expr == "sleepy":
            body_color = PALETTE["pet_sleepy"]

        accent_color = accent
        if expr == "sleepy":
            accent_color = accent.lighter(125)
        elif expr == "bathroom":
            accent_color = accent.darker(110)

        painter = p
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)

        def rect(x: int, y: int, w: int = 1, h: int = 1, color: QColor | None = None):
            brush = painter.brush()
            if color is not None:
                painter.setBrush(color)
            painter.fillRect(
                int(grid_left + x * SCALE),
                int(grid_top + y * SCALE),
                int(w * SCALE),
                int(h * SCALE),
                painter.brush(),
            )
            painter.setBrush(brush)

        painter.setBrush(body_color)
        for row in range(6, 22):
            width = 18 if 6 <= row <= 18 else 16
            offset = 5 if width == 18 else 6
            rect(offset, row, width, 1)
        rect(4, 10, 1, 8)
        rect(23, 10, 1, 8)

        # crown highlights
        painter.setBrush(accent_color)
        rect(6, 6, 16, 1)
        rect(7, 5, 14, 1)
        rect(8, 4, 12, 1)
        rect(9, 3, 10, 1)

        rect(7, 8, 4, 1, PALETTE["pet_highlight"])
        rect(6, 9, 3, 1, PALETTE["pet_highlight"])

        # cheeks
        rect(7, 15, 3, 2, PALETTE["pet_cheek"])
        rect(18, 15, 3, 2, PALETTE["pet_cheek"])

        # belly heart
        rect(12, 18, 2, 1, PALETTE["pet_highlight"])
        rect(11, 19, 4, 1, PALETTE["pet_highlight"])

        # feet hop animation
        foot_offset = (1, 0, 1, 0)[self.step_phase]
        rect(9, 23 + foot_offset, 4, 1, body_color.darker(130))
        rect(15, 23 - foot_offset, 4, 1, body_color.darker(130))

        painter.restore()
        painter.setBrush(face_color)
        painter.setPen(Qt.PenStyle.NoPen)
        eye_open = self.eye_open()

        if expr == "hungry":
            for eye_x in (10, 16):
                rect(eye_x, 13, 1, 1)
                rect(eye_x + 1, 12, 1, 1)
                rect(eye_x + 1, 14, 1, 1)
                rect(eye_x + 2, 13, 1, 1)
        elif expr == "sleepy":
            for eye_x in (10, 16):
                rect(eye_x, 14, 3, 1)
                rect(eye_x, 13, 3, 1, face_color.lighter(140))
                rect(eye_x, 15, 3, 1, face_color.lighter(120))
        else:
            height = 2 if eye_open > 0.4 else 1
            for eye_x in (10, 16):
                rect(eye_x, 13, 3, height)

        if expr == "bathroom":
            rect(12, 18, 6, 2)
            rect(12, 19, 6, 1, face_color.lighter(150))
        elif expr == "sleepy":
            rect(13, 19, 4, 1, face_color)
        else:
            mouth_y = 19 if expr == "hungry" else 18
            rect(13, mouth_y, 4, 1)


def make_icon() -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.RenderHint.Antialiasing)
    qp.setBrush(QColor(64, 64, 84))
    qp.setPen(Qt.PenStyle.NoPen)
    qp.drawRoundedRect(3, 3, 26, 26, 6, 6)
    qp.setBrush(PALETTE["pet_body"])
    qp.drawRect(9, 11, 14, 10)
    qp.setBrush(PALETTE["pet_face"])
    qp.drawRect(12, 14, 3, 2)
    qp.drawRect(17, 14, 3, 2)
    qp.drawRect(14, 18, 4, 1)
    qp.end()
    return QIcon(pm)


class App:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.window = PixelPetWindow()
        self.window.show()
        self.tray = QSystemTrayIcon(make_icon())
        menu = QMenu()
        quit_action = QAction("Quit")
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("Pixel Pal — cozy companion")
        self.tray.show()

    def run(self):
        sys.exit(self.app.exec())


if __name__ == "__main__":
    App().run()
