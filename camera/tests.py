from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import Client, SimpleTestCase
from django.urls import reverse

from .services import DEFAULTS, resolve_camera_index


class CameraPageTests(SimpleTestCase):
    def test_stream_processing_defaults_favor_low_latency(self):
        self.assertEqual(DEFAULTS["jpeg_quality"], 75)
        self.assertEqual(DEFAULTS["sharpen"], 0.0)

    @patch("camera.services.list_devices")
    def test_missing_camera_index_falls_back_to_first_external_camera(
        self, list_devices
    ):
        list_devices.return_value = [
            {"index": 10, "name": "bcm2835-codec-decode"},
            {"index": 1, "name": "Creative GestureCam"},
            {"index": 2, "name": "Creative GestureCam"},
        ]

        self.assertEqual(resolve_camera_index(0), 1)

    @patch("camera.services.list_devices")
    def test_available_camera_index_is_preserved(self, list_devices):
        list_devices.return_value = [
            {"index": 1, "name": "Creative GestureCam"},
            {"index": 2, "name": "Creative GestureCam"},
        ]

        self.assertEqual(resolve_camera_index(2), 2)

    @patch("camera.services.list_devices")
    def test_internal_devices_are_not_used_for_camera_fallback(self, list_devices):
        list_devices.return_value = [
            {"index": 10, "name": "bcm2835-codec-decode"},
            {"index": 13, "name": "bcm2835-isp-output0"},
        ]

        self.assertEqual(resolve_camera_index(0), 0)

    def test_homepage_renders_studio(self):
        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DS325 Studio")
        self.assertIn("no-store", response["Cache-Control"])

    def test_django_admin_route_is_configured(self):
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    @patch("camera.views.get_camera")
    def test_settings_endpoint_updates_camera(self, get_camera):
        camera = get_camera.return_value
        camera.status.return_value = {"ok": True}

        response = self.client.post(
            reverse("api_settings"),
            data='{"brightness": 12}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        camera.update.assert_called_once_with({"brightness": 12})
        self.assertEqual(response.json(), {"ok": True})

    def test_settings_endpoint_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        page = client.get(reverse("index"))
        token = page.cookies["csrftoken"].value

        with patch("camera.views.get_camera") as get_camera:
            get_camera.return_value.status.return_value = {"ok": True}
            response = client.post(
                reverse("api_settings"),
                data='{"brightness": 12}',
                content_type="application/json",
                HTTP_X_CSRFTOKEN=token,
            )

        self.assertEqual(response.status_code, 200)

    def test_settings_endpoint_rejects_stale_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("index"))

        with patch("camera.views.get_camera") as get_camera:
            response = client.post(
                reverse("api_settings"),
                data='{"brightness": 12}',
                content_type="application/json",
                HTTP_X_CSRFTOKEN="stale-token",
            )

        self.assertEqual(response.status_code, 403)
        get_camera.assert_not_called()

    def test_media_file_respects_byte_ranges(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "sample.jpg").write_bytes(b"abcdef")
            with patch("camera.views.PHOTO_DIR", folder):
                response = self.client.get(
                    reverse(
                        "media_file",
                        kwargs={"kind": "photos", "name": "sample.jpg"},
                    ),
                    HTTP_RANGE="bytes=1-3",
                )

                self.assertEqual(response.status_code, 206)
                self.assertEqual(response["Content-Range"], "bytes 1-3/6")
                self.assertEqual(b"".join(response.streaming_content), b"bcd")
                response.close()

    def test_unknown_media_kind_is_not_found(self):
        response = self.client.get(
            reverse("media_file", kwargs={"kind": "other", "name": "sample.jpg"})
        )

        self.assertEqual(response.status_code, 404)
