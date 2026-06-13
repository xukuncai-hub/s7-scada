"""
Claude Pet — 像素小猫桌宠 (PyQt6 复刻)
素材来自 claude-pet npm 包 (已安装在本机)
"""
import sys
import math
import random
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QMenu
from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF, pyqtSignal, QRect
from PyQt6.QtGui import (
    QPainter, QPixmap, QMouseEvent, QCursor, QColor, QFont, QPen, QBrush,
    QRadialGradient, QPainterPath,
)

# ═══════════════════════════════════════════════════════════
#  素材路径
# ═══════════════════════════════════════════════════════════

NPM_ROOT = Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "claude-pet"
CAT_SPRITE = NPM_ROOT / "src" / "renderer" / "assets" / "cat.png"
FALLBACK = NPM_ROOT / "src" / "renderer" / "assets" / "claude-mama.png"

# Sprite 参数 (与 Character.tsx 一致)
FRAME_SIZE = 32
TOTAL_FRAMES = 5
PLAY_FRAMES = 4        # 只用前 4 帧
DISPLAY_SCALE = 2       # 64x64 显示
FPS = 6

# ═══════════════════════════════════════════════════════════
#  情绪枚举
# ═══════════════════════════════════════════════════════════

MOODS = {
    "happy":    {"anim": "bounce",    "color": "#FFB0B0"},
    "playful":  {"anim": "jump",      "color": "#FFD700"},
    "sleepy":   {"anim": "tilt",      "color": "#3B82F6"},
    "sleeping": {"anim": "tilt",      "color": "#3B82F6"},
    "worried":  {"anim": "sway",      "color": "#60A5FA"},
    "bored":    {"anim": "wobble",    "color": "#9CA3AF"},
    "confused": {"anim": "wobble",    "color": "#666666"},
}


# ═══════════════════════════════════════════════════════════
#  粒子
# ═══════════════════════════════════════════════════════════

class Particle:
    __slots__ = ('x','y','vx','vy','life','max_life','size','color','kind')
    def __init__(self, x, y, vx, vy, life, size, color, kind="dot"):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = self.max_life = life
        self.size = size
        self.color = color
        self.kind = kind  # "dot", "heart", "star", "sparkle", "zzz"


# ═══════════════════════════════════════════════════════════
#  桌宠 Widget
# ═══════════════════════════════════════════════════════════

