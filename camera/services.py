import glob
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings

BASE_DIR = Path(settings.MEDIA_ROOT).parent
MEDIA_DIR = Path(settings.MEDIA_ROOT)
PHOTO_DIR = MEDIA_DIR / "photos"
VIDEO_DIR = MEDIA_DIR / "videos"

DEFAULTS = {
    "index": 0,
    "width": 1280,
    "height": 720,
    "fps": 30,
    "format": "auto",
    "jpeg_quality": 75,
    "brightness": 0.0,
    "contrast": 1.0,
    "gamma": 1.5,
    "saturation": 1.0,
    "sharpen": 0.0,
    "clahe": False,
    "flip_h": False,
    "flip_v": False,
    "rotate": 0,
}

SPEC = {
    "index": ("int", 0, 63),
    "width": ("int", 160, 1920),
    "height": ("int", 120, 1080),
    "fps": ("int", 1, 60),
    "format": ("enum", ["auto", "MJPG", "YUYV"]),
    "jpeg_quality": ("int", 30, 100),
    "brightness": ("float", -100.0, 100.0),
    "contrast": ("float", 0.3, 3.0),
    "gamma": ("float", 0.3, 4.0),
    "saturation": ("float", 0.0, 3.0),
    "sharpen": ("float", 0.0, 3.0),
    "clahe": ("bool",),
    "flip_h": ("bool",),
    "flip_v": ("bool",),
    "rotate": ("enum", [0, 90, 180, 270]),
}
RESTART_KEYS = {"index", "width", "height", "fps", "format"}


class ApiError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def clean_value(key, val):
    spec = SPEC[key]
    kind = spec[0]
    if kind == "int":
        return max(spec[1], min(spec[2], int(float(val))))
    if kind == "float":
        return max(spec[1], min(spec[2], float(val)))
    if kind == "bool":
        return bool(val)
    if kind == "enum":
        for o in spec[1]:
            if str(o) == str(val):
                return o
    raise ValueError("Giá trị không hợp lệ cho %s" % key)


def unique_path(folder, prefix, ext):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = folder / ("%s_%s.%s" % (prefix, ts, ext))
    n = 1
    while p.exists():
        p = folder / ("%s_%s_%d.%s" % (prefix, ts, n, ext))
        n += 1
    return p


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "<IP-của-Pi>"


# ----------------------------------------------------------------- thiết bị V4L2
def list_devices(show_all=False):
    devs = []
    paths = glob.glob("/sys/class/video4linux/video*")
    paths.sort(key=lambda x: int(re.sub(r"\D", "", os.path.basename(x)) or 0))
    for p in paths:
        n = int(re.sub(r"\D", "", os.path.basename(p)) or 0)
        try:
            name = open(os.path.join(p, "name")).read().strip()
        except OSError:
            name = "video%d" % n
        try:
            sub = open(os.path.join(p, "index")).read().strip()
        except OSError:
            sub = "0"
        internal = re.match(r"(bcm2835|rpi-|unicam|pispbe|rp1)", name, re.I) is not None
        devs.append({"index": n, "name": name, "sub": sub, "internal": internal})
    if show_all:
        return [{"index": d["index"], "name": d["name"]} for d in devs]
    keep = [d for d in devs if not d["internal"] and d["sub"] == "0"]
    if not keep:
        keep = [d for d in devs if not d["internal"]] or devs
    return [{"index": d["index"], "name": d["name"]} for d in keep]


def resolve_camera_index(index):
    internal_device = re.compile(r"(bcm2835|rpi-|unicam|pispbe|rp1)", re.I)
    camera_indexes = [
        device["index"]
        for device in list_devices()
        if not internal_device.match(device["name"])
    ]
    if index in camera_indexes or not camera_indexes:
        return index
    return camera_indexes[0]


CTRL_RE = re.compile(r"^\s*([a-z0-9_]+)\s+0x[0-9a-f]+\s+\((\w+)\)\s*:\s*(.*)$")
MENU_RE = re.compile(r"^\s+(\d+):\s+(.+?)\s*$")


