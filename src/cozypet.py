# src/cozypet.py — birdhouse layout (2×), sprites if present, pretty placeholders
import sys, math, os
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, QRectF, QSize
from PyQt6.QtGui import (
    QPainter, QBrush, QColor, QPen, QAction, QIcon, QPixmap, QFont,
    QLinearGradient, QRadialGradient
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QSystemTrayIcon, QMenu, QPushButton,
    QGraphicsOpacityEffect
)

# ========= Scaling =========
SCALE = 2              # 2× scene scale (192*2 = 384)
BASE_SCENE = 192
SCENE_SIZE = BASE_SCENE * SCALE

# ---- Frame/layout ----
PADDING   = 10
CHROME_H  = 24
OUTER_W   = PADDING*2 + SCENE_SIZE
OUTER_H   = PADDING*2 + CHROME_H + SCENE_SIZE
RADIUS    = 16   # outer bezel radius

# Scene anchors in BASE (192×192) coordinates
HOLE_C_BASE            = (BASE_SCENE // 2, 24)  # top-center hole (birdhouse)
HOLE_R_BASE            = 26
NEST_BASELINE_Y_BASE   = 168
SLOT_BACK_LEFT_BASE    = (60,  92)
SLOT_BACK_RIGHT_BASE   = (132, 92)
SLOT_FRONT_LEFT_BASE   = (84, 118)
SLOT_FRONT_RIGHT_BASE  = (112,118)

def S(v):  # scale helper
    if isinstance(v, tuple):
        return (v[0]*SCALE, v[1]*SCALE)
    return v * SCALE

HOLE_C           = S(HOLE_C_BASE)
HOLE_R           = S(HOLE_R_BASE)
NEST_BASELINE_Y  = S(NEST_BASELINE_Y_BASE)
SLOT_BACK_LEFT   = S(SLOT_BACK_LEFT_BASE)
SLOT_BACK_RIGHT  = S(SLOT_BACK_RIGHT_BASE)
SLOT_FRONT_LEFT  = S(SLOT_FRONT_LEFT_BASE)
SLOT_FRONT_RIGHT = S(SLOT_FRONT_RIGHT_BASE)

# ---- Palette (for vector fallbacks / chrome) ----
INK     = QColor(18, 19, 22)
WOOD_1  = QColor(138, 114, 82)   # fallback bg top
WOOD_2  = QColor(112, 91, 65)    # fallback bg bottom
ACCENT  = QColor(224, 196, 120)  # straw
ACCENT_2= QColor(168, 140, 88)
EGG_1   = QColor(255, 245, 224)  # egg highlight
EGG_2   = QColor(244, 229, 199)  # egg base
EGG_3   = QColor(210, 190, 156)  # egg shadow

# ---- Sprite theme ----
THEME = os.getenv("COZYPET_THEME", "theme_birdhouse")   # default: birdhouse vibe
ROOT = Path(__file__).resolve().parent.parent
SPRITES = ROOT / "assets" / "sprites" / THEME

def load_pix(path: Path) -> QPixmap | None:
    if not path.exists(): return None
    pm = QPixmap(str(path))
    return pm if not pm.isNull() else None

def load_frames(dirpath: Path, prefix: str = "") -> list[QPixmap]:
    if not dirpath.exists(): return []
    files = sorted([p for p in dirpath.iterdir() if p.suffix.lower() == ".png"])
    if prefix:
        files = [p for p in files if p.stem.startswith(prefix)]
    frames = []
    for p in files:
        pm = load_pix(p)
        if pm: frames.append(pm)
    return frames

def paint_light_and_vignette(p: QPainter, scene_rect: QRectF, hole_cx: float, hole_cy: float, radius: float, scale: int):
    # Glow around hole
    glow = QRadialGradient(hole_cx, hole_cy, radius*2)
    glow.setColorAt(0.00, QColor(255, 255, 240, 190))
    glow.setColorAt(0.35, QColor(255, 255, 220, 120))
    glow.setColorAt(0.70, QColor(255, 255, 220,  40))
    glow.setColorAt(1.00, QColor(255, 255, 220,   0))
    p.setBrush(QBrush(glow)); p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(hole_cx - radius*2, hole_cy - radius*2, radius*4, radius*4))

    # Downward light cone
    g = QLinearGradient(hole_cx, hole_cy, hole_cx, scene_rect.bottom())
    g.setColorAt(0.00, QColor(255, 255, 230, 110))
    g.setColorAt(0.25, QColor(255, 255, 230,  60))
    g.setColorAt(0.60, QColor(255, 255, 230,  20))
    g.setColorAt(1.00, QColor(255, 255, 230,   0))
    p.setBrush(QBrush(g)); p.setPen(Qt.PenStyle.NoPen)
    cone_w = 160 * scale
    p.drawRoundedRect(QRectF(hole_cx - cone_w/2, hole_cy, cone_w, scene_rect.bottom() - hole_cy), 40, 40)

    # Vignette
    p.save()
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(0,0,0,140), 40*scale))
    p.drawRoundedRect(scene_rect.adjusted(20, 20, -20, -20), 12*scale, 12*scale)
    p.restore()