class ClaudePet(QWidget):
    W, H = 120, 140

    def __init__(self):
        super().__init__()
        self.setFixedSize(self.W, self.H)

        # ── 素材 ──
        self._sprites: list[QPixmap] = []
        self._fallback: QPixmap = None
        self._load_assets()

        # ── 状态 ──
        self._mood = "happy"
        self._frame = 0
        self._frame_t = 0.0
        self._anim_t = 0.0   # mood 动画时间
        self._breath = 0.0

        # ── 拖拽 ──
        self._dragging = False
        self._drag_anchor = QPoint()

        # ── 粒子 ──
        self._particles: list[Particle] = []

        # ── 对话气泡 ──
        self._bubble_text = ""
        self._bubble_alpha = 0.0
        self._bubble_timer = 0.0

        # ── 心情循环 ──
        self._mood_cycle = 0.0

        # ── 帧驱动 ──
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(33)  # ~30fps
        self._timer.start()

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _load_assets(self):
        """加载像素猫 sprite sheet"""
        if CAT_SPRITE.exists():
            sheet = QPixmap(str(CAT_SPRITE))
            if not sheet.isNull():
                # 切分 5 帧 (每帧 32x32)
                for i in range(TOTAL_FRAMES):
                    frame = sheet.copy(i * FRAME_SIZE, 0, FRAME_SIZE, FRAME_SIZE)
                    self._sprites.append(frame)
        if FALLBACK.exists():
            self._fallback = QPixmap(str(FALLBACK))

    # ═══════════════════════════════════════════════════════
    #  帧更新
    # ═══════════════════════════════════════════════════════

    def _tick(self):
        dt = 0.033

        # Sprite 动画
        self._frame_t += dt
        if self._frame_t >= 1.0 / FPS:
            self._frame_t -= 1.0 / FPS
            self._frame = (self._frame + 1) % PLAY_FRAMES

        # Mood 动画
        self._anim_t += dt
        self._breath += dt * 2.5

        # 心情自动轮换 (30~60s)
        self._mood_cycle += dt
        if self._mood_cycle > random.uniform(25, 50):
            self._mood_cycle = 0.0
            moods = list(MOODS.keys())
            self._mood = random.choice(moods)
            # 触发性心情特效
            if self._mood == "happy":
                self._spawn_hearts()
            elif self._mood == "playful":
                self._spawn_sparkles()
            elif self._mood in ("sleepy", "sleeping"):
                pass  # zzz 每帧都画
            elif self._mood == "worried":
                pass

        # 气泡
        if self._bubble_alpha > 0:
            self._bubble_timer += dt
            if self._bubble_timer > 4.0:
                self._bubble_alpha = max(0, self._bubble_alpha - dt * 2)

        # 粒子
        for pt in self._particles:
            pt.life -= dt
            pt.x += pt.vx * dt
            pt.y += pt.vy * dt
            if pt.kind in ("heart", "sparkle", "star"):
                pt.vy -= 40 * dt
            else:
                pt.vy += 60 * dt
        self._particles = [p for p in self._particles if p.life > 0]

        self.update()

    # ═══════════════════════════════════════════════════════
    #  特效
    # ═══════════════════════════════════════════════════════

    def _spawn_hearts(self):
        for i in range(3):
            self._particles.append(Particle(
                random.uniform(-15, 15), random.uniform(-5, 10),
                random.uniform(-15, 15), random.uniform(-60, -30),
                random.uniform(1.5, 2.5), random.uniform(8, 14),
                QColor("#FF69B4"), "heart"
            ))

    def _spawn_sparkles(self):
        colors = ["#FFD700", "#FF69B4", "#00CED1", "#FF6347"]
        for i in range(6):
            self._particles.append(Particle(
                random.uniform(-20, 20), random.uniform(-10, 15),
                random.uniform(-25, 25), random.uniform(-70, -20),
                random.uniform(0.6, 1.4), random.uniform(3, 6),
                QColor(random.choice(colors)), "sparkle"
            ))

    def say(self, text: str):
        self._bubble_text = text
        self._bubble_alpha = 1.0
        self._bubble_timer = 0.0

    def set_mood(self, mood: str):
        if mood in MOODS:
            self._mood = mood
            self._mood_cycle = 0.0
            if mood == "happy":
                self._spawn_hearts()
            elif mood == "playful":
                self._spawn_sparkles()

    # ═══════════════════════════════════════════════════════
    #  鼠标交互
    # ═══════════════════════════════════════════════════════

    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_anchor = ev.globalPosition().toPoint()

    def mouseMoveEvent(self, ev: QMouseEvent):
        if self._dragging:
            gp = ev.globalPosition().toPoint()
            d = gp - self._drag_anchor
            self._drag_anchor = gp
            w = self.window()
            if w:
                w.move(w.x() + d.x(), w.y() + d.y())

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    # ═══════════════════════════════════════════════════════
    #  绘制
    # ═══════════════════════════════════════════════════════

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)  # 像素风格!

        cx, cy = self.W / 2, self.H / 2 - 8

        # ── Mood 动画变换 ──
        mood_info = MOODS.get(self._mood, MOODS["happy"])
        anim_type = mood_info["anim"]

        p.save()
        p.translate(cx, cy)

        # 动画参数
        bounce = 0
        rot = 0
        sway = 0
        scale = 1.0

        if anim_type == "bounce":
            bounce = abs(math.sin(self._anim_t * 3.5)) * 6
            scale = 1 + math.sin(self._anim_t * 3.5) * 0.04
        elif anim_type == "jump":
            t = self._anim_t * 3
            bounce = abs(math.sin(t)) * 10 if math.sin(t) > 0 else 0
            rot = math.sin(t * 1.5) * 3
            scale = 1 + abs(math.sin(t)) * 0.06
        elif anim_type == "tilt":
            rot = math.sin(self._anim_t * 0.8) * 5
            scale = 0.98
        elif anim_type == "sway":
            sway = math.sin(self._anim_t * 2.5) * 3
            rot = math.sin(self._anim_t * 2.5) * 2
        elif anim_type == "wobble":
            rot = math.sin(self._anim_t * 4) * 5

        # 呼吸微动
        micro = math.sin(self._breath) * 1.5
        bounce += micro

        p.translate(sway, -bounce)
        p.rotate(rot)
        p.scale(scale, scale)

        # ── 光晕 (playful/happy) ──
        if self._mood in ("playful", "happy"):
            alpha = int(40 + math.sin(self._anim_t * 3) * 20)
            glow = QRadialGradient(0, 0, 42)
            if self._mood == "playful":
                glow.setColorAt(0, QColor(255, 215, 0, alpha))
                glow.setColorAt(1, QColor(255, 215, 0, 0))
            else:
                glow.setColorAt(0, QColor(255, 182, 193, alpha))
                glow.setColorAt(1, QColor(255, 182, 193, 0))
            p.setBrush(QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(-40, -40, 80, 80))

        # ── 像素猫 sprite ──
        sprite_size = FRAME_SIZE * DISPLAY_SCALE  # 64
        sx = -sprite_size / 2
        sy = -sprite_size / 2

        if self._sprites:
            frame_idx = self._frame % len(self._sprites)
            pix = self._sprites[frame_idx]
            # 睡眠时变暗
            if self._mood in ("sleeping", "sleepy"):
                p.setOpacity(0.8)
            target = QRectF(sx, sy, sprite_size, sprite_size)
            p.drawPixmap(target, pix, QRectF(0, 0, FRAME_SIZE, FRAME_SIZE))
            p.setOpacity(1.0)
        elif self._fallback:
            p.drawPixmap(QRectF(sx, sy, sprite_size, sprite_size), self._fallback)

        p.restore()

        # ── Mood 叠加特效 ──
        self._draw_overlays(p, cx, cy)

        # ── 粒子 ──
        for pt in self._particles:
            alpha = int(255 * pt.life / pt.max_life)
            c = QColor(pt.color.red(), pt.color.green(), pt.color.blue(), alpha)
            p.setPen(Qt.PenStyle.NoPen)

            if pt.kind == "heart":
                p.setFont(QFont("Segoe UI", int(pt.size)))
                p.setPen(QPen(c, 1))
                p.drawText(QPoint(int(cx + pt.x), int(cy + pt.y)), "♥")
            elif pt.kind == "star":
                p.setFont(QFont("Segoe UI", int(pt.size)))
                p.setPen(QPen(c, 1))
                p.drawText(QPoint(int(cx + pt.x), int(cy + pt.y)), "★")
            elif pt.kind == "sparkle":
                p.setBrush(QBrush(c))
                # 菱形
                path = QPainterPath()
                sx, sy = cx + pt.x, cy + pt.y
                s = pt.size
                path.moveTo(sx, sy - s)
                path.lineTo(sx + s * 0.5, sy)
                path.lineTo(sx, sy + s)
                path.lineTo(sx - s * 0.5, sy)
                path.closeSubpath()
                p.drawPath(path)
            else:
                p.setBrush(QBrush(c))
                p.drawEllipse(QRectF(int(cx + pt.x), int(cy + pt.y), int(pt.size), int(pt.size)))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        # ── 对话气泡 ──
        if self._bubble_alpha > 0.01 and self._bubble_text:
            self._draw_bubble(p, cx, cy)

        p.end()

    def _draw_overlays(self, p: QPainter, cx: float, cy: float):
        """情绪叠加层"""
        font = QFont("Segoe UI", 8)

        if self._mood == "worried":
            # 汗滴
            t = self._anim_t
            p.setPen(QPen(QColor("#60A5FA"), 1.5))
            p.setFont(font)
            p.drawText(QPoint(int(cx + 28), int(cy - 24 + math.sin(t * 4) * 4)), "💧")

        elif self._mood == "happy":
            pass  # hearts are particles

        elif self._mood == "bored":
            t = self._anim_t
            alpha = int(200 + math.sin(t * 2) * 55)
            c = QColor(156, 163, 175, alpha)
            p.setPen(QPen(c, 2))
            p.setFont(QFont("monospace", 16))
            p.drawText(QPoint(int(cx + 26), int(cy - 28 + math.sin(t * 1.5) * 3)), "...")

        elif self._mood == "confused":
            t = self._anim_t
            alpha = int(180 + math.sin(t * 2) * 75)
            c = QColor(102, 102, 102, alpha)
            p.setPen(QPen(c, 3))
            p.setFont(QFont("monospace", 20, QFont.Weight.Bold))
            p.drawText(QPoint(int(cx + 24), int(cy - 28 + math.sin(t * 1.5) * 3)), "?")

        elif self._mood in ("sleepy", "sleeping"):
            for i, ch in enumerate(['z', 'z', 'Z']):
                alpha = int(160 + math.sin(self._anim_t * 2.5 + i * 1.4) * 60)
                c = QColor(59, 130, 246, alpha)
                p.setPen(QPen(c, 2))
                p.setFont(QFont("monospace", 10 + i * 3, QFont.Weight.Bold))
                oz_y = cy - 36 - i * 16 - math.sin(self._anim_t * 2.5 + i * 1.4) * 6
                oz_x = cx + 26 + i * 8
                p.drawText(QPoint(int(oz_x), int(oz_y)), ch)

    def _draw_bubble(self, p: QPainter, cx: float, cy: float):
        """对话气泡"""
        text = self._bubble_text
        alpha = self._bubble_alpha

        font = QFont("Microsoft YaHei", 10)
        p.setFont(font)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text) + 20
        th = fm.height() + 14

        bx = cx - tw / 2
        by = cy - 60 - th

        # 气泡背景
        p.setBrush(QBrush(QColor(40, 40, 50, int(220 * alpha))))
        p.setPen(QPen(QColor(80, 80, 100, int(200 * alpha)), 1))
        p.drawRoundedRect(QRectF(bx, by, tw, th), 12, 12)

        # 小三角
        tri = QPainterPath()
        tri.moveTo(cx - 6, by + th)
        tri.lineTo(cx, by + th + 8)
        tri.lineTo(cx + 6, by + th)
        tri.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(tri)

        # 文字
        p.setPen(QPen(QColor(240, 240, 245, int(255 * alpha))))
        p.drawText(QRectF(bx, by, tw, th), Qt.AlignmentFlag.AlignCenter, text)


