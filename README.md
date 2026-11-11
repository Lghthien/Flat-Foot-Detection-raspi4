# DS325 Studio

Django web interface for a SoftKinetic DS325 camera on Linux/Raspberry Pi.

For Flutter or other client integrations, see the [Camera API guide](API.md).

## Project structure

```text
ds325_studio/
├── camera/                 # Camera logic, API, templates, CSS, JavaScript
├── ds325_project/          # Django settings and app entry points (ASGI/WSGI)
├── media/
│   ├── photos/             # Captured photos
│   └── videos/             # Recorded videos
├── .venv/                  # Python virtual environment
├── manage.py               # Django management command entry point
├── ds325_cam.py            # Compatibility launcher
├── requirements.txt        # Python dependencies
└── README.md
```

## Install

Install the system camera utilities and Python dependencies:

```bash
sudo apt install python3-venv python3-opencv python3-numpy v4l-utils ffmpeg
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

On a non-Raspberry Pi Linux host, install compatible `numpy` and
`opencv-python-headless` packages in the virtual environment as well.

## Run

```bash
cd ~/Downloads/ds325_studio
source .venv/bin/activate
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Open `http://<Pi-IP>:8000`. The compatibility entry point
`python ds325_cam.py` also starts Django's development server.
Open `http://<Pi-IP>:8000/admin/` and sign in with the superuser created above
to use Django Admin.
On the camera page, use `+`/`−` or the mouse wheel to zoom the live preview
from 25% to 400%; drag the zoomed image to inspect other areas and select
`Reset` to restore 100%.

The guided foot capture workflow records four labeled views per session: the
left sole, right sole, left medial arch, and right medial arch. Photos are
tagged with an automatically generated session ID and view name in the gallery
and filename. Use anonymized records only. This workflow organizes images; it
does not diagnose medical conditions.

Camera settings can be supplied through environment variables:
`DS325_CAMERA_INDEX`, `DS325_CAMERA_WIDTH`, `DS325_CAMERA_HEIGHT`,
`DS325_CAMERA_FPS`, `DS325_FFMPEG_PRESET`, and `DS325_SHOW_ALL_DEVICES=1`.
If the configured camera index is not a detected external camera, the app
automatically selects the first detected external camera (for example
`/dev/video1` on some Raspberry Pi setups).
For lower live-view latency on Raspberry Pi, the defaults are 640x480 at 15 FPS,
JPEG quality 75, and no sharpening. You can choose 1280x720 in the camera page
when you prefer more detail, at the cost of higher CPU/network load.
Media is stored in `media/photos` and `media/videos`; set `DS325_MEDIA_ROOT` to
change the root directory.

The camera is initialized on the first request. The server controls camera
hardware and has no user login, so only expose it to a trusted LAN. For a
production deployment, configure `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
set `DJANGO_DEBUG=0`, collect static assets with `python manage.py collectstatic`,
and use a production WSGI server with a single worker because one camera device
cannot be shared between multiple independent camera-service workers. Django's
`runserver` is for development only.

Run the application checks and tests with:

```bash
python manage.py check
python manage.py test camera
```
# Flat-Foot-Detection
