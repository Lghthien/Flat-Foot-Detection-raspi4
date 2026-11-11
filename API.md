# Raspberry Pi Camera API

This document describes the HTTP API provided by the Django camera application.
The Raspberry Pi controls the camera; a Flutter app connects to the Pi over the
same Wi-Fi or private hotspot.

## Connection

Find the Pi's address on its current network, then set the app's base URL:

```text
http://<PI_ADDRESS>:8000
```

For example:

```text
http://192.168.1.31:8000
```

Replace the example address with the actual address configured on the Pi. The
phone and Pi must be able to reach each other, and the Pi firewall/network must
allow TCP port `8000`.

All paths below are relative to the base URL. JSON request bodies use
`Content-Type: application/json`. JSON error responses have this shape:

```json
{"error": "Description of the error"}
```

## CSRF requirement for POST requests

Django CSRF protection is enabled. Before sending any `POST` request:

1. Send `GET /` and retain the `csrftoken` cookie from the response.
2. Send that cookie with every POST request.
3. Set the `X-CSRFToken` header to the same token value.

The Flutter HTTP client must preserve cookies between requests. Native Flutter
HTTP clients do not use browser CORS rules, but they still need to send the
CSRF cookie and header.

## Endpoints

The endpoint names below are API titles. The suggested Flutter screen titles
are user-facing labels; you can rename them without changing the API.

| API title | Method and path | Flutter screen / action | When to call |
|---|---|---|---|
| Camera status | `GET /api/status` | **Connect to Raspberry Pi** / camera status badge | On app startup, when reconnecting, and periodically while viewing the camera |
| Live camera stream | `GET /stream.mjpg` | **Live Camera** / preview panel | When the user opens the camera or capture screen |
| Camera devices | `GET /api/devices` | **Camera Settings** / device picker | When opening camera settings or after changing the selected device |
| Hardware controls | `GET /api/controls` | **Camera Settings** / hardware controls | When opening the hardware-controls section |
| Media library | `GET /api/media` | **Photo Gallery** / **Video Gallery** | When opening or refreshing a gallery |
| Capture photo | `POST /api/snapshot` | **Capture Session** / capture button | For a regular photo or one labeled step in a guided session |
| Update camera settings | `POST /api/settings` | **Camera Settings** | When the user changes software image/camera settings |
| Start recording | `POST /api/record/start` | **Video Recording** / start button | When the user starts recording |
| Stop recording | `POST /api/record/stop` | **Video Recording** / stop button | When the user stops recording |
| Set hardware control | `POST /api/control` | **Camera Settings** / a hardware-control widget | When a hardware control changes |
| Reset hardware controls | `POST /api/controls/reset` | **Camera Settings** / reset button | Only after the user requests a hardware reset |
| Delete media | `POST /api/media/delete` | **Photo Gallery** or **Video Gallery** / delete action | After the user confirms deletion |
| Open or download media | `GET /media/<kind>/<filename>` | **Photo Viewer** or **Video Player** | To display, stream, or download a saved file |

### `GET /api/status`

Get camera connection, recording, settings, and media-directory status.

```json
{
  "ok": true,
  "error": "",
  "width": 640,
  "height": 480,
  "fourcc": "MJPG",
  "fps": 15.0,
  "clients": 1,
  "recording": false,
  "rec_seconds": 0,
  "rec_file": "",
  "ffmpeg": true,
  "settings": {
    "index": 0,
    "width": 640,
    "height": 480,
    "fps": 15,
    "format": "auto",
    "jpeg_quality": 75,
    "brightness": 0.0,
    "contrast": 1.0,
    "gamma": 1.5,
    "saturation": 1.0,
    "sharpen": 0.0,
    "clahe": false,
    "flip_h": false,
    "flip_v": false,
    "rotate": 0
  },
  "paths": {
    "photos": "/path/on/pi/media/photos",
    "videos": "/path/on/pi/media/videos"
  }
}
```

`ok` indicates whether the camera is currently available. `error` contains a
camera error message when one is present. Use `settings` as the current camera
configuration; directory paths are informational server paths and should not be
used as phone file paths.

### `GET /stream.mjpg`