# ═══════════════════════════════════════════════════════════
#  主窗口
# ═══════════════════════════════════════════════════════════

class DeskPetWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.pet = ClaudePet()
        self.setCentralWidget(self.pet)
        self.setFixedSize(self.pet.W, self.pet.H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.right() - self.width() - 25,
            screen.bottom() - self.height() - 40
        )

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

        # 欢迎气泡
        QTimer.singleShot(500, lambda: self.pet.say("喵~ 我来陪你写代码! 🐱"))

    def _menu(self, pos):
        m = QMenu(self)
        m.setStyleSheet("""
            QMenu {
                background: #252530; border: 1px solid #3a3a4a;
                border-radius: 10px; padding: 5px; color: #ddd;
            }
            QMenu::item {
                padding: 9px 28px 9px 14px; border-radius: 6px; margin: 2px 3px;
            }
            QMenu::item:selected { background: #e88850; color: #fff; }
            QMenu::separator { height: 1px; background: #383848; margin: 4px 8px; }
        """)

        moods_menu = m.addMenu("😺  心情")
        for mood_key in ["happy", "playful", "sleepy", "worried", "bored", "confused"]:
            moods_menu.addAction(mood_key, lambda k=mood_key: self.pet.set_mood(k))

        m.addSeparator()
        m.addAction("❌  退出", QApplication.instance().quit)
        m.exec(self.mapToGlobal(pos))


# ═══════════════════════════════════════════════════════════

def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Claude Pet")
    app.setQuitOnLastWindowClosed(False)

    pet = DeskPetWindow()
    pet.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