class TopChrome(QWidget):
    """Hover chrome bar that fades in/out and hosts a close button."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(CHROME_H)

        self.btn = QPushButton("✕", self)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setFixedSize(18, 18)
        self.btn.move(OUTER_W - PADDING - self.btn.width(), (CHROME_H - self.btn.height())//2)
        self.btn.setStyleSheet("""
            QPushButton { border: none; color: #eee; background: rgba(255,255,255,35); border-radius: 9px; }
            QPushButton:hover { background: rgba(255,255,255,65); }
            QPushButton:pressed { background: rgba(255,255,255,95); }
        """)

        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self._opacity = 0.0
        self.effect.setOpacity(self._opacity)
        self.setVisible(False)

        self._target_opacity = 0.0
        self._fade = QTimer(self)
        self._fade.setInterval(16)
        self._fade.timeout.connect(self._tick_fade)

    def _tick_fade(self):
        step = 0.12 if self._target_opacity > self._opacity else -0.12
        self._opacity = max(0.0, min(1.0, self._opacity + step))
        self.effect.setOpacity(self._opacity)
        self.setVisible(self._opacity > 0.01)
        if abs(self._opacity - self._target_opacity) < 0.02:
            self._fade.stop()
            self._opacity = self._target_opacity
            self.effect.setOpacity(self._opacity)
            self.setVisible(self._opacity > 0.01)

    def set_target(self, op: float):
        self._target_opacity = max(0.0, min(1.0, op))
        self._fade.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar = QRectF(0, 0, OUTER_W, CHROME_H)
        p.setBrush(QBrush(QColor(20, 20, 24, 190)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(bar, RADIUS, RADIUS)

class CozyWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cozy Pet")
        self.setFixedSize(OUTER_W, OUTER_H)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Drag support
        self._drag = None

        # Animation tick (wiggle + sprite cycling)
        self.phase = 0.0
        self.anim = QTimer(self)
        self.anim.timeout.connect(self.on_anim)
        self.anim.start(120)  # ~8 FPS vibe
        self.frame_tick = 0

        # Hover chrome
        self.chrome = TopChrome(self)
        self.chrome.move(0, 0)
        self.chrome.btn.clicked.connect(QApplication.instance().quit)

        # Load sprites (optional)
        self.bg = load_pix(SPRITES / "bg.png")
        self.nest = load_pix(SPRITES / "nest.png")
        self.hole_overlay = load_pix(SPRITES / "hole.png")
        self.egg_idle = load_frames(SPRITES / "egg", "idle_")

        # Place window near bottom-right of primary screen
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - self.width() - 40, scr.bottom() - self.height() - 80)

    # ---- Events ----
    def enterEvent(self, _):
        self.chrome.set_target(1.0)

    def leaveEvent(self, _):
        self.chrome.set_target(0.0)

    def on_anim(self):
        self.phase = (self.phase + 0.25) % (2*math.pi)
        self.frame_tick += 1
        self.update()

    # ---- Painting ----
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Outer bezel
        panel_rect = QRectF(0, 0, OUTER_W, OUTER_H)
        p.setBrush(QBrush(INK))
        p.setPen(QPen(QColor(255, 255, 255, 35), 1.2))
        p.drawRoundedRect(panel_rect, RADIUS, RADIUS)
        inset = panel_rect.adjusted(1.5, 1.5, -1.5, -1.5)
        p.setPen(QPen(QColor(0, 0, 0, 140), 1))
        p.drawRoundedRect(inset, RADIUS-2, RADIUS-2)

        # Scene rect
        scene_rect = QRectF(PADDING, PADDING + CHROME_H, SCENE_SIZE, SCENE_SIZE)

        # Background: sprite or wood gradient placeholder
        if self.bg:
            p.drawPixmap(scene_rect.toRect(), self.bg)
        else:
            grad = QLinearGradient(scene_rect.topLeft(), scene_rect.bottomLeft())
            grad.setColorAt(0.0, WOOD_1); grad.setColorAt(1.0, WOOD_2)
            p.setBrush(QBrush(grad)); p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(scene_rect, 12*SCALE, 12*SCALE)

        # Hole (top center)
        hole_cx = scene_rect.x() + HOLE_C[0]
        hole_cy = scene_rect.y() + HOLE_C[1]
        p.setBrush(QBrush(QColor(10, 10, 12)))
        p.setPen(QPen(QColor(0, 0, 0, 220), 2))
        p.drawEllipse(QRectF(hole_cx - HOLE_R, hole_cy - HOLE_R, HOLE_R*2, HOLE_R*2))
        if self.hole_overlay:
            r = self.hole_overlay.rect()
            pm = self.hole_overlay.scaled(QSize(r.width()*SCALE, r.height()*SCALE),
                                          Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
            rr = pm.rect()
            p.drawPixmap(int(hole_cx - rr.width()/2), int(hole_cy - rr.height()/2), pm)

        # Light cone + vignette
        paint_light_and_vignette(p, scene_rect, hole_cx, hole_cy, HOLE_R, SCALE)

        # Nest: sprite or straw placeholder
        if self.nest:
            r = self.nest.rect()
            pm = self.nest.scaled(QSize(r.width()*SCALE, r.height()*SCALE),
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
            rr = pm.rect()
            x = int(scene_rect.center().x() - rr.width()/2)
            y = int(scene_rect.y() + NEST_BASELINE_Y - rr.height())
            p.drawPixmap(x, y, pm)
        else:
            nest_y = scene_rect.y() + NEST_BASELINE_Y
            p.setPen(QPen(ACCENT_2, 5*SCALE, cap=Qt.PenCapStyle.RoundCap))
            for dx in (-50, -22, 6, 34):
                p.drawArc(int(scene_rect.center().x() - 64*SCALE + dx*SCALE),
                          int(nest_y - 28*SCALE + (dx % 4)),
                          128*SCALE, 48*SCALE, 0, 180*16)
            p.setPen(QPen(ACCENT, 4*SCALE, cap=Qt.PenCapStyle.RoundCap))
            for dx in (-46, -18, 10, 38):
                p.drawArc(int(scene_rect.center().x() - 64*SCALE + dx*SCALE),
                          int(nest_y - 24*SCALE + (dx % 3)),
                          128*SCALE, 48*SCALE, 0, 180*16)
            p.setPen(QPen(ACCENT, 3*SCALE))
            for xoff in (-34, -16, 2, 18, 34):
                p.drawLine(int(scene_rect.center().x()+xoff*SCALE), int(nest_y-4*SCALE),
                           int(scene_rect.center().x()+xoff*SCALE+10*SCALE), int(nest_y+10*SCALE))

        # Egg (sprite frames or vector fallback), positioned on front-left slot
        wiggle = math.sin(self.phase) * (1.2*SCALE)
        egg_cx, egg_cy = SLOT_FRONT_LEFT
        egg_px = scene_rect.x() + egg_cx + wiggle
        egg_py = scene_rect.y() + egg_cy

        if self.egg_idle:
            idx = (self.frame_tick // 3) % len(self.egg_idle)
            base = self.egg_idle[idx]
            r = base.rect()
            pm = base.scaled(QSize(r.width()*SCALE, r.height()*SCALE),
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            rr = pm.rect()
            x = int(egg_px - rr.width()/2)
            y = int(egg_py - rr.height()/2 - 6*SCALE)
            p.setBrush(QBrush(QColor(0, 0, 0, 80))); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(x + rr.width()/2 - 19*SCALE, y + rr.height() - 6*SCALE, 38*SCALE, 10*SCALE))
            p.drawPixmap(x, y, pm)
        else:
            egg_x = egg_px - 16*SCALE
            egg_y = egg_py - 22*SCALE
            p.setBrush(QBrush(QColor(0, 0, 0, 80))); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(egg_x - 3*SCALE, egg_y + 32*SCALE, 38*SCALE, 10*SCALE))
            p.setBrush(QBrush(EGG_2)); p.setPen(QPen(QColor(80, 80, 80), 1*SCALE))
            p.drawEllipse(QRectF(egg_x, egg_y, 32*SCALE, 44*SCALE))
            p.setBrush(QBrush(EGG_1)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(egg_x + 6*SCALE, egg_y + 6*SCALE, 16*SCALE, 20*SCALE))
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(EGG_3, 2*SCALE))
            p.drawArc(int(egg_x), int(egg_y + 10*SCALE), 32*SCALE, 26*SCALE, -40*16, -110*16)

        # debug label (remove later)
        p.setPen(QPen(QColor(255,255,255,80), 1*SCALE))
        p.setFont(QFont("Helvetica", 8*SCALE))
        p.drawText(int(scene_rect.x()+8*SCALE), int(scene_rect.y()+16*SCALE),
                   f"cozy scene {SCENE_SIZE}×{SCENE_SIZE}")

    # ---- Drag to move ----
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if self._drag and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)
    def mouseReleaseEvent(self, e):
        self._drag = None


# ---- Tray wrapper ----
def make_simple_icon() -> QIcon:
    pm = QPixmap(32, 32); pm.fill(Qt.GlobalColor.transparent)
    qp = QPainter(pm); qp.setRenderHint(QPainter.RenderHint.Antialiasing)
    qp.setBrush(QBrush(QColor(255, 240, 200))); qp.setPen(QPen(QColor(60, 60, 60), 2))
    qp.drawEllipse(3, 3, 26, 26); qp.end()
    return QIcon(pm)

class App:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.win = CozyWindow(); self.win.show()
        self.tray = QSystemTrayIcon(make_simple_icon())
        menu = QMenu()
        quit_action = QAction("Quit"); quit_action.triggered.connect(self.app.quit); menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("CozyPet — birdhouse layout (2×)")
        self.tray.show()
    def run(self):
        sys.exit(self.app.exec())

if __name__ == "__main__":
    App().run()
