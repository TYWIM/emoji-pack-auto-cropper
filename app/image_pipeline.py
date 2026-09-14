from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageOps


CHINESE_NAME = re.compile(r"^[\u4e00-\u9fff]{1,4}$")
INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class CropBox:
    x: int
    y: int
    size: int

    def as_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "size": self.size}


def load_png(data: bytes) -> Image.Image:
    if len(data) > 25 * 1024 * 1024:
        raise ValueError("PNG 文件不能超过 25 MB")
    try:
        with Image.open(io.BytesIO(data)) as opened:
            if opened.format != "PNG":
                raise ValueError("仅支持 PNG 图片")
            if opened.width * opened.height > 40_000_000:
                raise ValueError("图片像素总量不能超过 4000 万")
            return ImageOps.exif_transpose(opened).convert("RGBA")
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("PNG 文件无法读取或已损坏") from exc


def _square_box(x: int, y: int, width: int, height: int, image_width: int, image_height: int) -> CropBox:
    size = min(max(int(round(max(width, height) * 1.18)), 1), min(image_width, image_height))
    center_x = x + width / 2
    center_y = y + height / 2
    left = max(0, min(int(round(center_x - size / 2)), image_width - size))
    top = max(0, min(int(round(center_y - size / 2)), image_height - size))
    return CropBox(left, top, size)


def _foreground_mask(image: Image.Image) -> np.ndarray:
    rgba = np.asarray(image)
    alpha = rgba[:, :, 3]
    if np.count_nonzero(alpha < 245) > alpha.size * 0.005:
        mask = np.where(alpha > 12, 255, 0).astype(np.uint8)
    else:
        rgb = rgba[:, :, :3].astype(np.int16)
        border = np.concatenate((rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]), axis=0)
        background = np.median(border, axis=0)
        difference = np.max(np.abs(rgb - background), axis=2).astype(np.uint8)
        otsu, _ = cv2.threshold(difference, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        threshold = max(10, min(int(otsu), 55))
        mask = np.where(difference > threshold, 255, 0).astype(np.uint8)

    height, width = mask.shape
    close_size = max(3, int(round(min(width, height) * 0.012)))
    if close_size % 2 == 0:
        close_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (close_size, close_size))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.dilate(mask, kernel, iterations=1)
    return mask


def detect_crops(image: Image.Image) -> list[CropBox]:
    mask = _foreground_mask(image)
    image_width, image_height = image.size
    image_area = image_width * image_height
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    components: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width * height < image_area * 0.00015:
            continue
        if width < image_width * 0.008 or height < image_height * 0.008:
            continue
        components.append((x, y, width, height))

    if not components:
        return [CropBox(0, 0, min(image_width, image_height))]

    largest_component = max(components, key=lambda component: component[2] * component[3])
    largest_area = largest_component[2] * largest_component[3]
    primary_threshold = max(image_area * 0.003, largest_area * 0.42)
    minimum_width = largest_component[2] * 0.45
    minimum_height = largest_component[3] * 0.45
    primary = [
        component
        for component in components
        if component[2] * component[3] >= primary_threshold
        and component[2] >= minimum_width
        and component[3] >= minimum_height
    ]
    if not primary:
        primary = [max(components, key=lambda component: component[2] * component[3])]

    groups = _attach_nearby_components(primary, components)
    boxes = [
        _square_box(x, y, width, height, image_width, image_height)
        for x, y, width, height in groups
    ]

    boxes = _soft_limit_overlap(boxes, groups, image_width, image_height)
    boxes = _remove_near_duplicates(boxes)
    return _sort_row_major(boxes)


