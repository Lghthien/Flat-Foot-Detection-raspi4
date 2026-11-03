import atexit
import shutil
import threading

from django.conf import settings

from .services import CameraService, PHOTO_DIR, VIDEO_DIR


_camera = None
_camera_lock = threading.Lock()


def get_camera():
    global _camera
    with _camera_lock:
        if _camera is None:
            PHOTO_DIR.mkdir(parents=True, exist_ok=True)
            VIDEO_DIR.mkdir(parents=True, exist_ok=True)
            camera = CameraService(
                settings.DS325_CAMERA_OPTIONS,
                shutil.which("ffmpeg"),
                settings.DS325_FFMPEG_PRESET,
            )
            camera.start()
            _camera = camera
            atexit.register(camera.stop)
        return _camera
