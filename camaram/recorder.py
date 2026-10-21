"""Grabación de vídeo enviando los fotogramas de la vista previa a ffmpeg.

Se usa ffmpeg en lugar de QMediaRecorder porque, sin aceleración por hardware,
QMediaRecorder produce H.264 4:4:4 10-bit (muchos reproductores no lo abren)
y no da tiempo a codificar 1080p en equipos modestos. Si la GPU admite VA-API
se codifica con ella a resolución completa; si no, con libx264 a 720p como máximo.
"""

import queue
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QImage

MAX_SIZE = QSize(1280, 720)       # codificando por software (libx264)
MAX_SIZE_HW = QSize(1920, 1080)   # codificando con la GPU (VA-API)
FPS = 30
VAAPI_DEVICE = "/dev/dri/renderD128"
_vaapi_ok: bool | None = None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def vaapi_available() -> bool:
    """Comprueba una vez si ffmpeg puede codificar H.264 con la GPU (VA-API)."""
    global _vaapi_ok
    if _vaapi_ok is None:
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
               "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30", "-frames:v", "5",
               "-vaapi_device", VAAPI_DEVICE, "-vf", "format=nv12,hwupload",
               "-c:v", "h264_vaapi", "-f", "null", "-"]
        try:
            _vaapi_ok = Path(VAAPI_DEVICE).exists() and subprocess.run(
                cmd, capture_output=True, timeout=10).returncode == 0
        except (OSError, subprocess.SubprocessError):
            _vaapi_ok = False
    return _vaapi_ok


class FfmpegRecorder:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self.frames: queue.Queue = queue.Queue(maxsize=4)
        self.size = QSize()
        self.path: Path | None = None
        self.started_at = 0.0
        self.error = ""
        self.finished = False
        self.hardware = False

    @property
    def active(self) -> bool:
        return self.proc is not None and not self.finished

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at if self.active else 0.0

    @staticmethod
    def output_size(frame_size: QSize, max_size: QSize) -> QSize:
        size = frame_size
        if size.width() > max_size.width() or size.height() > max_size.height():
            size = size.scaled(max_size, Qt.AspectRatioMode.KeepAspectRatio)
        # H.264 con yuv420p/nv12 necesita dimensiones pares
        return QSize(size.width() // 2 * 2, size.height() // 2 * 2)

    def start(self, path: Path, frame_size: QSize, with_audio: bool):
        hw = vaapi_available()
        self.hardware = hw
        self.size = self.output_size(frame_size, MAX_SIZE_HW if hw else MAX_SIZE)
        self.path = path
        self.error = ""
        self.finished = False
        self.frames = queue.Queue(maxsize=4)
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            *(["-vaapi_device", VAAPI_DEVICE] if hw else []),
            "-thread_queue_size", "64", "-use_wallclock_as_timestamps", "1",
            "-f", "rawvideo", "-pix_fmt", "bgra",
            "-s", f"{self.size.width()}x{self.size.height()}", "-i", "pipe:0",
        ]
        if with_audio:
            cmd += ["-thread_queue_size", "1024", "-f", "pulse", "-i", "default"]
        cmd += ["-map", "0:v"]
        if hw:
            cmd += ["-vf", "format=nv12,hwupload", "-c:v", "h264_vaapi", "-qp", "22"]
        else:
            cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p"]
        cmd += ["-fps_mode", "cfr", "-r", str(FPS)]
        if with_audio:
            # el micrófono no se acaba nunca: -shortest corta cuando termina el vídeo
            cmd += ["-map", "1:a", "-c:a", "aac", "-b:a", "128k", "-shortest"]
        cmd += ["-movflags", "+faststart", str(path)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)
        self.started_at = time.monotonic()
        self.thread = threading.Thread(target=self._writer, daemon=True)
        self.thread.start()

    def push(self, img: QImage):
        if not self.active or img.isNull():
            return
        if img.size() != self.size:
            img = img.scaled(self.size, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        img = img.convertToFormat(QImage.Format.Format_RGB32)
        try:
            self.frames.put_nowait(img.constBits().asstring(img.sizeInBytes()))
        except queue.Full:
            pass  # ffmpeg va con retraso: descartamos el fotograma, -fps_mode cfr lo rellena

    def stop(self):
        if self.active:
            # el escritor vacía la cola y luego cierra la tubería
            threading.Thread(target=self.frames.put, args=(None,), daemon=True).start()

    def _writer(self):
        proc = self.proc
        try:
            while True:
                data = self.frames.get()
                if data is None:
                    break
                proc.stdin.write(data)
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.send_signal(signal.SIGINT)  # ffmpeg cierra el archivo limpiamente con SIGINT
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            if proc.returncode != 0:
                self.error = proc.stderr.read().decode(errors="replace").strip().splitlines()[-1:] or ["ffmpeg falló"]
                self.error = self.error[0]
            self.finished = True