def _soft_limit_overlap(
    boxes: list[CropBox],
    groups: list[tuple[int, int, int, int]],
    image_width: int,
    image_height: int,
) -> list[CropBox]:
    if len(boxes) < 2:
        return boxes
    centers = [(x + width / 2, y + height / 2) for x, y, width, height in groups]
    limited: list[CropBox] = []
    for index, box in enumerate(boxes):
        center_x, center_y = centers[index]
        x, y, width, height = groups[index]
        allowed_left, allowed_top = 0, 0
        allowed_right, allowed_bottom = image_width, image_height
        for other_index, (other_center_x, other_center_y) in enumerate(centers):
            if other_index == index:
                continue
            other_x, other_y, other_width, other_height = groups[other_index]
            rows_overlap = min(y + height, other_y + other_height) > max(y, other_y)
            columns_overlap = min(x + width, other_x + other_width) > max(x, other_x)
            if rows_overlap:
                if other_center_x < center_x:
                    allowed_left = max(allowed_left, other_x + other_width)
                else:
                    allowed_right = min(allowed_right, other_x)
            if columns_overlap:
                if other_center_y < center_y:
                    allowed_top = max(allowed_top, other_y + other_height)
                else:
                    allowed_bottom = min(allowed_bottom, other_y)
        content_size = max(width, height)
        available_size = min(allowed_right - allowed_left, allowed_bottom - allowed_top)
        size = max(content_size, min(box.size, max(content_size, available_size)))
        left = int(round(max(allowed_left, min(center_x - size / 2, allowed_right - size))))
        top = int(round(max(allowed_top, min(center_y - size / 2, allowed_bottom - size))))
        left = max(0, min(left, image_width - size))
        top = max(0, min(top, image_height - size))
        limited.append(CropBox(left, top, size))
    return limited


def _sort_row_major(boxes: list[CropBox]) -> list[CropBox]:
    if len(boxes) < 2:
        return boxes
    typical_size = float(np.median([box.size for box in boxes]))
    rows: list[list[CropBox]] = []
    for box in sorted(boxes, key=lambda item: item.y + item.size / 2):
        center_y = box.y + box.size / 2
        matching_row = next(
            (
                row
                for row in rows
                if abs(center_y - np.mean([item.y + item.size / 2 for item in row])) <= typical_size * 0.55
            ),
            None,
        )
        if matching_row is None:
            rows.append([box])
        else:
            matching_row.append(box)
    rows.sort(key=lambda row: np.mean([item.y + item.size / 2 for item in row]))
    return [box for row in rows for box in sorted(row, key=lambda item: item.x)]


