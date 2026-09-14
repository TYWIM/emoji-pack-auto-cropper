import io
import unittest
import zipfile

from PIL import Image

from app.image_pipeline import build_export, detect_crops, grid_crops, load_png


class ImagePipelineTests(unittest.TestCase):
    def make_sheet(self) -> Image.Image:
        image = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
        for left, top, color in [
            (40, 40, (235, 80, 60, 255)),
            (340, 40, (50, 120, 210, 255)),
            (40, 340, (45, 160, 100, 255)),
            (340, 340, (230, 185, 40, 255)),
        ]:
            patch = Image.new("RGBA", (180, 180), color)
            image.alpha_composite(patch, (left, top))
        return image

    def test_detects_four_transparent_regions_as_square_crops(self):
        boxes = detect_crops(self.make_sheet())
        self.assertEqual(len(boxes), 4)
        self.assertTrue(all(box.size > 0 for box in boxes))
        self.assertTrue(all(0 <= box.x <= 600 - box.size for box in boxes))
        self.assertTrue(all(0 <= box.y <= 600 - box.size for box in boxes))

    def test_small_decorations_are_attached_instead_of_exported(self):
        image = self.make_sheet()
        decoration = Image.new("RGBA", (24, 24), (255, 210, 60, 255))
        for left, top in [(226, 55), (526, 55), (226, 355), (526, 355)]:
            image.alpha_composite(decoration, (left, top))
        boxes = detect_crops(image)
        self.assertEqual(len(boxes), 4)

    def test_large_standalone_symbols_are_not_detected_as_emojis(self):
        image = self.make_sheet()
        symbol = Image.new("RGBA", (70, 70), (255, 210, 60, 255))
        image.alpha_composite(symbol, (250, 250))
        boxes = detect_crops(image)
        self.assertEqual(len(boxes), 4)

    def test_neighboring_crop_boxes_may_overlap_to_keep_subjects_complete(self):
        image = Image.new("RGBA", (500, 300), (0, 0, 0, 0))
        image.alpha_composite(Image.new("RGBA", (150, 240), (80, 130, 220, 255)), (50, 30))
        image.alpha_composite(Image.new("RGBA", (150, 240), (220, 90, 80, 255)), (300, 30))
        boxes = detect_crops(image)
        self.assertEqual(len(boxes), 2)
        self.assertGreater(boxes[0].x + boxes[0].size, boxes[1].x)
        self.assertLessEqual(boxes[0].x + boxes[0].size, 300)
        self.assertGreaterEqual(boxes[1].x, 200)

    def test_primary_subject_near_cell_edge_keeps_its_full_extent(self):
        image = Image.new("RGBA", (900, 300), (0, 0, 0, 0))
        for left in (0, 300, 600):
            # Deliberately fill nearly the entire 300px cell.
            image.alpha_composite(Image.new("RGBA", (292, 292), (80, 130, 220, 255)), (left + 4, 4))
        boxes = detect_crops(image)
        self.assertEqual(len(boxes), 3)
        self.assertTrue(all(box.size >= 292 for box in boxes))

    def test_source_crop_size_follows_subject_not_output_size(self):
        image = Image.new("RGBA", (900, 300), (0, 0, 0, 0))
        for left in (90, 390, 690):
            image.alpha_composite(Image.new("RGBA", (120, 120), (80, 130, 220, 255)), (left, 90))
        boxes = detect_crops(image)
        self.assertEqual(len(boxes), 3)
        self.assertTrue(all(120 < box.size < 200 for box in boxes))

    def test_grid_count_and_order(self):
        boxes = grid_crops(self.make_sheet(), 2, 3)
        self.assertEqual(len(boxes), 6)
        self.assertLess(boxes[0].x, boxes[1].x)
        self.assertLess(boxes[0].y, boxes[3].y)

    def test_export_contract_and_dimensions(self):
        image = self.make_sheet()
        boxes = grid_crops(image, 2, 2)
        archive_data = build_export(image, boxes, [(0, "开心"), (2, "疑问")], "测试表情包")
        with zipfile.ZipFile(archive_data) as archive:
            names = set(archive.namelist())
            self.assertEqual(names, {
                "测试表情包/PNG_300x300/开心_01.png",
                "测试表情包/PNG_300x300/疑问_02.png",
                "测试表情包/GIF_300x300/开心_01.gif",
                "测试表情包/GIF_300x300/疑问_02.gif",
                "测试表情包/开心_01_200.png",
            })
            for name in names:
                with Image.open(io.BytesIO(archive.read(name))) as output:
                    expected = (200, 200) if name.endswith("_200.png") else (300, 300)
                    self.assertEqual(output.size, expected)

    def test_export_accepts_a_manually_adjusted_box(self):
        image = self.make_sheet()
        boxes = grid_crops(image, 2, 2)
        archive_data = build_export(image, boxes, [(0, "开心", {"x": 20, "y": 20, "size": 200})], "手动裁剪")
        with zipfile.ZipFile(archive_data) as archive:
            with Image.open(io.BytesIO(archive.read("手动裁剪/PNG_300x300/开心_01.png"))) as output:
                self.assertEqual(output.size, (300, 300))

    def test_rejects_non_chinese_names(self):
        with self.assertRaisesRegex(ValueError, "1 到 4 个汉字"):
            build_export(self.make_sheet(), grid_crops(self.make_sheet(), 1, 1), [(0, "happy")], "测试")

    def test_load_png_rejects_jpeg(self):
        data = io.BytesIO()
        Image.new("RGB", (10, 10), "white").save(data, "JPEG")
        with self.assertRaisesRegex(ValueError, "仅支持 PNG"):
            load_png(data.getvalue())


if __name__ == "__main__":
    unittest.main()