Returns an MJPEG stream with content type
`multipart/x-mixed-replace; boundary=FRAME`. Use an MJPEG-capable client or
decode each multipart JPEG frame; this endpoint is not a single JPEG image.

### `GET /api/devices`

List detected camera devices.

```json
{
  "devices": [
    {"index": 0, "name": "Camera"}
  ]
}
```

### `GET /api/controls`

List V4L2 hardware controls for the selected camera.

```json
{
  "available": true,
  "controls": [
    {
      "name": "brightness",
      "type": "int",
      "min": 0,
      "max": 255,
      "step": 1,
      "default": 128,
      "value": 128,
      "inactive": false,
      "menu": []
    }
  ]
}
```

When `available` is false, install `v4l-utils` on the Pi. Controls are hardware-
dependent; integer, boolean, and menu controls may be returned.

### `GET /api/media`

List saved media. `mtime` is a Unix timestamp in seconds; `size` is bytes and
`url` is relative to the base URL.

```json
{
  "photos": [
    {
      "name": "capture_abc123_left_sole_20261109_120000.jpg",
      "size": 55231,
      "mtime": 1794200400.0,
      "url": "/media/photos/capture_abc123_left_sole_20261109_120000.jpg",
      "capture_session": "abc123",
      "capture_view": "left_sole"
    }
  ],
  "videos": []
}
```

The `capture_session` and `capture_view` properties are present on labeled
guided-capture photos. Existing photos and ordinary snapshots do not have these
properties.

### `POST /api/snapshot`

Take a regular photo:

```json
{}
```

Response:

```json
{"ok": true, "name": "photo_20261109_120000.jpg"}
```

Take a labeled photo as part of a guided capture session:

```json
{
  "view": "left_sole",
  "session_id": "abc123"
}
```

Supported `view` values:

| Value | View |
|---|---|
| `left_sole` | Left sole |
| `right_sole` | Right sole |
| `left_medial` | Left medial arch |
| `right_medial` | Right medial arch |

`session_id` must be 1–32 lowercase letters, digits, or hyphens. Use the same
ID for all four photos in one capture session. A request without an available
camera image returns HTTP `503`; invalid capture metadata returns HTTP `400`.

### `POST /api/settings`

Update one or more software camera settings. Send only fields to change.

```json
{
  "width": 640,
  "height": 480,
  "fps": 15,
  "brightness": 10,
  "flip_h": false
}
```

Supported fields and ranges:

| Field | Values |
|---|---|
| `index` | Integer, 0–63 |
| `width` | Integer, 160–1920 |
| `height` | Integer, 120–1080 |
| `fps` | Integer, 1–60 |
| `format` | `auto`, `MJPG`, or `YUYV` |
| `jpeg_quality` | Integer, 30–100 |
| `brightness` | Number, -100–100 |
| `contrast` | Number, 0.3–3 |
| `gamma` | Number, 0.3–4 |
| `saturation` | Number, 0–3 |
| `sharpen` | Number, 0–3 |
| `clahe`, `flip_h`, `flip_v` | Boolean |
| `rotate` | `0`, `90`, `180`, or `270` |

The successful response is the updated status object. Changing camera device,
resolution, FPS, or format while recording returns HTTP `409`.

The app should send only the changed fields, not settings that have not
changed. This endpoint responds with the full status object, so it can also
refresh the app's camera state.

### `POST /api/record/start` and `POST /api/record/stop`

Start or stop video recording. A request body is not required.

```json
{"ok": true, "name": "video_20261109_120000.mp4"}
```

Starting an active recording or stopping when not recording returns HTTP `409`.
If FFmpeg is unavailable, the Pi may save an `.avi` file instead.

### `POST /api/control`

Set a V4L2 hardware control using a control name from `GET /api/controls`.

```json
{"name": "brightness", "value": 128}
```

Success response: `{"ok": true}`.

### `POST /api/controls/reset`

Reset available, active V4L2 hardware controls to their reported defaults.
A request body is not required. Success response: `{"ok": true}`.

### `POST /api/media/delete`

Delete a saved photo or video by its kind and filename.

```json
{"kind": "photos", "name": "photo_20261109_120000.jpg"}
```

