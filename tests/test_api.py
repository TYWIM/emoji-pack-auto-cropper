import io
import unittest
import zipfile

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import MAX_UPLOAD_BYTES, app


def make_sheet() -> bytes:
    image = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 180, 180), fill=(235, 80, 60, 255))
    draw.rectangle((220, 20, 380, 180), fill=(50, 120, 210, 255))
    data = io.BytesIO()
    image.save(data, "PNG")
    return data.getvalue()


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def analyze(self, payload: bytes = None, mode: str = "auto"):
        payload = payload or make_sheet()
        return self.client.post(
            "/api/analyze",
            files={"file": ("拼图.png", payload, "image/png")},
            data={"mode": mode, "rows": "2", "columns": "2"},
        )

    def test_analyze_returns_square_boxes_and_session(self):
        response = self.analyze()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["width"], 400)
        self.assertEqual(body["height"], 200)
        self.assertTrue(body["session_id"])
        self.assertEqual(len(body["boxes"]), 2)
        for box in body["boxes"]:
            self.assertEqual(box["size"], box["size"])
            self.assertGreater(box["size"], 0)

    def test_analyze_rejects_non_png(self):
        data = io.BytesIO()
        Image.new("RGB", (10, 10), "white").save(data, "JPEG")
        response = self.analyze(payload=data.getvalue())
        self.assertEqual(response.status_code, 422)
        self.assertIn("仅支持 PNG", response.json()["detail"])

    def test_analyze_rejects_oversized_file(self):
        oversized = b"\x89PNG" + b"\x00" * (MAX_UPLOAD_BYTES + 1024)
        response = self.analyze(payload=oversized)
        self.assertEqual(response.status_code, 422)
        self.assertIn("25 MB", response.json()["detail"])

    def test_analyze_rejects_bad_grid_dimensions(self):
        payload = make_sheet()
        too_many = self.client.post(
            "/api/analyze",
            files={"file": ("拼图.png", payload, "image/png")},
            data={"mode": "grid", "rows": "21", "columns": "2"},
        )
        self.assertEqual(too_many.status_code, 422)
        zero = self.client.post(
            "/api/analyze",
            files={"file": ("拼图.png", payload, "image/png")},
            data={"mode": "grid", "rows": "0", "columns": "2"},
        )
        self.assertEqual(zero.status_code, 422)

    def test_source_and_crop_endpoints(self):
        session_id = self.analyze().json()["session_id"]
        source = self.client.get(f"/api/session/{session_id}/source")
        self.assertEqual(source.status_code, 200)
        self.assertEqual(source.headers["content-type"], "image/png")
        crop = self.client.get(f"/api/session/{session_id}/crop/0")
        self.assertEqual(crop.status_code, 200)
        with Image.open(io.BytesIO(crop.content)) as output:
            self.assertEqual(output.size, (300, 300))
        missing = self.client.get(f"/api/session/{session_id}/crop/99")
        self.assertEqual(missing.status_code, 404)

    def test_export_roundtrip(self):
        session_id = self.analyze().json()["session_id"]
        response = self.client.post(
            "/api/export",
            json={
                "session_id": session_id,
                "folder_name": "冒烟测试",
                "items": [
                    {"crop_index": 0, "name": "开心"},
                    {"crop_index": 1, "name": "疑问"},
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["content-disposition"])
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = set(archive.namelist())
            self.assertEqual(
                names,
                {
                    "冒烟测试/PNG_300x300/开心_01.png",
                    "冒烟测试/PNG_300x300/疑问_02.png",
                    "冒烟测试/GIF_300x300/开心_01.gif",
                    "冒烟测试/GIF_300x300/疑问_02.gif",
                    "冒烟测试/开心_01_200.png",
                },
            )

    def test_export_rejects_invalid_name_and_crop_index(self):
        session_id = self.analyze().json()["session_id"]
        bad_name = self.client.post(
            "/api/export",
            json={"session_id": session_id, "folder_name": "x", "items": [{"crop_index": 0, "name": "hello"}]},
        )
        self.assertEqual(bad_name.status_code, 422)
        bad_index = self.client.post(
            "/api/export",
            json={"session_id": session_id, "folder_name": "x", "items": [{"crop_index": 99, "name": "开心"}]},
        )
        self.assertEqual(bad_index.status_code, 422)

    def test_export_rejects_expired_session(self):
        response = self.client.post(
            "/api/export",
            json={"session_id": "does-not-exist", "folder_name": "x", "items": [{"crop_index": 0, "name": "开心"}]},
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
