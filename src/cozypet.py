# cozy_pet_min.py (fixed + stays-on-top reliably on macOS)
import sys, math
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QBrush, QColor, QPen, QAction, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu

class Pet(QWidget):
    def __init__(self):
        super().__init__()
        self.resize(140, 140)

        # frameless, transparent, always-on-top (as a real Window, not a Tool)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._drag = None
        self.phase = 0.0

        # simple animation
        self.t = QTimer(self)
        self.t.timeout.connect(self.tick)
        self.t.start(120)

      

        # start near bottom-right
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 40, screen.bottom() - self.height() - 80)

    def tick(self):
        self.phase = (self.phase + 0.25) % (2 * math.pi)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # soft shadow (use QRectF so floats are OK)
        p.setBrush(QBrush(QColor(0, 0, 0, 60)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(w / 2 - 45.0, h - 28.0, 90.0, 18.0))

        # body
        p.setBrush(QBrush(QColor(255, 240, 200)))
        p.setPen(QPen(QColor(60, 60, 60), 2))
        p.drawEllipse(10, 10, 120, 120)

        # eyes (blink by squashing)
        blink = 1 if int((self.phase * 5) % 20) == 0 else 0
        eye_h = 10 if not blink else 2
        p.setBrush(QBrush(QColor(30, 30, 30)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(50, 60, 12, eye_h)
        p.drawEllipse(78, 60, 12, eye_h)

        # tiny smile
        p.setPen(QPen(QColor(40, 40, 40), 3))
        p.drawArc(55, 74, 30, 16, 0, -180 * 16)

    # drag to move
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


def make_simple_icon() -> QIcon:
    """Create a tiny in-memory circular icon so the tray has something to show."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.RenderHint.Antialiasing)
    qp.setBrush(QBrush(QColor(255, 240, 200)))
    qp.setPen(QPen(QColor(60, 60, 60), 2))
    qp.drawEllipse(3, 3, 26, 26)
    qp.end()
    return QIcon(pm)

class App:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.pet = Pet()
        self.pet.show()

        # tray (menubar) with Quit + real icon
        self.tray = QSystemTrayIcon(make_simple_icon())
        menu = QMenu()
        quit_action = QAction("Quit")
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("CozyPet Mini")
        self.tray.show()

    def run(self):
        sys.exit(self.app.exec())

if __name__ == "__main__":
    App().run()
# To run: python cozy_pet_min.py