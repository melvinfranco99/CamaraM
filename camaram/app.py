"""CamaraM - aplicación de cámara para Linux (PyQt6 + QtMultimedia)."""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSettings, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QIcon, QImage, QKeySequence, QPainter, QPixmap
from PyQt6.QtMultimedia import (
    QCamera,
    QCameraDevice,
    QMediaCaptureSession,
    QMediaDevices,
    QVideoFrame,
    QVideoSink,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from camaram.recorder import FfmpegRecorder, ffmpeg_available

APP_NAME = "CamaraM"
VERSION = "1.0.0"
ICON_PATH = Path(__file__).resolve().parent / "camaram.svg"


def user_dir(kind: str, fallback: str) -> Path:
    """Devuelve la carpeta XDG del usuario (Imágenes, Vídeos...) con subcarpeta CamaraM."""
    try:
        out = subprocess.run(["xdg-user-dir", kind], capture_output=True, text=True, timeout=2)
        base = Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        base = None
    if base is None or base == Path.home():
        base = Path.home() / fallback
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


class Viewfinder(QWidget):
    """Muestra los fotogramas de la cámara, con espejo opcional y efecto de flash."""

    def __init__(self):
        super().__init__()
        self.image = QImage()
        self.mirror = True
        self.message = "Buscando cámaras…"
        self.countdown = 0
        self.recording = False
        self.flash = 0.0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 240)
        self._flash_timer = QTimer(self, interval=30, timeout=self._fade_flash)

    def set_frame(self, image: QImage):
        self.image = image
        self.message = ""
        self.update()

    def current_image(self) -> QImage:
        if self.image.isNull():
            return QImage()
        return self.image.mirrored(True, False) if self.mirror else self.image.copy()

    def do_flash(self):
        self.flash = 1.0
        self._flash_timer.start()

    def _fade_flash(self):
        self.flash -= 0.12
        if self.flash <= 0:
            self.flash = 0
            self._flash_timer.stop()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#111"))
        if not self.image.isNull():
            img = self.image.mirrored(True, False) if self.mirror else self.image
            scaled = img.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(self.rect().adjusted(x, y, -x, -y), img)
        if self.message:
            p.setPen(QColor("#ddd"))
            f = p.font()
            f.setPointSize(14)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
        if self.countdown:
            p.setPen(QColor(255, 255, 255, 230))
            f = p.font()
            f.setPointSize(96)
            f.setBold(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self.countdown))
        if self.recording:
            p.setBrush(QColor("#e53935"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(16, 16, 18, 18)
        if self.flash > 0:
            p.fillRect(self.rect(), QColor(255, 255, 255, int(255 * self.flash)))


class CameraWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(960, 680)
        self.settings = QSettings(APP_NAME, APP_NAME)
        self.photo_dir = user_dir("PICTURES", "Imágenes")
        self.video_dir = user_dir("VIDEOS", "Vídeos")
        self.last_file: Path | None = None

        self.devices = QMediaDevices(self)
        self.camera: QCamera | None = None
        self.session = QMediaCaptureSession(self)
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self.on_frame)
        self.session.setVideoSink(self.sink)
        self.recorder = FfmpegRecorder()
        self._rec_poll = QTimer(self, interval=200, timeout=self.poll_recorder)

        self.timer_options = [0, 3, 10]
        self.timer_index = int(self.settings.value("timer_index", 0))
        self.countdown_timer = QTimer(self, interval=1000, timeout=self.tick_countdown)

        self.build_ui()
        self.viewfinder.mirror = self.settings.value("mirror", True, type=bool)
        self.mirror_btn.setChecked(self.viewfinder.mirror)
        self.devices.videoInputsChanged.connect(self.refresh_cameras)
        self.refresh_cameras()

    # ---------- interfaz ----------
    def build_ui(self):
        self.viewfinder = Viewfinder()

        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(220)
        self.camera_combo.currentIndexChanged.connect(self.on_camera_selected)
        self.res_combo = QComboBox()
        self.res_combo.currentIndexChanged.connect(self.on_resolution_selected)

        self.switch_btn = self.tool_button("🔄  Cambiar cámara", "Cambiar entre cámara frontal y trasera (C)", self.switch_camera)
        self.mirror_btn = self.tool_button("↔  Espejo", "Voltear la imagen horizontalmente (M)", self.toggle_mirror)
        self.mirror_btn.setCheckable(True)
        self.timer_btn = self.tool_button("", "Temporizador para la foto (T)", self.cycle_timer)
        self.update_timer_label()

        top = QHBoxLayout()
        top.addWidget(QLabel("Cámara:"))
        top.addWidget(self.camera_combo)
        top.addWidget(QLabel("Resolución:"))
        top.addWidget(self.res_combo)
        top.addStretch()
        top.addWidget(self.timer_btn)
        top.addWidget(self.mirror_btn)
        top.addWidget(self.switch_btn)

        self.thumb = QToolButton()
        self.thumb.setFixedSize(72, 72)
        self.thumb.setIconSize(QSize(64, 64))
        self.thumb.setToolTip("Abrir la última captura")
        self.thumb.clicked.connect(self.open_last)

        self.photo_btn = QPushButton("📷")
        self.photo_btn.setObjectName("shutter")
        self.photo_btn.setFixedSize(84, 84)
        self.photo_btn.setToolTip("Hacer foto (Espacio)")
        self.photo_btn.clicked.connect(self.take_photo)

        self.record_btn = QPushButton("⏺")
        self.record_btn.setObjectName("record")
        self.record_btn.setFixedSize(64, 64)
        self.record_btn.setToolTip("Grabar vídeo (R)")
        self.record_btn.clicked.connect(self.toggle_recording)

        folder_btn = self.tool_button("📁  Galería", "Abrir la carpeta de fotos", lambda: self.open_path(self.photo_dir))
        video_folder_btn = self.tool_button("🎞  Vídeos", "Abrir la carpeta de vídeos", lambda: self.open_path(self.video_dir))

        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        bottom = QHBoxLayout()
        bottom.addWidget(self.thumb)
        bottom.addWidget(folder_btn)
        bottom.addWidget(video_folder_btn)
        bottom.addStretch()
        bottom.addWidget(self.photo_btn)
        bottom.addSpacing(12)
        bottom.addWidget(self.record_btn)
        bottom.addStretch()
        bottom.addWidget(self.status)

        root = QWidget()
        lay = QVBoxLayout(root)
        lay.addLayout(top)
        lay.addWidget(self.viewfinder, 1)
        lay.addLayout(bottom)
        self.setCentralWidget(root)

        self.setStyleSheet("""
            QWidget { background: #1e1e22; color: #eee; font-size: 13px; }
            QComboBox, QToolButton { background: #2c2c33; border: 1px solid #3a3a44; border-radius: 6px; padding: 6px 10px; }
            QToolButton:hover, QComboBox:hover { background: #383842; }
            QToolButton:checked { background: #3d5afe; border-color: #3d5afe; }
            QPushButton#shutter { background: #fafafa; color: #111; border: 4px solid #888; border-radius: 42px; font-size: 30px; }
            QPushButton#shutter:hover { background: #fff; border-color: #3d5afe; }
            QPushButton#record { background: #2c2c33; color: #e53935; border: 3px solid #e53935; border-radius: 32px; font-size: 26px; }
            QPushButton#record[recording="true"] { background: #e53935; color: #fff; }
            QPushButton:disabled { background: #444; color: #777; border-color: #555; }
        """)

        shortcuts = [
            ("Space", self.take_photo), ("R", self.toggle_recording), ("C", self.switch_camera),
            ("M", self.toggle_mirror), ("T", self.cycle_timer), ("F", self.toggle_fullscreen),
            ("F11", self.toggle_fullscreen), ("Esc", self.exit_fullscreen), ("Ctrl+Q", self.close),
        ]
        for key, fn in shortcuts:
            act = QAction(self)
            act.setShortcut(QKeySequence(key))
            act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            act.triggered.connect(fn)
            self.addAction(act)

    def tool_button(self, text, tip, slot):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(slot)
        return b

    def show_status(self, text, ms=4000):
        self.status.setText(text)
        if ms:
            QTimer.singleShot(ms, lambda: self.status.text() == text and self.status.setText(""))

    # ---------- cámaras ----------
    @staticmethod
    def camera_label(dev: QCameraDevice) -> str:
        pos = {
            QCameraDevice.Position.FrontFace: " (frontal)",
            QCameraDevice.Position.BackFace: " (trasera)",
        }.get(dev.position(), "")
        name = dev.description()
        # V4L2 suele repetir el nombre ("HP Full HD Camera: HP Full HD C"); nos quedamos con la primera parte
        head, sep, tail = name.partition(": ")
        if sep and tail and head.startswith(tail.rstrip()):
            name = head
        return name + pos

    def refresh_cameras(self):
        current = self.camera.cameraDevice().id() if self.camera else self.settings.value("camera_id", b"")
        cams = QMediaDevices.videoInputs()
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        index = 0
        for i, dev in enumerate(cams):
            self.camera_combo.addItem(self.camera_label(dev), dev)
            if bytes(dev.id()) == bytes(current or b""):
                index = i
        self.camera_combo.blockSignals(False)
        self.switch_btn.setEnabled(len(cams) > 1)
        self.switch_btn.setToolTip(
            "Cambiar entre cámara frontal y trasera (C)" if len(cams) > 1
            else "Solo hay una cámara disponible en este equipo"
        )
        has_cam = bool(cams)
        for w in (self.photo_btn, self.record_btn, self.res_combo):
            w.setEnabled(has_cam)
        if not has_cam:
            self.stop_camera()
            self.viewfinder.image = QImage()
            self.viewfinder.message = "No se ha encontrado ninguna cámara.\nConecta una cámara y aparecerá aquí automáticamente."
            self.viewfinder.update()
            return
        self.camera_combo.setCurrentIndex(index)
        self.on_camera_selected(index)

    def stop_camera(self):
        if self.recorder.active:
            self.recorder.stop()
        if self.camera:
            self.camera.stop()
            self.camera.deleteLater()
            self.camera = None

    def on_camera_selected(self, index):
        dev = self.camera_combo.itemData(index)
        if dev is None:
            return
        if self.camera and self.camera.cameraDevice().id() == dev.id() and self.camera.isActive():
            return
        self.stop_camera()
        self.viewfinder.message = "Abriendo cámara…"
        self.viewfinder.image = QImage()
        self.viewfinder.update()
        self.camera = QCamera(dev, self)
        self.camera.errorOccurred.connect(self.on_camera_error)
        self.session.setCamera(self.camera)
        self.settings.setValue("camera_id", bytes(dev.id()))
        self.fill_resolutions(dev)
        self.camera.start()
        self.show_status(f"Usando: {self.camera_label(dev)}")

    def fill_resolutions(self, dev: QCameraDevice):
        best = {}
        for fmt in dev.videoFormats():
            size = fmt.resolution()
            key = (size.width(), size.height())
            prev = best.get(key)
            # para cada resolución nos quedamos con el formato de más fps
            if prev is None or fmt.maxFrameRate() > prev.maxFrameRate():
                best[key] = fmt
        keys = sorted(best, key=lambda k: k[0] * k[1], reverse=True)
        saved = self.settings.value(f"res/{bytes(dev.id()).decode(errors='ignore')}", "")
        self.res_combo.blockSignals(True)
        self.res_combo.clear()
        choose = 0
        for i, (w, h) in enumerate(keys):
            fmt = best[(w, h)]
            self.res_combo.addItem(f"{w}×{h} @ {fmt.maxFrameRate():.0f} fps", fmt)
            if saved == f"{w}x{h}":
                choose = i
        self.res_combo.blockSignals(False)
        if keys:
            self.res_combo.setCurrentIndex(choose)
            self.camera.setCameraFormat(self.res_combo.itemData(choose))

    def on_resolution_selected(self, index):
        fmt = self.res_combo.itemData(index)
        if fmt is None or not self.camera:
            return
        if self.recorder.active:
            self.show_status("Detén la grabación para cambiar la resolución")
            return
        self.camera.stop()
        self.camera.setCameraFormat(fmt)
        self.camera.start()
        size = fmt.resolution()
        dev_id = bytes(self.camera.cameraDevice().id()).decode(errors="ignore")
        self.settings.setValue(f"res/{dev_id}", f"{size.width()}x{size.height()}")

    def on_camera_error(self, _err, msg):
        self.viewfinder.image = QImage()
        self.viewfinder.message = f"No se pudo abrir la cámara:\n{msg}\n\n¿La está usando otra aplicación?"
        self.viewfinder.update()

    def switch_camera(self):
        n = self.camera_combo.count()
        if n < 2:
            self.show_status("Solo hay una cámara disponible")
            return
        if self.recorder.active:
            self.show_status("Detén la grabación para cambiar de cámara")
            return
        self.camera_combo.setCurrentIndex((self.camera_combo.currentIndex() + 1) % n)

    def on_frame(self, frame: QVideoFrame):
        img = frame.toImage()
        if not img.isNull():
            self.viewfinder.set_frame(img)
            if self.recorder.active:
                self.recorder.push(self.viewfinder.current_image())

    # ---------- fotos ----------
    def toggle_mirror(self):
        self.viewfinder.mirror = not self.viewfinder.mirror
        self.mirror_btn.setChecked(self.viewfinder.mirror)
        self.settings.setValue("mirror", self.viewfinder.mirror)
        self.viewfinder.update()

    def cycle_timer(self):
        self.timer_index = (self.timer_index + 1) % len(self.timer_options)
        self.settings.setValue("timer_index", self.timer_index)
        self.update_timer_label()

    def update_timer_label(self):
        secs = self.timer_options[self.timer_index]
        self.timer_btn.setText(f"⏱  {secs} s" if secs else "⏱  Sin temporizador")

    def take_photo(self):
        if not self.camera or self.countdown_timer.isActive():
            return
        secs = self.timer_options[self.timer_index]
        if secs:
            self.viewfinder.countdown = secs
            self.viewfinder.update()
            self.countdown_timer.start()
        else:
            self.capture_now()

    def tick_countdown(self):
        self.viewfinder.countdown -= 1
        if self.viewfinder.countdown <= 0:
            self.countdown_timer.stop()
            self.viewfinder.countdown = 0
            self.capture_now()
        self.viewfinder.update()

    def capture_now(self):
        img = self.viewfinder.current_image()
        if img.isNull():
            self.show_status("Todavía no hay imagen de la cámara")
            return
        path = self.photo_dir / f"CamaraM_{datetime.now():%Y%m%d_%H%M%S_%f}"[:-3]
        path = path.with_suffix(".jpg")
        if img.save(str(path), "JPG", 95):
            self.viewfinder.do_flash()
            self.set_last(path, img)
            self.show_status(f"Foto guardada: {path.name}")
        else:
            self.show_status("No se pudo guardar la foto")

    # ---------- vídeo ----------
    def toggle_recording(self):
        if not self.camera:
            return
        if self.recorder.active:
            self.recorder.stop()
            self.record_btn.setEnabled(False)
            self.show_status("Guardando vídeo…", 0)
            return
        if not ffmpeg_available():
            self.show_status("Para grabar vídeo hace falta ffmpeg instalado", 8000)
            return
        frame = self.viewfinder.current_image()
        if frame.isNull():
            self.show_status("Todavía no hay imagen de la cámara")
            return
        path = self.video_dir / f"CamaraM_{datetime.now():%Y%m%d_%H%M%S}.mp4"
        self.recorder.start(path, frame.size(), with_audio=bool(QMediaDevices.audioInputs()))
        self.update_recording_ui(True)
        self._rec_poll.start()

    def poll_recorder(self):
        if self.recorder.active:
            s = int(self.recorder.elapsed())
            self.status.setText(f"● Grabando {s // 60:02d}:{s % 60:02d}")
            return
        self._rec_poll.stop()
        self.update_recording_ui(False)
        path = self.recorder.path
        if self.recorder.error:
            self.show_status(f"Error al grabar: {self.recorder.error}", 10000)
        elif path and path.exists():
            self.set_last(path, self.viewfinder.current_image())
            self.show_status(f"Vídeo guardado: {path.name}", 6000)

    def update_recording_ui(self, recording: bool):
        self.viewfinder.recording = recording
        self.viewfinder.update()
        self.record_btn.setEnabled(True)
        self.record_btn.setText("⏹" if recording else "⏺")
        self.record_btn.setProperty("recording", recording)
        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)
        for w in (self.camera_combo, self.res_combo, self.switch_btn):
            w.setEnabled(not recording and (w is not self.switch_btn or self.camera_combo.count() > 1))

    # ---------- utilidades ----------
    def set_last(self, path: Path, img: QImage):
        self.last_file = path
        if not img.isNull():
            pix = QPixmap.fromImage(img.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                               Qt.TransformationMode.SmoothTransformation))
            self.thumb.setIcon(QIcon(pix))

    def open_last(self):
        if self.last_file and self.last_file.exists():
            self.open_path(self.last_file)
        else:
            self.open_path(self.photo_dir)

    @staticmethod
    def open_path(path: Path):
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()

    def closeEvent(self, event):
        self.stop_camera()
        if self.recorder.thread:
            self.recorder.thread.join(timeout=15)  # deja que ffmpeg cierre el archivo
        super().closeEvent(event)


def main():
    os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")
    if "--version" in sys.argv:
        print(f"{APP_NAME} {VERSION}")
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("camaram")
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    win = CameraWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
