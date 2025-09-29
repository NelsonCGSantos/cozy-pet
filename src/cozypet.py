# src/cozypet.py — birdhouse layout (2×), sprites if present, pretty placeholders
import sys, math, os, random
from pathlib import Path
from dataclasses import dataclass, field
from itertools import count
from PyQt6.QtCore import Qt, QTimer, QRectF, QSize, QPointF
from PyQt6.QtGui import (
    QPainter, QBrush, QColor, QPen, QAction, QIcon, QPixmap, QFont,
    QLinearGradient, QRadialGradient, QPolygonF, QPainterPath
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

SLOTS = [
    ("front_left", SLOT_FRONT_LEFT),
    ("front_right", SLOT_FRONT_RIGHT),
    ("back_left", SLOT_BACK_LEFT),
    ("back_right", SLOT_BACK_RIGHT),
]

# ---- Palette (for vector fallbacks / chrome) ----
INK     = QColor(18, 19, 22)
WOOD_1  = QColor(138, 114, 82)   # fallback bg top
WOOD_2  = QColor(112, 91, 65)    # fallback bg bottom
ACCENT  = QColor(224, 196, 120)  # straw
ACCENT_2= QColor(168, 140, 88)
EGG_1   = QColor(255, 245, 224)  # egg highlight
EGG_2   = QColor(244, 229, 199)  # egg base
EGG_3   = QColor(210, 190, 156)  # egg shadow

_BIRD_ID = count()


@dataclass
class ScenePalette:
    wood_top: QColor
    wood_mid: QColor
    wood_bottom: QColor
    wood_shadow: QColor
    wood_highlight: QColor
    straw_light: QColor
    straw_dark: QColor
    straw_shadow: QColor
    dust: QColor
    overlay_bg: QColor
    overlay_outline: QColor
    overlay_text: QColor


def make_scene_palette(rng: random.Random) -> ScenePalette:
    hue = rng.randint(24, 40)
    wood_top = QColor.fromHsl(hue, 110, 170)
    wood_mid = QColor.fromHsl(max(15, hue - 4), 90, 150)
    wood_bottom = QColor.fromHsl(max(10, hue - 8), 80, 125)
    shadow = QColor.fromHsl(max(0, hue - 12), 130, 80)
    highlight = wood_top.lighter(130)
    straw_hue = hue + rng.randint(18, 32)
    straw_light = QColor.fromHsl(straw_hue, 160, 200)
    straw_dark = QColor.fromHsl(straw_hue - 8, 140, 170)
    straw_shadow = QColor.fromHsl(straw_hue - 16, 180, 110)
    dust = QColor(255, 248, 230, 90)
    overlay_bg = QColor(32, 25, 18, 200)
    overlay_outline = QColor(0, 0, 0, 130)
    overlay_text = QColor(248, 244, 238)
    return ScenePalette(
        wood_top, wood_mid, wood_bottom, shadow, highlight,
        straw_light, straw_dark, straw_shadow, dust,
        overlay_bg, overlay_outline, overlay_text,
    )


SEASON_BASES = [
    QColor(244, 214, 120),
    QColor(118, 176, 228),
]


def season_base_color(season: int, rng: random.Random) -> QColor:
    if season <= len(SEASON_BASES):
        return QColor(SEASON_BASES[season - 1])
    h = rng.randint(0, 359)
    s = rng.randint(120, 180)
    l = rng.randint(150, 200)
    return QColor.fromHsl(h, s, l)


def build_bird_palette(base: QColor, rng: random.Random) -> tuple[dict[str, QColor], str]:
    primary = QColor(base)
    highlight = QColor(primary).lighter(rng.randint(125, 150))
    accent = QColor(primary).darker(rng.randint(140, 170))
    deep = QColor(28, 28, 32)
    beak = QColor(206, 164, 88)
    pattern = rng.choice(["mask", "wing", "belly", "speck"])
    colors = {
        "body": primary,
        "belly": highlight,
        "wing": primary,
        "head": primary,
        "speck": accent,
        "beak": beak,
        "eye": deep,
        "accent": accent,
    }
    if pattern == "mask":
        colors["head"] = accent
    elif pattern == "wing":
        colors["wing"] = accent
    elif pattern == "belly":
        colors["belly"] = accent.lighter(115)
    else:
        colors["speck"] = accent
    return colors, pattern


@dataclass
class Bird:
    slot_name: str
    slot: tuple[int, int]
    palette: dict[str, QColor]
    pattern: str
    stage: str = "egg"
    age: int = 0
    hatch_ticks: int = 0
    grow_ticks: int = 0
    wiggle_offset: float = 0.0
    id: int = field(default_factory=lambda: next(_BIRD_ID))
    action: str | None = None
    action_timer: int = 0
    action_duration: int = 0

    def advance(self):
        self.age += 1
        if self.stage == "egg" and self.age >= self.hatch_ticks:
            self.stage = "hatchling"
            self.age = 0
        elif self.stage == "hatchling" and self.age >= self.grow_ticks:
            self.stage = "adult"
            self.age = 0
        if self.action:
            self.action_timer += 1
            if self.action_timer >= self.action_duration:
                self.action = None
                self.action_timer = 0
                self.action_duration = 0

    def start_action(self, name: str, duration: int):
        self.action = name
        self.action_duration = duration
        self.action_timer = 0


class AviarySim:
    TICKS_PER_DAY = 10
    SPAWN_DELAY = 35
    RESET_DELAY = 55

    def __init__(self):
        self.rng = random.Random()
        self.season = 1
        self.day = 1
        self.tick = 0
        self.spawn_timer = 0
        self.reset_timer = 0
        self.birds: list[Bird] = []
        self.just_reset = False
        self.season_rng = random.Random()
        self.season_color = QColor(SEASON_BASES[0])
        self.next_action = 0
        self.reset_season()

    def reset_season(self):
        self.day = 1
        self.tick = 0
        self.spawn_timer = 0
        self.reset_timer = 0
        self.birds = []
        seed = self.rng.randint(0, 1_000_000)
        self.season_rng = random.Random(seed)
        self.season_color = season_base_color(self.season, self.season_rng)
        self._spawn_egg(initial=True)
        self.just_reset = True
        self.next_action = self._action_cooldown()

    def _occupied_slots(self) -> set[str]:
        return {b.slot_name for b in self.birds}

    def _next_slot(self) -> tuple[str, tuple[int, int]] | None:
        available = [s for s in SLOTS if s[0] not in self._occupied_slots()]
        return available[0] if available else None

    def _spawn_egg(self, *, initial: bool = False):
        nxt = self._next_slot()
        if not nxt:
            return
        name, coord = nxt
        rng = random.Random(self.rng.randint(0, 1_000_000))
        palette, pattern = build_bird_palette(self.season_color, rng)
        wiggle = rng.random() * math.tau
        hatch = self.rng.randint(50, 90)
        grow = self.rng.randint(80, 130)
        self.birds.append(
            Bird(
                slot_name=name,
                slot=coord,
                palette=palette,
                pattern=pattern,
                hatch_ticks=hatch,
                grow_ticks=grow,
                wiggle_offset=wiggle,
            )
        )
        if not initial:
            self.spawn_timer = 0

    def tick_once(self) -> bool:
        season_reset = False
        self.tick += 1
        if self.tick % self.TICKS_PER_DAY == 0:
            self.day += 1

        adults = 0
        for bird in self.birds:
            bird.advance()
            if bird.stage == "adult":
                adults += 1

        if len(self.birds) < 4:
            if adults > 0:
                self.spawn_timer += 1
                if self.spawn_timer >= self.SPAWN_DELAY:
                    self._spawn_egg()
            else:
                self.spawn_timer = 0

        if len(self.birds) == 4 and adults == 4:
            self.reset_timer += 1
            if self.reset_timer >= self.RESET_DELAY:
                self.season += 1
                self.reset_season()
                season_reset = True
        else:
            self.reset_timer = 0

        if self.next_action > 0:
            self.next_action -= 1
        else:
            self._try_trigger_action()
            self.next_action = self._action_cooldown()

        jr = self.just_reset
        self.just_reset = False
        return season_reset or jr

    def _action_cooldown(self) -> int:
        return self.rng.randint(2400, 3200)

    def _try_trigger_action(self):
        choices = [b for b in self.birds if b.stage in {"hatchling", "adult"} and not b.action]
        if not choices:
            return
        bird = self.rng.choice(choices)
        if bird.stage == "hatchling":
            action = self.rng.choice(["hop", "shake"])
        else:
            action = self.rng.choice(["drink", "preen", "hop", "shake"])
        bird.start_action(action, self.rng.randint(80, 120))

# ---- Sprite theme ----
THEME = os.getenv("COZYPET_THEME", "theme_birdhouse")   # default: birdhouse vibe
ROOT = Path(__file__).resolve().parent.parent
SPRITES = ROOT / "assets" / "sprites" / THEME

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
        self.sim = AviarySim()
        self.visual_rng = random.Random()
        self.decor_seed = 0
        self.scene_palette = make_scene_palette(self.visual_rng)
        self._refresh_scene_ornaments()

        # Hover chrome
        self.chrome = TopChrome(self)
        self.chrome.move(0, 0)
        self.chrome.btn.clicked.connect(QApplication.instance().quit)

        # Load sprites (optional)

        # Place window near bottom-right of primary screen
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - self.width() - 40, scr.bottom() - self.height() - 80)

    def _refresh_scene_ornaments(self):
        self.decor_seed = self.visual_rng.randint(0, 1_000_000)
        rng = random.Random(self.decor_seed)

        self.wall_grains: list[dict[str, float]] = []
        for _ in range(6):
            self.wall_grains.append({
                "x": rng.uniform(0.05, 0.94),
                "width": rng.uniform(0.015, 0.045),
                "alpha": rng.randint(35, 80),
                "highlight": rng.choice((True, False))
            })

        self.wall_scratches: list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]] = []
        for _ in range(3):
            start = (rng.uniform(0.12, 0.88), rng.uniform(0.4, 0.78))
            ctrl = (start[0] + rng.uniform(-0.08, 0.08), start[1] + rng.uniform(0.08, 0.16))
            end = (start[0] + rng.uniform(-0.12, 0.12), min(0.98, start[1] + rng.uniform(0.14, 0.22)))
            self.wall_scratches.append((start, ctrl, end))

        self.floor_panels: list[tuple[float, float, float]] = []
        for _ in range(4):
            cx = rng.uniform(0.25, 0.75)
            w = rng.uniform(0.22, 0.34)
            shade = rng.uniform(0.18, 0.38)
            self.floor_panels.append((cx, w, shade))

        self.dust_motes: list[tuple[float, float, float, float]] = []
        for _ in range(14):
            self.dust_motes.append((
                rng.uniform(0.2, 0.8),
                rng.uniform(0.08, 0.6),
                rng.uniform(1.8, 3.6),
                rng.uniform(0, math.tau)
            ))

    # ---- Events ----
    def enterEvent(self, _):
        self.chrome.set_target(1.0)

    def leaveEvent(self, _):
        self.chrome.set_target(0.0)

    def on_anim(self):
        self.phase = (self.phase + 0.25) % (2*math.pi)
        self.frame_tick += 1
        season_reset = self.sim.tick_once()
        if season_reset:
            self.scene_palette = make_scene_palette(self.visual_rng)
            self._refresh_scene_ornaments()
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

        # Scene layers
        self.draw_background(p, scene_rect)
        self.draw_nest(p, scene_rect)
        self.draw_floating_dust(p, scene_rect)

        # Render birds (eggs → family)
        occupants = sorted(self.sim.birds, key=lambda b: b.slot[1])
        for bird in occupants:
            self.draw_occupant(p, scene_rect, bird)

        self.draw_overlay(p, scene_rect)

    def draw_background(self, p: QPainter, scene_rect: QRectF):
        palette = self.scene_palette
        grad = QLinearGradient(scene_rect.topLeft(), scene_rect.bottomLeft())
        grad.setColorAt(0.0, palette.wood_top)
        grad.setColorAt(0.55, palette.wood_mid)
        grad.setColorAt(1.0, palette.wood_bottom)
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(scene_rect, 16*SCALE, 16*SCALE)

        vignette = QLinearGradient(scene_rect.topLeft(), scene_rect.bottomRight())
        shadow = QColor(palette.wood_shadow)
        shadow.setAlpha(60)
        vignette.setColorAt(0.0, Qt.GlobalColor.transparent)
        vignette.setColorAt(1.0, shadow)
        p.setBrush(QBrush(vignette))
        p.drawRoundedRect(scene_rect.adjusted(2*SCALE, 2*SCALE, -2*SCALE, -2*SCALE), 14*SCALE, 14*SCALE)

        for grain in self.wall_grains:
            color = QColor(palette.wood_highlight if grain["highlight"] else palette.wood_shadow)
            color.setAlpha(int(grain["alpha"]))
            gx = scene_rect.x() + scene_rect.width() * grain["x"]
            gw = scene_rect.width() * grain["width"]
            rect = QRectF(gx - gw/2, scene_rect.y() + 18*SCALE, gw, scene_rect.height() - 36*SCALE)
            p.setBrush(QBrush(color))
            p.drawRect(rect)

        scratch_color = QColor(palette.wood_shadow)
        scratch_color.setAlpha(120)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(scratch_color, 1.4*SCALE, cap=Qt.PenCapStyle.RoundCap))
        for start, ctrl, end in self.wall_scratches:
            path = QPainterPath()
            path.moveTo(scene_rect.x() + scene_rect.width()*start[0], scene_rect.y() + scene_rect.height()*start[1])
            path.quadTo(scene_rect.x() + scene_rect.width()*ctrl[0], scene_rect.y() + scene_rect.height()*ctrl[1],
                        scene_rect.x() + scene_rect.width()*end[0], scene_rect.y() + scene_rect.height()*end[1])
            p.drawPath(path)

        edge_highlight = QColor(palette.wood_highlight)
        edge_highlight.setAlpha(70)
        p.setPen(QPen(edge_highlight, 3.5*SCALE))
        p.drawRoundedRect(scene_rect.adjusted(6*SCALE, 6*SCALE, -6*SCALE, -6*SCALE), 12*SCALE, 12*SCALE)

    def draw_nest(self, p: QPainter, scene_rect: QRectF):
        palette = self.scene_palette
        floor_y = scene_rect.y() + scene_rect.height() * 0.82

        base_shadow = QColor(palette.wood_shadow)
        base_shadow.setAlpha(120)
        p.setBrush(QBrush(base_shadow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(scene_rect.center().x() - 100*SCALE, floor_y - 4*SCALE, 200*SCALE, 28*SCALE))

        cushion = QRectF(scene_rect.center().x() - 92*SCALE, floor_y - 18*SCALE, 184*SCALE, 30*SCALE)
        pad_grad = QLinearGradient(cushion.topLeft(), cushion.bottomLeft())
        pad_grad.setColorAt(0.0, palette.straw_dark.lighter(120))
        pad_grad.setColorAt(1.0, palette.straw_dark.darker(120))
        p.setBrush(QBrush(pad_grad))
        p.drawRoundedRect(cushion, 18*SCALE, 18*SCALE)

        lip_color = QColor(palette.straw_light)
        lip_color.setAlpha(150)
        p.setPen(QPen(lip_color, 4*SCALE, cap=Qt.PenCapStyle.RoundCap))
        lip_rect = cushion.adjusted(12*SCALE, 6*SCALE, -12*SCALE, -4*SCALE)
        p.drawArc(lip_rect, 12*16, 156*16)

        grain_color = QColor(palette.straw_shadow)
        for cx, width_ratio, shade in self.floor_panels:
            width = scene_rect.width() * width_ratio
            rx = scene_rect.x() + scene_rect.width() * cx - width/2
            panel = QRectF(rx, floor_y - 8*SCALE, width, 12*SCALE)
            color = QColor(grain_color)
            color.setAlpha(int(80 + shade * 60))
            p.setBrush(QBrush(color))
            p.drawRoundedRect(panel, 6*SCALE, 6*SCALE)

    def draw_floating_dust(self, p: QPainter, scene_rect: QRectF):
        base_color = QColor(self.scene_palette.dust)
        p.setPen(Qt.PenStyle.NoPen)
        for x_pct, y_pct, radius, phase in self.dust_motes:
            oscillation = math.sin(phase + self.frame_tick * 0.05)
            color = QColor(base_color)
            color.setAlpha(70 + int(60 * max(0.0, oscillation + 1) / 2))
            px = scene_rect.x() + scene_rect.width() * x_pct
            py = scene_rect.y() + scene_rect.height() * y_pct + oscillation * 6
            p.setBrush(QBrush(color))
            p.drawEllipse(QRectF(px - radius, py - radius, radius*2, radius*2))

    def draw_overlay(self, p: QPainter, scene_rect: QRectF):
        palette = self.scene_palette
        title = f"DAY {self.sim.day}"
        font = QFont("Futura", 20*SCALE)
        font.setBold(True)
        p.setFont(font)
        text_rect = p.boundingRect(scene_rect.toRect(), Qt.AlignmentFlag.AlignCenter, title)
        text_rect.moveTop(int(scene_rect.y() + 10*SCALE))

        bubble_rect = text_rect.adjusted(-18, -12, 18, 12)
        bg = QColor(palette.overlay_bg)
        outline = QColor(palette.overlay_outline)
        p.setBrush(QBrush(bg))
        p.setPen(QPen(outline, 2*SCALE))
        p.drawRoundedRect(bubble_rect, 18, 18)

        shadow_rect = QRectF(text_rect)
        shadow_rect.translate(2*SCALE, 2*SCALE)
        p.setPen(QPen(QColor(0, 0, 0, 220), 4*SCALE))
        p.drawText(shadow_rect, Qt.AlignmentFlag.AlignCenter, title)

        p.setPen(QPen(palette.overlay_text, 4*SCALE))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, title)

        info_font = QFont("Futura", 11*SCALE)
        info_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1*SCALE)
        p.setFont(info_font)
        season_text = f"Season {self.sim.season}" \
            f"  ·  Flock {len(self.sim.birds)}/4"
        info_color = QColor(palette.overlay_text)
        info_color.setAlpha(210)
        p.setPen(QPen(info_color, 2*SCALE))
        p.drawText(int(scene_rect.x()+16*SCALE), int(scene_rect.bottom()-16*SCALE), season_text)

    def draw_occupant(self, p: QPainter, scene_rect: QRectF, bird: Bird):
        cx = scene_rect.x() + bird.slot[0]
        cy = scene_rect.y() + bird.slot[1]
        wobble = math.sin(self.phase + bird.wiggle_offset)
        rng = random.Random(bird.id)
        action = bird.action or ""
        prog = bird.action_timer / max(1, bird.action_duration) if bird.action else 0.0
        ease = math.sin(min(1.0, prog) * math.pi) if bird.action else 0.0
        offset_x = 0.0
        offset_y = 0.0
        head_dx = 0.0
        head_dy = 0.0
        wing_lift = 0.0
        if action == "drink":
            offset_x -= 12*SCALE * ease
            head_dx -= 6*SCALE * ease
            head_dy += 14*SCALE * ease
        elif action == "preen":
            swing = math.sin(prog * math.pi * 2)
            head_dx += swing * 8*SCALE
            head_dy += 6*SCALE * ease
            wing_lift = 6*SCALE * ease
        elif action == "hop":
            offset_y -= 12*SCALE * math.sin(prog * math.pi)
        elif action == "shake":
            head_dx += math.sin(prog * math.pi * 4) * 10*SCALE

        cx2 = cx + offset_x
        cy2 = cy + offset_y
        p.save()

        if bird.stage == "egg":
            wob = wobble * (1.1*SCALE)
            egg_rect = QRectF(cx - 16*SCALE + wob, cy - 28*SCALE, 32*SCALE, 46*SCALE)
            shadow = QRectF(cx - 20*SCALE, cy + 14*SCALE, 40*SCALE, 14*SCALE)
            p.setBrush(QBrush(QColor(0, 0, 0, 95)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(shadow)

            shell = QLinearGradient(egg_rect.topLeft(), egg_rect.bottomRight())
            shell.setColorAt(0.0, QColor(255, 248, 234))
            shell.setColorAt(0.5, QColor(246, 232, 210))
            shell.setColorAt(1.0, QColor(222, 204, 180))
            p.setBrush(QBrush(shell))
            rim = QColor(198, 182, 160)
            p.setPen(QPen(rim, 1.2*SCALE))
            p.drawEllipse(egg_rect)

            highlight = QPainterPath()
            highlight.addEllipse(egg_rect.adjusted(6*SCALE, 8*SCALE, -18*SCALE, -26*SCALE))
            p.setBrush(QBrush(QColor(255, 255, 255, 115)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(highlight)

            progress = min(1.0, bird.age / max(1, bird.hatch_ticks))
            if progress > 0.45:
                crack = QPainterPath()
                crack.moveTo(cx - 5*SCALE + wob, egg_rect.center().y() - 2*SCALE)
                crack.quadTo(cx, egg_rect.center().y() + 4*SCALE,
                             cx + 4*SCALE, egg_rect.center().y() - 1*SCALE)
                crack_color = QColor(160, 136, 112)
                crack_color.setAlpha(180)
                p.setPen(QPen(crack_color, 1.4*SCALE, cap=Qt.PenCapStyle.RoundCap))
                p.drawPath(crack)
                if progress > 0.75:
                    p.drawLine(QPointF(cx - 3*SCALE, egg_rect.center().y() + 4*SCALE),
                               QPointF(cx - 6*SCALE, egg_rect.center().y() + 10*SCALE))

        elif bird.stage == "hatchling":
            bob = wobble * (1.8*SCALE)
            body_rect = QRectF(cx2 - 17*SCALE, cy2 - 16*SCALE + bob, 34*SCALE, 26*SCALE)
            head_rect = QRectF(cx2 - 14*SCALE + head_dx, cy2 - 36*SCALE + bob + head_dy, 28*SCALE, 24*SCALE)
            shadow = QRectF(cx2 - 20*SCALE, cy2 + 8*SCALE, 40*SCALE, 12*SCALE)
            p.setBrush(QBrush(QColor(0, 0, 0, 80)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(shadow)

            body_grad = QLinearGradient(body_rect.topLeft(), body_rect.bottomRight())
            body_grad.setColorAt(0.0, bird.palette["body"].lighter(120))
            body_grad.setColorAt(1.0, bird.palette["body"].darker(120))
            p.setBrush(QBrush(body_grad))
            p.drawEllipse(body_rect)

            head_grad = QLinearGradient(head_rect.topLeft(), head_rect.bottomRight())
            head_grad.setColorAt(0.0, bird.palette["head"].lighter(130))
            head_grad.setColorAt(1.0, bird.palette["head"].darker(120))
            p.setBrush(QBrush(head_grad))
            p.drawEllipse(head_rect)

            belly = body_rect.adjusted(6*SCALE, 8*SCALE, -6*SCALE, -6*SCALE)
            belly_grad = QLinearGradient(belly.topLeft(), belly.bottomRight())
            belly_grad.setColorAt(0.0, bird.palette["belly"].lighter(110))
            belly_grad.setColorAt(1.0, bird.palette["belly"].darker(110))
            p.setBrush(QBrush(belly_grad))
            p.drawEllipse(belly)

            wing_pen = QPen(bird.palette["wing"], 4.4*SCALE, cap=Qt.PenCapStyle.RoundCap)
            wing_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(wing_pen)
            for direction in (-1, 1):
                path = QPainterPath()
                ctrl_x = cx2 + direction * (16*SCALE - wing_lift)
                ctrl_y = cy2 + 4*SCALE + bob - wing_lift * 0.4
                end_x = cx2 + direction * 8*SCALE
                end_y = cy2 + 16*SCALE
                path.moveTo(cx2 + direction * 3*SCALE, cy2 - 4*SCALE + bob)
                path.quadTo(ctrl_x, ctrl_y, end_x, end_y)
                p.drawPath(path)

            if bird.pattern == "speck":
                p.setBrush(QBrush(bird.palette["speck"].lighter(120)))
                p.setPen(Qt.PenStyle.NoPen)
                for i in range(3):
                    px = cx2 + rng.uniform(-6, 6) * SCALE
                    py = cy2 - 6*SCALE + i * 4*SCALE
                    p.drawEllipse(QRectF(px, py, 3*SCALE, 3*SCALE))

            beak_points = [
                (cx2, head_rect.y() + 10*SCALE + head_dy),
                (cx2 + 6*SCALE, head_rect.y() + 16*SCALE + head_dy),
                (cx2 - 6*SCALE, head_rect.y() + 16*SCALE + head_dy),
            ]
            beak_poly = QPolygonF([QPointF(x, y) for x, y in beak_points])
            p.setBrush(QBrush(bird.palette["beak"].lighter(120)))
            p.setPen(QPen(bird.palette["beak"].darker(140), 1.4*SCALE))
            p.drawPolygon(beak_poly)

            eye_r = 2.6*SCALE
            eye_y = head_rect.y() + 10*SCALE
            p.setBrush(QBrush(bird.palette["eye"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(cx2 - 5*SCALE + head_dx, eye_y, eye_r, eye_r))
            p.drawEllipse(QRectF(cx2 + 2*SCALE + head_dx, eye_y, eye_r, eye_r))
            p.setBrush(QBrush(QColor(255, 255, 255, 180)))
            p.drawEllipse(QRectF(cx2 - 4*SCALE + head_dx, eye_y + 1*SCALE, 1.6*SCALE, 1.6*SCALE))
            p.drawEllipse(QRectF(cx2 + 3*SCALE + head_dx, eye_y + 1*SCALE, 1.6*SCALE, 1.6*SCALE))

        else:
            sway = wobble * (1.4*SCALE)
            body_rect = QRectF(cx2 - 21*SCALE, cy2 - 28*SCALE + sway, 42*SCALE, 46*SCALE)
            head_rect = QRectF(cx2 - 15*SCALE + head_dx, cy2 - 52*SCALE + sway + head_dy, 30*SCALE, 30*SCALE)
            shadow = QRectF(cx2 - 22*SCALE, cy2 + 18*SCALE, 44*SCALE, 14*SCALE)
            p.setBrush(QBrush(QColor(0, 0, 0, 90)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(shadow)

            body_grad = QLinearGradient(body_rect.topLeft(), body_rect.bottomRight())
            body_grad.setColorAt(0.0, bird.palette["body"].lighter(118))
            body_grad.setColorAt(1.0, bird.palette["body"].darker(132))
            p.setBrush(QBrush(body_grad))
            p.drawEllipse(body_rect)

            head_grad = QLinearGradient(head_rect.topLeft(), head_rect.bottomRight())
            head_grad.setColorAt(0.0, bird.palette["head"].lighter(130))
            head_grad.setColorAt(1.0, bird.palette["head"].darker(130))
            p.setBrush(QBrush(head_grad))
            p.drawEllipse(head_rect)

            belly = body_rect.adjusted(8*SCALE, 12*SCALE, -8*SCALE, -10*SCALE)
            belly_grad = QLinearGradient(belly.topLeft(), belly.bottomRight())
            belly_grad.setColorAt(0.0, bird.palette["belly"].lighter(108))
            belly_grad.setColorAt(1.0, bird.palette["belly"].darker(118))
            p.setBrush(QBrush(belly_grad))
            p.drawEllipse(belly)

            wing_color = bird.palette["wing"]
            p.setPen(QPen(wing_color.darker(155), 1.8*SCALE))
            p.setBrush(QBrush(wing_color))
            for direction in (-1, 1):
                path = QPainterPath()
                start = QPointF(cx2 + direction * 5*SCALE, cy2 - 6*SCALE + sway)
                ctrl = QPointF(cx2 + direction * (32*SCALE - wing_lift * direction), cy2 + 4*SCALE + sway - wing_lift * 0.5)
                end = QPointF(cx2 + direction * 14*SCALE, cy2 + 30*SCALE)
                path.moveTo(start)
                path.quadTo(ctrl, end)
                path.quadTo(QPointF(cx2 + direction * 4*SCALE, cy2 + 16*SCALE), start)
                p.drawPath(path)

            if bird.pattern == "speck":
                p.setBrush(QBrush(bird.palette["speck"].lighter(125)))
                p.setPen(Qt.PenStyle.NoPen)
                for i in range(4):
                    px = cx2 + rng.uniform(-8, 8) * SCALE
                    py = cy2 - 6*SCALE + i * 5*SCALE
                    p.drawEllipse(QRectF(px, py, 3.2*SCALE, 3.2*SCALE))

            beak_points = [
                (cx2, head_rect.y() + 14*SCALE + head_dy),
                (cx2 + 8*SCALE, head_rect.y() + 22*SCALE + head_dy),
                (cx2 - 8*SCALE, head_rect.y() + 22*SCALE + head_dy),
            ]
            beak_poly = QPolygonF([QPointF(x, y) for x, y in beak_points])
            p.setBrush(QBrush(bird.palette["beak"].lighter(128)))
            p.setPen(QPen(bird.palette["beak"].darker(140), 1.6*SCALE))
            p.drawPolygon(beak_poly)

            eye_r = 3.2*SCALE
            eye_y = head_rect.y() + 11*SCALE
            p.setBrush(QBrush(bird.palette["eye"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(cx2 - 7*SCALE + head_dx, eye_y, eye_r, eye_r))
            p.drawEllipse(QRectF(cx2 + 3*SCALE + head_dx, eye_y, eye_r, eye_r))
            p.setBrush(QBrush(QColor(255, 255, 255, 200)))
            p.drawEllipse(QRectF(cx2 - 6*SCALE + head_dx, eye_y + 1*SCALE, 1.8*SCALE, 1.8*SCALE))
            p.drawEllipse(QRectF(cx2 + 4*SCALE + head_dx, eye_y + 1*SCALE, 1.8*SCALE, 1.8*SCALE))

            tail = QPainterPath()
            tail.moveTo(cx2 - 5*SCALE, body_rect.bottom() - 4*SCALE)
            tail.quadTo(cx2 - 12*SCALE, body_rect.bottom() + 10*SCALE,
                        cx2, body_rect.bottom() + 14*SCALE)
            tail.quadTo(cx2 + 12*SCALE, body_rect.bottom() + 10*SCALE,
                        cx2 + 5*SCALE, body_rect.bottom() - 4*SCALE)
            tail_color = wing_color.darker(140)
            p.setBrush(QBrush(tail_color))
            p.setPen(QPen(tail_color.darker(150), 1.4*SCALE))
            p.drawPath(tail)

        p.restore()

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
