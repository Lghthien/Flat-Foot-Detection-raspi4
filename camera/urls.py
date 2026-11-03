from django.urls import path

from . import views


urlpatterns = [
    path("", views.index, name="index"),
    path("stream.mjpg", views.stream, name="stream"),
    path("api/status", views.api_status, name="api_status"),
    path("api/devices", views.api_devices, name="api_devices"),
    path("api/controls", views.api_controls, name="api_controls"),
    path("api/media", views.api_media, name="api_media"),
    path("api/settings", views.api_settings, name="api_settings"),
    path("api/snapshot", views.api_snapshot, name="api_snapshot"),
    path("api/record/start", views.api_record_start, name="api_record_start"),
    path("api/record/stop", views.api_record_stop, name="api_record_stop"),
    path("api/control", views.api_control, name="api_control"),
    path("api/controls/reset", views.api_controls_reset, name="api_controls_reset"),
    path("api/media/delete", views.api_media_delete, name="api_media_delete"),
    path("media/<str:kind>/<path:name>", views.media_file, name="media_file"),
]
