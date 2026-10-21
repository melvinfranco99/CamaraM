# CamaraM

Aplicación de cámara para Linux escrita en Python con PyQt6 y QtMultimedia.

![icono](camaram/camaram.svg)

## Funciones

- Vista previa en directo de la cámara, hasta 1920×1080.
- **Cambio de cámara** (frontal ↔ trasera, o cualquier webcam USB) con un botón o la tecla `C`.
  Las cámaras que se conectan o desconectan aparecen y desaparecen solas.
- **Fotos** en JPG con efecto de flash y miniatura de la última captura.
- **Vídeo** en MP4 (H.264 + audio AAC del micrófono por defecto), con contador de tiempo.
  Si la GPU admite VA-API (Intel: paquete `intel-media-driver`) se graba con la GPU hasta 1080p;
  si no, por software hasta 720p.
- Temporizador de foto de 3 o 10 segundos.
- Modo espejo, selector de resolución y pantalla completa.
- Recuerda la última cámara, resolución y ajustes que usaste.

Las fotos se guardan en `~/Imágenes/CamaraM` y los vídeos en `~/Vídeos/CamaraM`
(o en las carpetas XDG equivalentes de tu idioma).

### Atajos de teclado

| Tecla | Acción |
|---|---|
| `Espacio` | Hacer foto |
| `R` | Empezar / parar grabación |
| `C` | Cambiar de cámara |
| `M` | Espejo |
| `T` | Temporizador (0 / 3 / 10 s) |
| `F` / `F11` | Pantalla completa |
| `Ctrl+Q` | Salir |

## Instalación

### Instalador de un solo archivo

Descarga `CamaraM-<versión>-installer.sh` desde [Releases](https://github.com/melvinfranco99/CamaraM/releases) y ejecútalo:

```sh
bash CamaraM-1.1.0-installer.sh            # para tu usuario (~/.local), sin sudo
sudo bash CamaraM-1.1.0-installer.sh --system   # para todo el sistema (/usr/local)
```

### Desde el código

```sh
git clone https://github.com/melvinfranco99/CamaraM.git
cd CamaraM
./install.sh
```

### Arch Linux (paquete)

```sh
cd packaging/arch
makepkg -si
```

### Dependencias

- Python 3, PyQt6, Qt6 Multimedia (con el backend FFmpeg) y `ffmpeg`.
- Arch: `sudo pacman -S --needed python-pyqt6 qt6-multimedia qt6-multimedia-ffmpeg ffmpeg`
- Debian/Ubuntu: `sudo apt install python3-pyqt6 python3-pyqt6.qtmultimedia ffmpeg`

### Desinstalar

```sh
./uninstall.sh          # o ./uninstall.sh --system
```

## Notas sobre cámaras integradas

CamaraM usa todas las cámaras que el sistema expone como dispositivos de vídeo (V4L2).
Algunas tabletas y portátiles 2 en 1 con procesador Intel (por ejemplo el HP Elite x2 1012 G1)
conectan la cámara trasera a la unidad de imagen IPU3. Si el kernel no tiene driver para ese
sensor, la cámara no aparece en ninguna aplicación de Linux y CamaraM mostrará solo las
cámaras disponibles; el botón de cambiar cámara se activa en cuanto hay dos o más.

## Generar el instalador

```sh
./build_installer.sh   # crea dist/CamaraM-<versión>-installer.sh y el .tar.gz
```

## Licencia

MIT