`kind` must be `photos` or `videos`. Success response: `{"ok": true}`.
Possible errors include `404` if the file is absent, `403` if the Pi process
cannot delete it, and `409` if the file is currently being recorded.

### `GET /media/<kind>/<filename>`

Download or display a saved file. The endpoint supports HTTP byte ranges for
media seeking. Add `?dl=1` to request a download:

```text
/media/photos/photo_20261109_120000.jpg?dl=1
```

## Minimal Flutter request sequence

1. Configure and save the Pi base URL.
2. `GET /` and retain the CSRF cookie.
3. Poll `GET /api/status` until `ok` is true.
4. Open `/stream.mjpg` in an MJPEG-capable view.
5. For each guided view, POST its `view` and shared `session_id` to
   `/api/snapshot`.
6. Refresh `GET /api/media` and render each returned media URL as
   `baseUrl + url`.

## Suggested Flutter screen titles and purpose

These are suggested app navigation titles and are not extra server endpoints.

### 1. Connect to Raspberry Pi

Purpose: select which Pi the phone controls. Provide a base-URL field, a
connect/retry button, and a connection status indicator.

- Ask for the full base URL, such as `http://192.168.4.1:8000`.
- Do not hard-code the example address: the address depends on the hotspot or
  network configuration.
- Send `GET /` first so the client receives its CSRF cookie.
- Then send `GET /api/status`.
- Show **Connected** only when the request succeeds and the response has
  `"ok": true`. If `"ok": false`, show the `error` message and let the user
  retry.
- Store the base URL on the phone for the next launch. Provide an obvious way
  to edit it when moving to another network.

### 2. Live Camera

Purpose: show the Pi's camera preview and let the user navigate to capture.

- Check `GET /api/status` before showing capture actions.
- Open `/stream.mjpg` in a view that supports MJPEG multipart streams.
- Show camera resolution and FPS from the status response.
- When the stream disconnects, retry the status request and reconnect the
  stream when the camera is available again.
- Keep camera adjustments stable during a guided session so all images are
  captured consistently.

### 3. Capture Session

Purpose: guide the user through the four requested views and associate their
photos with one anonymous session ID.

1. Generate a session ID using only lowercase letters, digits, and hyphens;
   keep it between 1 and 32 characters. For example, `exam-20261109-a1`.
2. Keep the same ID until all views are complete or the user cancels.
3. Show one instruction at a time:
   - **Left sole** — `left_sole`
   - **Right sole** — `right_sole`
   - **Left medial arch** — `left_medial`
   - **Right medial arch** — `right_medial`
4. On each capture tap, send a POST to `/api/snapshot`, for example:

   ```json
   {
     "view": "left_sole",
     "session_id": "exam-20261109-a1"
   }
   ```

5. Advance to the next view only after a successful response. If the response
   is an error, keep the current step so the user can retry.
6. After the fourth successful capture, show a completion state and refresh
   **Photo Gallery** with `GET /api/media`.

The server saves the files on the Pi. The `name` in the snapshot response is
the saved filename; it is not a local path on the phone.

### 4. Photo Gallery and Photo Viewer

Purpose: browse photos saved on the Pi, open them, download them, or request
deletion.

- Get the latest list from `GET /api/media`.
- Build an image URL by joining the base URL with the item's `url`, for example:
  `http://192.168.4.1:8000/media/photos/photo.jpg`.
- For guided photos, use `capture_view` as the display title and
  `capture_session` to group related images. These fields are absent on older
  and regular photos.
- Send `POST /api/media/delete` with `{"kind":"photos","name":"..."}` only
  after the user confirms. Refresh the list after success.
- To download, open the media URL with `?dl=1`.

### 5. Video Gallery and Video Player

Purpose: list and play recordings saved on the Pi.

- Use the `videos` array from `GET /api/media`.
- Play the returned media URL. The server supports byte-range requests, which
  allow players to seek through supported video files.
- If FFmpeg is unavailable on the Pi, a recording may be `.avi`; some phone
  players cannot play that format. Offer a download action in that case.
- Delete a recording with `POST /api/media/delete` and
  `{"kind":"videos","name":"..."}` after confirmation.

### 6. Camera Settings

Purpose: configure software image processing and physical camera controls.

