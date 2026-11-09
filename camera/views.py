import json
import mimetypes
import re
from pathlib import Path

from django.conf import settings
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import render
from django.utils.http import content_disposition_header
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .runtime import get_camera
from .services import (
    ApiError,
    PHOTO_DIR,
    VIDEO_DIR,
    list_devices,
    media_list,
    v4l2_controls,
    v4l2_set,
)


@ensure_csrf_cookie
@never_cache
def index(request):
    response = render(request, "camera/index.html")
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


def _json_error(error):
    return JsonResponse({"error": error.msg}, status=error.code)


def _request_data(request):
    try:
        data = json.loads(request.body or b"{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ApiError(400, "Invalid JSON data") from error
    if not isinstance(data, dict):
        raise ApiError(400, "Data must be a JSON object")
    return data


@require_GET
def api_status(request):
    return JsonResponse(get_camera().status())


@require_GET
def api_devices(request):
    return JsonResponse({"devices": list_devices(settings.DS325_SHOW_ALL_DEVICES)})


@require_GET
def api_controls(request):
    controls = v4l2_controls(get_camera().get("index"))
    return JsonResponse({"available": controls is not None, "controls": controls or []})


@require_GET
def api_media(request):
    return JsonResponse(media_list(get_camera()))


@require_POST
def api_settings(request):
    try:
        camera = get_camera()
        camera.update(_request_data(request))
        return JsonResponse(camera.status())
    except ApiError as error:
        return _json_error(error)


@require_POST
def api_snapshot(request):
    try:
        return JsonResponse({"ok": True, "name": get_camera().snapshot()})
    except ApiError as error:
        return _json_error(error)


@require_POST
def api_record_start(request):
    try:
        return JsonResponse({"ok": True, "name": get_camera().rec.start()})
    except ApiError as error:
        return _json_error(error)


@require_POST
def api_record_stop(request):
    try:
        return JsonResponse({"ok": True, "name": get_camera().rec.stop()})
    except ApiError as error:
        return _json_error(error)


@require_POST
def api_control(request):
    try:
        camera = get_camera()
        data = _request_data(request)
        v4l2_set(camera.get("index"), str(data.get("name", "")), data.get("value", 0))
        return JsonResponse({"ok": True})
    except ApiError as error:
        return _json_error(error)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid control value"}, status=400)


@require_POST
def api_controls_reset(request):
    try:
        camera = get_camera()
        for control in v4l2_controls(camera.get("index")) or []:
            if not control["inactive"]:
                try:
                    v4l2_set(camera.get("index"), control["name"], control["default"])
                except ApiError:
                    continue
        return JsonResponse({"ok": True})
    except ApiError as error:
        return _json_error(error)


@require_POST
def api_media_delete(request):
    try:
        camera = get_camera()
        data = _request_data(request)
        path = _media_path(str(data.get("kind", "")), str(data.get("name", "")))
        if camera.rec.active and path.name == camera.rec.name:
            raise ApiError(409, "The file is currently being recorded")
        path.unlink()
        return JsonResponse({"ok": True})
    except ApiError as error:
        return _json_error(error)


def _stream_frames(camera):
    camera.add_client()
    last = -1
    try:
        while camera.running:
            with camera.cond:
                camera.cond.wait_for(
                    lambda: camera.seq != last and camera.jpeg is not None,
                    timeout=3,
                )
                data = camera.jpeg if camera.seq != last else None
                last = camera.seq
            if data is not None:
                yield (
                    b"--FRAME\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(data)).encode("ascii")
                    + b"\r\n\r\n"
                    + data
                    + b"\r\n"
                )
    finally:
        camera.remove_client()


@require_GET
def stream(request):
    response = StreamingHttpResponse(
        _stream_frames(get_camera()),
        content_type="multipart/x-mixed-replace; boundary=FRAME",
    )
    response["Cache-Control"] = "no-cache, private"
    response["Pragma"] = "no-cache"
    response["Age"] = "0"
    return response


def _media_path(kind, name):
    folders = {"photos": PHOTO_DIR, "videos": VIDEO_DIR}
    folder = folders.get(kind)
    if folder is None:
        raise Http404("Not found")
    path = folder / Path(name).name
    if not path.is_file():
        raise Http404("File not found")
    return path


@require_GET
def media_file(request, kind, name):
    path = _media_path(kind, name)
    size = path.stat().st_size
    start, end = 0, size - 1
    status = 200
    range_header = request.headers.get("Range")
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match or size == 0:
            return HttpResponse(
                status=416, headers={"Content-Range": f"bytes */{size}"}
            )
        first, last = match.groups()
        try:
            if first:
                start = int(first)
                if last:
                    end = min(int(last), size - 1)
            elif last:
                start = max(0, size - int(last))
            else:
                return HttpResponse(
                    status=416,
                    headers={"Content-Range": f"bytes */{size}"},
                )
        except ValueError:
            return HttpResponse(
                status=416, headers={"Content-Range": f"bytes */{size}"}
            )
        if start > end or start >= size:
            return HttpResponse(
                status=416, headers={"Content-Range": f"bytes */{size}"}
            )
        status = 206

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    file_obj = path.open("rb")
    file_obj.seek(start)
    response = FileResponse(file_obj, status=status, content_type=media_type)
    response["Accept-Ranges"] = "bytes"
    response["Content-Length"] = str(end - start + 1)
    if status == 206:
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
    if request.GET.get("dl") is not None:
        response["Content-Disposition"] = content_disposition_header(
            as_attachment=True,
            filename=path.name,
        )
    if end >= start:
        response.streaming_content = _limited_file(
            response.streaming_content, end - start + 1
        )
    return response


def _limited_file(chunks, remaining):
    for chunk in chunks:
        if remaining <= 0:
            break
        data = chunk[:remaining]
        remaining -= len(data)
        yield data