def v4l2_controls(index):
    exe = shutil.which("v4l2-ctl")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-d", "/dev/video%d" % index, "--list-ctrls-menus"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return []
    ctrls = []
    cur = None
    for line in out.splitlines():
        m = CTRL_RE.match(line)
        if m:
            name, typ, rest = m.groups()
            if typ not in ("int", "bool", "menu"):
                cur = None
                continue
            kv = {k: int(v) for k, v in re.findall(r"\b(min|max|step|default|value)=(-?\d+)", rest)}
            cur = {
                "name": name, "type": typ,
                "min": kv.get("min", 0), "max": kv.get("max", 1), "step": kv.get("step", 1) or 1,
                "default": kv.get("default", 0), "value": kv.get("value", kv.get("default", 0)),
                "inactive": ("inactive" in rest) or ("read-only" in rest),
                "menu": [],
            }
            ctrls.append(cur)
            continue
        mm = MENU_RE.match(line)
        if mm and cur and cur["type"] == "menu":
            cur["menu"].append({"value": int(mm.group(1)), "label": mm.group(2)})
    return ctrls


def v4l2_set(index, name, value):
    exe = shutil.which("v4l2-ctl")
    if not exe:
        raise ApiError(400, "Chưa cài v4l-utils (sudo apt install v4l-utils)")
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise ApiError(400, "Tên điều khiển không hợp lệ")
    r = subprocess.run([exe, "-d", "/dev/video%d" % index, "--set-ctrl", "%s=%d" % (name, int(value))],
                       capture_output=True, text=True, timeout=5)
    if r.returncode != 0:
        raise ApiError(400, r.stderr.strip() or "v4l2-ctl báo lỗi")


# ----------------------------------------------------------------- xử lý ảnh
def to_bgr(frame):
    """Đưa mọi kiểu frame về ảnh BGR uint8 để xử lý/hiển thị."""
    if frame is None:
        return None
    if frame.dtype == np.uint8 and frame.ndim == 3 and frame.shape[2] == 3:
        return frame
    if frame.ndim == 3 and frame.shape[2] == 2 and frame.dtype == np.uint8:
        try:
            return cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_YUYV)
        except cv2.error:
            frame = frame[:, :, 0]
    if frame.ndim == 3 and frame.shape[2] == 1:
        frame = frame[:, :, 0]
    if frame.ndim == 2:
        if frame.dtype == np.uint8:
            return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        norm = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        return cv2.applyColorMap(norm, cv2.COLORMAP_JET)
    return cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


class Recorder:
    def __init__(self, cam, ffmpeg, preset):
        self.cam = cam
        self.ffmpeg = ffmpeg
        self.preset = preset
        self.active = False
        self.name = ""
        self.t0 = 0.0
        self.size = (0, 0)
        self.fps = 30
        self._stop = threading.Event()
        self._thread = None
        self._proc = None
        self._writer = None

    def start(self):
        if self.active:
            raise ApiError(409, "Đang quay video rồi")
        img = self.cam.latest
        if img is None:
            raise ApiError(503, "Chưa có hình từ camera")
        h, w = img.shape[:2]
        w -= w % 2
        h -= h % 2
        fps = max(1, min(30, self.cam.get("fps")))
        ext = "mp4" if self.ffmpeg else "avi"
        path = unique_path(VIDEO_DIR, "video", ext)
        if self.ffmpeg:
            cmd = [self.ffmpeg, "-y", "-loglevel", "error",
                   "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "%dx%d" % (w, h), "-r", str(fps), "-i", "-",
                   "-c:v", "libx264", "-preset", self.preset, "-crf", "23", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", str(path)]
            self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        else:
            self._writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
            if not self._writer.isOpened():
                raise ApiError(500, "Không tạo được file video")
        self.name = path.name
        self.size = (w, h)
        self.fps = fps
        self.t0 = time.time()
        self._stop.clear()
        self.active = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self.name

    def _run(self):
        w, h = self.size
        period = 1.0 / self.fps
        nxt = time.time()
        try:
            while not self._stop.is_set():
                img = self.cam.latest
                if img is not None:
                    if img.shape[1] != w or img.shape[0] != h:
                        img = cv2.resize(img, (w, h))
                    img = np.ascontiguousarray(img)
                    if self._proc is not None:
                        self._proc.stdin.write(img.data)
                    else:
                        self._writer.write(img)
                nxt += period
                delay = nxt - time.time()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -1.0:
                    nxt = time.time()
        except (BrokenPipeError, OSError):
            pass
        finally:
            self._close()

    def _close(self):
        if self._proc is not None:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=60)
            except Exception:
                self._proc.kill()
            self._proc = None
        if self._writer is not None:
            self._writer.release()
            self._writer = None
        self.active = False

    def stop(self):
        if not self.active:
            raise ApiError(409, "Chưa quay video")
        name = self.name
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=90)
        return name