def _attach_nearby_components(
    primary: list[tuple[int, int, int, int]],
    components: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    groups = [list(component) for component in primary]
    primary_set = set(primary)
    for component in components:
        if component in primary_set:
            continue
        x, y, width, height = component
        center_x, center_y = x + width / 2, y + height / 2
        nearest_index = -1
        nearest_distance = float("inf")
        for index, (px, py, pwidth, pheight) in enumerate(primary):
            gap_x = max(px - (x + width), x - (px + pwidth), 0)
            gap_y = max(py - (y + height), y - (py + pheight), 0)
            distance = (gap_x**2 + gap_y**2) ** 0.5
            primary_center_x, primary_center_y = px + pwidth / 2, py + pheight / 2
            center_distance = ((center_x - primary_center_x) ** 2 + (center_y - primary_center_y) ** 2) ** 0.5
            if distance < nearest_distance and center_distance <= max(pwidth, pheight) * 1.2:
                nearest_index = index
                nearest_distance = distance
        if nearest_index < 0:
            continue
        px, py, pwidth, pheight = primary[nearest_index]
        if nearest_distance > max(pwidth, pheight) * 0.45:
            continue
        group = groups[nearest_index]
        right = max(group[0] + group[2], x + width)
        bottom = max(group[1] + group[3], y + height)
        group[0] = min(group[0], x)
        group[1] = min(group[1], y)
        group[2] = right - group[0]
        group[3] = bottom - group[1]
    return [tuple(group) for group in groups]


def _remove_near_duplicates(boxes: Iterable[CropBox]) -> list[CropBox]:
    kept: list[CropBox] = []
    for candidate in sorted(boxes, key=lambda box: box.size, reverse=True):
        candidate_center = (candidate.x + candidate.size / 2, candidate.y + candidate.size / 2)
        duplicate = False
        for current in kept:
            current_center = (current.x + current.size / 2, current.y + current.size / 2)
            distance = ((candidate_center[0] - current_center[0]) ** 2 + (candidate_center[1] - current_center[1]) ** 2) ** 0.5
            if distance < min(candidate.size, current.size) * 0.25:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept


def grid_crops(image: Image.Image, rows: int, columns: int) -> list[CropBox]:
    if not 1 <= rows <= 20 or not 1 <= columns <= 20:
        raise ValueError("行数和列数必须在 1 到 20 之间")
    width, height = image.size
    boxes: list[CropBox] = []
    for row in range(rows):
        top = round(row * height / rows)
        bottom = round((row + 1) * height / rows)
        for column in range(columns):
            left = round(column * width / columns)
            right = round((column + 1) * width / columns)
            boxes.append(_square_box(left, top, right - left, bottom - top, width, height))
    return boxes


def crop_and_resize(image: Image.Image, box: CropBox, size: int) -> Image.Image:
    cropped = image.crop((box.x, box.y, box.x + box.size, box.y + box.size))
    return cropped.resize((size, size), Image.Resampling.LANCZOS)


def _gif_friendly(image: Image.Image) -> Image.Image:
    """GIF 输出预处理：把半透明像素的 RGB 按 alpha 预乘。

    Pillow 保存 GIF 时会把 alpha >= 128 的半透明像素按原始 RGB 硬切为不透明，
    抗锯齿边缘因此变成白色/亮色硬边；预乘后边缘变为平滑渐变，消除白边。
    """
    rgba = image.convert("RGBA")
    if rgba.getchannel("A").getextrema()[0] >= 255:
        return rgba
    array = np.asarray(rgba).astype(np.int16)
    array[:, :, :3] = array[:, :, :3] * array[:, :, 3:4] // 255
    return Image.fromarray(array.astype(np.uint8))


def safe_folder_name(value: str, fallback: str = "表情包") -> str:
    cleaned = INVALID_PATH_CHARS.sub("_", value).strip(" .")
    return cleaned[:60] or fallback


def build_export(
    image: Image.Image,
    boxes: list[CropBox],
    selections: list[tuple[int, str] | tuple[int, str, dict[str, int] | None]],
    folder_name: str,
) -> io.BytesIO:
    if not selections:
        raise ValueError("至少保留一张表情图片")
    root = safe_folder_name(folder_name)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        first_image: tuple[str, Image.Image] | None = None
        for output_index, selection in enumerate(selections, start=1):
            crop_index, name = selection[0], selection[1]
            if not CHINESE_NAME.fullmatch(name):
                raise ValueError(f"第 {output_index} 张的名称应为 1 到 4 个汉字")
            has_custom_box = len(selection) == 3 and selection[2] is not None
            if not has_custom_box and not 0 <= crop_index < len(boxes):
                raise ValueError("裁剪序号无效，请重新识别")
            selected_box = boxes[crop_index] if 0 <= crop_index < len(boxes) else CropBox(0, 0, 1)
            if has_custom_box:
                raw_box = selection[2]
                try:
                    selected_box = CropBox(int(raw_box["x"]), int(raw_box["y"]), int(raw_box["size"]))
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("裁剪框参数无效") from exc
                if selected_box.size <= 0 or selected_box.x < 0 or selected_box.y < 0:
                    raise ValueError("裁剪框参数无效")
                if selected_box.x + selected_box.size > image.width or selected_box.y + selected_box.size > image.height:
                    raise ValueError("裁剪框不能超出原图范围")
            base_name = f"{name}_{output_index:02d}"
            resized = crop_and_resize(image, selected_box, 300)

            png_data = io.BytesIO()
            resized.save(png_data, "PNG", optimize=True)
            archive.writestr(f"{root}/PNG_300x300/{base_name}.png", png_data.getvalue())

            gif_data = io.BytesIO()
            _gif_friendly(resized).save(gif_data, "GIF", save_all=False, optimize=True, disposal=2)
            archive.writestr(f"{root}/GIF_300x300/{base_name}.gif", gif_data.getvalue())
            if first_image is None:
                first_image = (base_name, resized)

        assert first_image is not None
        preview_data = io.BytesIO()
        first_image[1].resize((200, 200), Image.Resampling.LANCZOS).save(preview_data, "PNG", optimize=True)
        archive.writestr(f"{root}/{first_image[0]}_200.png", preview_data.getvalue())
    output.seek(0)
    return output


def image_bytes(image: Image.Image, image_format: str = "PNG") -> bytes:
    data = io.BytesIO()
    image.save(data, image_format, optimize=True)
    return data.getvalue()