- Use `GET /api/status` to populate software-setting values.
- Use `GET /api/devices` to populate the camera-device picker.
- Use `GET /api/controls` to populate V4L2 hardware controls.
- Send changed software settings to `POST /api/settings`.
- Send one physical control change to `POST /api/control`, using the control
  `name` reported by `/api/controls`.
- A hardware-control list may be unavailable or empty; hide or disable those
  controls rather than treating that as a camera failure.
- Changing device, resolution, FPS, or format while recording is rejected with
  HTTP `409`. Stop the recording first.

### 7. Video Recording

Purpose: start, monitor, and stop a recording.

- Read `recording` from `GET /api/status` to determine whether recording is
  active.
- Call `POST /api/record/start` to start, and
  `POST /api/record/stop` to stop.
- Use `rec_seconds` and `rec_file` from status to show elapsed time and the
  active filename.
- Refresh `GET /api/media` after stopping so the completed recording appears.

## Flutter/Dio CSRF example

Use a persistent cookie jar so the CSRF cookie from `GET /` is sent with later
POST requests. Add compatible `dio`, `cookie_jar`, and `dio_cookie_manager`
packages to the Flutter project.

```dart
import 'package:cookie_jar/cookie_jar.dart';
import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';

class PiCameraApi {
  PiCameraApi(String baseUrl)
      : baseUri = Uri.parse(baseUrl),
        dio = Dio(BaseOptions(
          baseUrl: baseUrl,
          connectTimeout: const Duration(seconds: 5),
          receiveTimeout: const Duration(seconds: 15),
          headers: {'Content-Type': 'application/json'},
        )) {
    dio.interceptors.add(CookieManager(cookieJar));
  }

  final Dio dio;
  final Uri baseUri;
  final CookieJar cookieJar = CookieJar();

  Future<void> initialize() async {
    await dio.get('/');
  }

  Future<String> _csrfToken() async {
    final cookies = await cookieJar.loadForRequest(baseUri);
    for (final cookie in cookies) {
      if (cookie.name == 'csrftoken' && cookie.value.isNotEmpty) {
        return cookie.value;
      }
    }
    throw StateError('CSRF token not found. Call initialize() first.');
  }

  Future<Response<T>> post<T>(String path, Map<String, dynamic> body) async {
    final token = await _csrfToken();
    return dio.post<T>(
      path,
      data: body,
      options: Options(headers: {'X-CSRFToken': token}),
    );
  }

  Future<Map<String, dynamic>> getStatus() async {
    final response = await dio.get<Map<String, dynamic>>('/api/status');
    return response.data!;
  }

  Future<String> captureView({
    required String view,
    required String sessionId,
  }) async {
    final response = await post<Map<String, dynamic>>('/api/snapshot', {
      'view': view,
      'session_id': sessionId,
    });
    return response.data!['name'] as String;
  }
}
```

In production code, use a `PersistCookieJar` if the CSRF cookie should survive
app restarts. The example's `CookieJar` is in-memory and must be initialized
again after an app restart.

## HTTP status codes to handle

| Status | Meaning | Suggested app behavior |
|---|---|---|
| `200` | Request succeeded | Read the JSON response |
| `400` | Invalid JSON, unsupported value, or invalid capture metadata | Show the server's `error`; let the user correct input |
| `403` | CSRF check failed or file deletion permission denied | Refresh CSRF state or ask the Pi administrator to fix media-folder permissions |
| `404` | Requested media file does not exist | Refresh the gallery |
| `409` | Operation conflicts with current state, such as changing resolution while recording | Explain the conflict and offer to stop recording first |
| `416` | Invalid byte range when requesting media | Re-open the media URL without the invalid range |
| `500` | Unexpected server/file-system error | Show a generic retry message; inspect Pi server logs |
| `503` | Camera has no available frame yet | Keep the capture step and retry after status becomes ready |

## Security and clinical-use notes

The current API has no user authentication and uses plain HTTP by default.
Keep it on a private, trusted network; do not expose it directly to the
Internet or an untrusted hospital network. Before storing identifiable patient
images or production use, add authentication and encrypted transport (HTTPS)
and follow the facility's privacy and data-retention requirements. The API
captures and organizes photos; it does not diagnose medical conditions.