class CameraService:
    def __init__(self, settings, ffmpeg, preset):
        self.s = dict(DEFAULTS)
        self.s.update(settings)
        self.lock = threading.Lock()
        self.cond = threading.Condition()
        self.jpeg = None
        self.seq = 0
        self.latest = None
        self.clients = 0
        self.restart = threading.Event()
        self.running = True
        self.error = ""
        self.info = {"ok": False, "fourcc": "", "width": 0, "height": 0}
        self.fps = 0.0
        self.ffmpeg = ffmpeg
        self.rec = Recorder(self, ffmpeg, preset)
        self._lut = None
        self._lut_key = None
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self._thread = threading.Thread(target=self._loop, daemon=True)

    # --- cấu hình
    def get(self, key):
        with self.lock:
            return self.s[key]

    def settings(self):
        with self.lock:
            return dict(self.s)

    def update(self, patch):
        new = {}
        for k, v in patch.items():
            if k in SPEC:
                try:
                    new[k] = clean_value(k, v)
                except (ValueError, TypeError):
                    raise ApiError(400, "Giá trị không hợp lệ cho %s" % k)
        with self.lock:
            restart = [k for k in new if k in RESTART_KEYS and new[k] != self.s.get(k)]
        if restart and self.rec.active:
            raise ApiError(409, "Hãy dừng quay video trước khi đổi camera/độ phân giải/FPS")
        with self.lock:
            self.s.update(new)
        if restart:
            self.restart.set()

    # --- vòng lặp camera
    def start(self):
        self._thread.start()

    def stop(self):
        self.running = False
        if self.rec.active:
            try:
                self.rec.stop()
            except ApiError:
                pass
        self._thread.join(timeout=3)

    def add_client(self):
        with self.cond:
            self.clients += 1

    def remove_client(self):
        with self.cond:
            self.clients = max(0, self.clients - 1)

    def _open(self):
        s = self.settings()
        camera_index = resolve_camera_index(s["index"])
        if camera_index != s["index"]:
            s["index"] = camera_index
            with self.lock:
                self.s["index"] = camera_index
        prefs = {"auto": ["MJPG", None], "MJPG": ["MJPG"], "YUYV": ["YUYV"]}.get(s["format"], ["MJPG", None])
        for fmt in prefs:
            cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
            if not cap.isOpened():
                cap.release()
                continue
            if fmt:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fmt))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, s["width"])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, s["height"])
            cap.set(cv2.CAP_PROP_FPS, s["fps"])
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            got = False
            for _ in range(20):
                ok, f = cap.read()
                if ok and f is not None:
                    got = True
                    break
                time.sleep(0.05)
            if got:
                code = int(cap.get(cv2.CAP_PROP_FOURCC))
                self.info = {
                    "ok": True,
                    "fourcc": "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4)).strip(),
                    "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                }
                return cap
            cap.release()
        return None

    def _loop(self):
        cap = None
        last = time.time()
        fail = 0
        while self.running:
            if cap is None or self.restart.is_set():
                self.restart.clear()
                if cap is not None:
                    cap.release()
                    cap = None
                self.info["ok"] = False
                cap = self._open()
                if cap is None:
                    self.error = "Không mở được /dev/video%d (hoặc không đọc được hình)" % self.get("index")
                    time.sleep(1.0)
                    continue
                self.error = ""
                fail = 0
                last = time.time()
            ok, frame = cap.read()
            if not ok or frame is None:
                fail += 1
                if fail > 40:
                    cap.release()
                    cap = None
                    self.info["ok"] = False
                    self.error = "Mất tín hiệu camera, đang thử kết nối lại..."
                time.sleep(0.02)
                continue
            fail = 0
            now = time.time()
            dt = now - last
            last = now
            if dt > 0:
                inst = 1.0 / dt
                self.fps = inst if self.fps == 0 else self.fps * 0.9 + inst * 0.1
            try:
                out = self.process(frame)
            except Exception as e:  # không để một frame lỗi làm sập luồng
                self.error = "Lỗi xử lý ảnh: %s" % e
                continue
            jpg = None
            if self.clients > 0:
                ok2, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, self.get("jpeg_quality")])
                if ok2:
                    jpg = buf.tobytes()
            with self.cond:
                self.latest = out
                if jpg is not None:
                    self.jpeg = jpg
                self.seq += 1
                self.cond.notify_all()
        if cap is not None:
            cap.release()

    def process(self, frame):
        s = self.settings()
        img = to_bgr(frame)
        if img is None:
            raise ValueError("frame rỗng")
        rot = s["rotate"]
        if rot == 90:
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        elif rot == 180:
            img = cv2.rotate(img, cv2.ROTATE_180)
        elif rot == 270:
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if s["flip_h"] and s["flip_v"]:
            img = cv2.flip(img, -1)
        elif s["flip_h"]:
            img = cv2.flip(img, 1)
        elif s["flip_v"]:
            img = cv2.flip(img, 0)
        # gamma + tương phản + độ sáng gộp trong một bảng tra LUT
        key = (round(s["gamma"], 3), round(s["contrast"], 3), round(s["brightness"], 2))
        if key != self._lut_key:
            x = np.arange(256, dtype=np.float32) / 255.0
            y = np.power(x, 1.0 / max(0.1, s["gamma"])) * 255.0
            y = (y - 128.0) * s["contrast"] + 128.0 + s["brightness"]
            self._lut = np.clip(y, 0, 255).astype(np.uint8)
            self._lut_key = key
        img = cv2.LUT(img, self._lut)
        if s["clahe"]:
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            l = self._clahe.apply(l)
            img = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
        if abs(s["saturation"] - 1.0) > 0.01:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            hsv[:, :, 1] = cv2.convertScaleAbs(hsv[:, :, 1], alpha=s["saturation"])
            img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        if s["sharpen"] > 0.01:
            blur = cv2.GaussianBlur(img, (0, 0), 1.2)
            img = cv2.addWeighted(img, 1.0 + s["sharpen"], blur, -s["sharpen"], 0)
        return img

    # --- hành động
    def snapshot(self):
        img = self.latest
        if img is None:
            raise ApiError(503, "Chưa có hình từ camera")
        path = unique_path(PHOTO_DIR, "photo", "jpg")
        cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        return path.name

    def status(self):
        img = self.latest
        h, w = (img.shape[:2] if img is not None else (0, 0))
        rec = self.rec
        return {
            "ok": self.info["ok"],
            "error": self.error,
            "width": w,
            "height": h,
            "fourcc": self.info["fourcc"],
            "fps": round(self.fps, 1) if self.info["ok"] else 0,
            "clients": self.clients,
            "recording": rec.active,
            "rec_seconds": round(time.time() - rec.t0, 1) if rec.active else 0,
            "rec_file": rec.name if rec.active else "",
            "ffmpeg": bool(self.ffmpeg),
            "settings": self.settings(),
            "paths": {"photos": str(PHOTO_DIR), "videos": str(VIDEO_DIR)},
        }


def media_list(cam):
    cur = cam.rec.name if cam.rec.active else None
    out = {"photos": [], "videos": []}
    for kind, folder, exts in (("photos", PHOTO_DIR, (".jpg", ".jpeg", ".png")),
                               ("videos", VIDEO_DIR, (".mp4", ".avi", ".webm"))):
        items = []
        for p in folder.iterdir():
            if p.suffix.lower() in exts and p.name != cur:
                st = p.stat()
                items.append({"name": p.name, "size": st.st_size, "mtime": st.st_mtime,
                              "url": "/media/%s/%s" % (kind, p.name)})
        items.sort(key=lambda x: x["mtime"], reverse=True)
        out[kind] = items
    return out
