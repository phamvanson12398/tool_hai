# -*- coding: utf-8 -*-
"""Xuất dự án CapCut từ timeline đã dựng.

Bước B: tạo dự án thử chỉ có 1 track hình + 1 clip giọng.
Đọc dự án mẫu 1021 làm template, copy cấu trúc cần thiết.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# UUID placeholder cố định CapCut dùng cho local files
CAPCUT_PLACEHOLDER_UUID = "0E685133-18CE-45ED-8CB8-2904A212EC80"

# Khung mặc định khi dự án mẫu thiếu loại vật liệu / đoạn tương ứng
DEFAULT_SEGMENT = {
    "id": "", "material_id": "", "source_timerange": None, "target_timerange": None,
    "speed": 1.0, "volume": 1.0, "last_nonzero_volume": 1.0, "visible": True,
    "reverse": False, "cartoon": False, "is_placeholder": False, "is_tone_modify": False,
    "intensifies_audio": False, "enable_adjust": True, "enable_color_curves": True,
    "enable_color_wheels": True, "enable_lut": True, "render_index": 0,
    "track_render_index": 0, "track_attribute": 0, "extra_material_refs": [],
    "keyframe_refs": [], "common_keyframes": [],
    "uniform_scale": {"on": True, "value": 1.0},
    "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000},
    "clip": {"alpha": 1.0, "flip": {"horizontal": False, "vertical": False},
             "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0},
             "transform": {"x": 0.0, "y": 0.0}},
}
DEFAULT_MATERIALS = {
    "videos": {
        "id": "", "type": "video", "path": "", "material_name": "", "duration": 0,
        "width": 1080, "height": 1920, "has_audio": False, "category_name": "local",
        "crop": {"lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0,
                 "lower_right_y": 1.0, "upper_left_x": 0.0, "upper_left_y": 0.0,
                 "upper_right_x": 1.0, "upper_right_y": 0.0},
        "crop_ratio": "free", "crop_scale": 1.0, "extra_type_option": 0,
        "local_material_id": "", "source": 0, "source_platform": 0,
    },
    "audios": {
        "id": "", "type": "extract_music", "path": "", "name": "", "duration": 0,
        "category_name": "local", "app_id": 0, "local_material_id": "",
        "check_flag": 1, "source_platform": 0, "wave_points": [],
    },
    "texts": {
        "id": "", "type": "text", "content": "", "font_path": "", "font_size": 11.0,
        "text_color": "#FFFFFF", "alignment": 1, "line_spacing": 0.02, "typesetting": 0,
        "check_flag": 7, "text_alpha": 1.0, "global_alpha": 1.0,
        "fixed_width": -1.0, "fixed_height": -1.0,
    },
}


def _uuid() -> str:
    """UUID viết hoa theo chuẩn CapCut."""
    return str(uuid.uuid4()).upper()


def _microseconds(sec: float) -> int:
    """Chuyển giây sang microseconds (đơn vị thời gian CapCut)."""
    return int(sec * 1_000_000)


def _now_microseconds() -> int:
    """Timestamp hiện tại dạng microseconds."""
    return int(datetime.now().timestamp() * 1_000_000)


def _default_template_draft(capcut_root: Path) -> Path | None:
    """Tìm dự án mẫu từ cài đặt; chưa chọn thì thử MAU_XUAT, rồi 1021."""
    try:
        from . import config as _config

        name = str(_config.load_settings().get("capcut_template_draft") or "").strip()
    except Exception:
        name = ""
    for cand in (name, "MAU_XUAT", "1021"):
        if cand and (capcut_root / cand / "draft_content.json").exists():
            return capcut_root / cand
    return None


def list_draft_names(capcut_root: Path) -> list[str]:
    """Danh sách tên các dự án CapCut đang có, sắp xếp theo tên."""
    root = Path(capcut_root)
    if not root.is_dir():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir()
        and not p.name.startswith(".")
        and (p / "draft_content.json").exists()
    )


def _project_title(project_dir: Path) -> str:
    """Lấy tiêu đề tập từ project.json / timeline.json, cho tên dự án CapCut."""
    for cand in (project_dir / "project.json", project_dir / "out" / "timeline.json"):
        if not cand.exists():
            continue
        try:
            d = json.loads(cand.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict):
            t = d.get("title") or d.get("tieu_de") or d.get("name")
            if t:
                return str(t)
    return ""


def _srt_timestamp_to_seconds(ts: str) -> float:
    """'00:00:01,719' -> 1.719 giây."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) != 3:
        return 0.0
    try:
        h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError:
        return 0.0
    return h * 3600 + m * 60 + s


def _parse_srt(text: str) -> list[tuple[str, float, float]]:
    """Đọc file .srt, trả về [(nội dung, start_giây, duration_giây)]."""
    out: list[tuple[str, float, float]] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        # Bỏ dòng số thứ tự nếu có
        if lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines:
            continue
        time_line = lines[0]
        if "-->" not in time_line:
            continue
        start_s, end_s = [p.strip() for p in time_line.split("-->", 1)]
        start = _srt_timestamp_to_seconds(start_s)
        end = _srt_timestamp_to_seconds(end_s)
        content = " ".join(l.strip() for l in lines[1:]).strip()
        if not content:
            continue
        out.append((content, start, max(0.0, end - start)))
    return out


# Lỗi CapCut mã hoá file dự án — dừng ngay, hiện đúng câu báo trong đặc tả
MSG_ENCRYPTED = (
    "Phiên bản CapCut này mã hoá file dự án nên chưa xuất được. "
    "Chị dùng file mp4 và bộ file rời trong thư mục tập nhé."
)


class CapCutEncryptedError(RuntimeError):
    """draft_content.json của dự án mẫu không đọc được dạng JSON."""


def check_template_readable(template_draft: Path) -> dict:
    """Đọc draft_content.json của dự án mẫu, ném CapCutEncryptedError nếu bị mã hoá.

    Trả về dict nội dung nếu đọc được.
    """
    path = Path(template_draft)
    timeline_dir = path / "Timelines"
    candidates = []
    if timeline_dir.is_dir():
        for sub in timeline_dir.glob("*/draft_content.json"):
            candidates.append(sub)
    candidates.append(path / "draft_content.json")

    content_path = next((c for c in candidates if c.exists()), None)
    if content_path is None:
        raise FileNotFoundError(
            f"Không tìm thấy draft_content.json trong dự án mẫu: {template_draft}"
        )

    try:
        text = content_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise CapCutEncryptedError(MSG_ENCRYPTED) from None
    except OSError as e:
        raise RuntimeError(f"Không đọc được file dự án mẫu: {e}") from e

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise CapCutEncryptedError(MSG_ENCRYPTED) from None

    if not isinstance(data, dict) or "tracks" not in data:
        raise CapCutEncryptedError(MSG_ENCRYPTED)
    return data


class CapCutExporter:
    """Xuất dự án CapCut từ timeline.json của tool."""

    def __init__(self, capcut_root: Path, template_draft: Path | None = None):
        """
        Args:
            capcut_root: thư mục %LOCALAPPDATA%\\CapCut\\User Data\\Projects\\com.lveditor.draft
            template_draft: thư mục dự án mẫu dùng để học cấu trúc;
                None = tự tìm từ cài đặt.
        """
        self.capcut_root = Path(capcut_root)
        if not self.capcut_root.exists():
            raise FileNotFoundError(
                f"Không tìm thấy thư mục dự án CapCut: {capcut_root}. "
                "Chị kiểm tra lại đường dẫn trong trang Cài đặt nhé."
            )
        self.template_draft = Path(template_draft) if template_draft else None
        if self.template_draft is None:
            self.template_draft = _default_template_draft(self.capcut_root)
        if self.template_draft is None or not self.template_draft.exists():
            raise FileNotFoundError(
                "Chưa chọn dự án CapCut mẫu. Vào trang Cài đặt, mục "
                "“Chọn dự án CapCut mẫu” rồi bấm Lưu nhé."
            )
        # Dừng sớm nếu dự án mẫu bị mã hoá (không ghi gì cả)
        check_template_readable(self.template_draft)

    @staticmethod
    def default_draft_name(title: str = "") -> str:
        """Tên dự án mới: <ngày>_<tiêu đề> — có số thứ tự nếu trùng."""
        safe = ""
        if title:
            safe = re.sub(r'[<>:"/\\|?*]+', "", title).strip()
            safe = re.sub(r"\s+", "_", safe)
        return datetime.now().strftime("%Y%m%d_%H%M%S") + (f"_{safe}" if safe else "")

    def export_project(
        self,
        project_dir: Path,
        draft_name: str = "",
        video_path: Path | None = None,
        audio_paths: list[Path] | None = None,
    ) -> Path:
        """Xuất dự án CapCut mới từ thư mục tập (projects/<id>/).

        Args:
            project_dir: thư mục tập (projects/e2e_test)
            draft_name: tên dự án mới; để trống = tự đặt <ngày>_<tiêu đề>
            video_path: đường dẫn video không tiếng (None = tách từ video.mp4)
            audio_paths: danh sách file giọng (None = lấy từ audio/)

        Returns:
            đường dẫn thư mục dự án CapCut mới
        """
        # Đọc timeline
        tl_path = project_dir / "out" / "timeline.json"
        if not tl_path.exists():
            raise FileNotFoundError(
                "Tập này chưa dựng xong nên chưa xuất CapCut được. "
                "Chị bấm “Xác nhận và dựng video” trước nhé."
            )

        with open(tl_path, encoding="utf-8") as f:
            timeline = json.load(f)

        # Tên dự án: tự đặt nếu trống, thêm hậu tố nếu trùng
        if not draft_name.strip():
            draft_name = self.default_draft_name(_project_title(project_dir))
        name = draft_name
        n = 1
        while (self.capcut_root / name).exists():
            n += 1
            name = f"{draft_name}_{n}"
        draft_name = name

        # Tạo thư mục dự án mới
        draft_folder = self.capcut_root / draft_name
        if draft_folder.exists():
            raise FileExistsError(f"Dự án đã tồn tại: {draft_folder}")

        draft_folder.mkdir(parents=True, exist_ok=True)
        try:
            return self._export_into(
                draft_folder, draft_name, project_dir, timeline,
                video_path, audio_paths,
            )
        except Exception:
            # Dọn thư mục dở dang để không để lại dự án hỏng
            shutil.rmtree(draft_folder, ignore_errors=True)
            log.exception(f"Xuất dự án CapCut thất bại, đã xoá {draft_folder}")
            raise

    def _export_into(
        self,
        draft_folder: Path,
        draft_name: str,
        project_dir: Path,
        timeline: dict,
        video_path: Path | None,
        audio_paths: list[Path] | None,
    ) -> Path:
        """Thân hàm xuất, chạy sau khi thư mục dự án đã được tạo."""
        (draft_folder / "Resources").mkdir(exist_ok=True)
        timelines_dir = draft_folder / "Timelines"
        timelines_dir.mkdir(exist_ok=True)

        # Tạo video không tiếng
        if video_path and video_path.exists():
            video_dst = draft_folder / "video_khong_tieng.mp4"
            shutil.copy2(video_path, video_dst)
        else:
            # Tách audio từ video.mp4 thành video_khong_tieng.mp4
            video_src = project_dir / "out" / "video.mp4"
            if not video_src.exists():
                raise FileNotFoundError(f"Không có video: {video_src}")
            video_dst = draft_folder / "video_khong_tieng.mp4"
            self._strip_audio(video_src, video_dst)

        # Lấy danh sách giọng
        if audio_paths is None:
            audio_dir = project_dir / "audio"
            audio_paths = sorted(audio_dir.glob("*.wav"))

        if not audio_paths:
            raise FileNotFoundError(f"Không có file giọng trong {project_dir / 'audio'}")

        # Chép toàn bộ file giọng + SFX vào thư mục media/ của dự án
        media_dir = draft_folder / "media"
        media_dir.mkdir(exist_ok=True)

        # Copy giọng từ audio/
        copied_audio = []
        for audio_src in audio_paths:
            audio_dst = media_dir / audio_src.name
            shutil.copy2(audio_src, audio_dst)
            copied_audio.append(audio_dst)

        # Copy SFX từ data/sfx/ (nếu timeline có dùng)
        sfx_used = set()
        for ln in timeline.get("lines", []):
            if ln.get("sfx"):
                sfx_used.add(ln["sfx"])
        for bt in timeline.get("beats", []):
            if bt.get("sfx"):
                sfx_used.add(bt["sfx"])

        sfx_files = {}
        if sfx_used:
            sfx_dir = project_dir.parent.parent / "data" / "sfx"
            for sfx_name in sfx_used:
                src = sfx_dir / sfx_name
                if src.exists():
                    dst = media_dir / sfx_name
                    shutil.copy2(src, dst)
                    sfx_files[sfx_name] = dst

        # Tạo draft_content.json trong Timelines/<timeline_id>/
        draft_id = _uuid()
        timeline_id = _uuid()
        timeline_folder = timelines_dir / timeline_id
        timeline_folder.mkdir(parents=True, exist_ok=True)
        (timeline_folder / "common_attachment").mkdir(exist_ok=True)

        content = self._build_draft_content(
            draft_id=timeline_id,  # id trong draft_content = timeline_id
            draft_name=draft_name,
            video_path=video_dst,
            audio_files=copied_audio,
            sfx_files=sfx_files,
            timeline=timeline,
            project_dir=project_dir,
        )

        content_path = timeline_folder / "draft_content.json"
        with open(content_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)

        # Tạo Timelines/project.json
        now = _now_microseconds()
        project_json = {
            "id": _uuid(),
            "main_timeline_id": timeline_id,
            "version": 0,
            "create_time": now,
            "update_time": now,
            "config": {
                "color_space": -1,
                "hdr_vivid": False,
                "mixed_track_mode_on": False,
                "render_index_track_mode_on": False,
                "use_float_render": False,
            },
            "timelines": [
                {
                    "id": timeline_id,
                    "name": "Dòng thời gian 01",
                    "create_time": now,
                    "update_time": now,
                    "is_marked_delete": False,
                }
            ],
        }
        with open(timelines_dir / "project.json", "w", encoding="utf-8") as f:
            json.dump(project_json, f, ensure_ascii=False)

        # Tạo draft_content.json ở root (legacy copy)
        with open(draft_folder / "draft_content.json", "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)

        # Tạo draft_meta_info.json
        meta = self._build_draft_meta(
            draft_id=draft_id,
            draft_name=draft_name,
            draft_folder=draft_folder,
            duration=_microseconds(timeline.get("total", 10.0)),
        )

        meta_path = draft_folder / "draft_meta_info.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)

        # Tạo các file config tối thiểu
        self._write_minimal_configs(draft_folder)
        self._write_timeline_configs(timeline_folder)

        # Đăng ký dự án vào root_meta_info.json để CapCut nhìn thấy
        self._register_in_root_meta(
            draft_folder, draft_name, draft_id, _microseconds(timeline.get("total", 10.0))
        )

        log.info(f"Đã xuất dự án CapCut: {draft_folder}")
        return draft_folder

    def _register_in_root_meta(
        self, draft_folder: Path, draft_name: str, draft_id: str, duration: int
    ) -> None:
        """Thêm dự án mới vào root_meta_info.json (chỉ thêm, không xóa dự án cũ)."""
        root_meta = self.capcut_root / "root_meta_info.json"
        if not root_meta.exists():
            log.warning("Không tìm thấy root_meta_info.json, bỏ qua đăng ký dự án.")
            return

        with open(root_meta, encoding="utf-8") as f:
            data = json.load(f)

        store = data.get("all_draft_store")
        if not isinstance(store, list):
            log.warning("root_meta_info.json không có all_draft_store, bỏ qua.")
            return

        # Bỏ qua nếu đã có tên trùng
        for entry in store:
            if entry.get("draft_name") == draft_name:
                log.warning(f"Dự án '{draft_name}' đã có trong root_meta_info.json.")
                return

        now = _now_microseconds()
        folder_str = str(draft_folder)
        store.append(
            {
                "cloud_draft_cover": False,
                "cloud_draft_sync": False,
                "draft_cloud_last_action_download": False,
                "draft_cloud_purchase_info": "",
                "draft_cloud_template_id": "",
                "draft_cloud_tutorial_info": "",
                "draft_cloud_videocut_purchase_info": "",
                "draft_cover": f"{folder_str}/draft_cover.jpg",
                "draft_fold_path": folder_str.replace("\\", "/"),
                "draft_id": draft_id,
                "draft_is_ai_shorts": False,
                "draft_is_cloud_temp_draft": False,
                "draft_is_infinite_canvas_draft": False,
                "draft_is_invisible": False,
                "draft_is_pippit_draft": False,
                "draft_is_web_article_video": False,
                "draft_json_file": f"{folder_str}/draft_content.json",
                "draft_name": draft_name,
                "draft_new_version": "",
                "draft_root_path": str(self.capcut_root),
                "draft_timeline_materials_size": 0,
                "draft_type": "",
                "draft_web_article_video_enter_from": "",
                "pippit_avatar_url": "",
                "pippit_extra_info": "",
                "pippit_id": "",
                "pippit_user_name": "",
                "streaming_edit_draft_ready": True,
                "tm_draft_cloud_completed": "",
                "tm_draft_cloud_entry_id": -1,
                "tm_draft_cloud_modified": 0,
                "tm_draft_cloud_parent_entry_id": -1,
                "tm_draft_cloud_space_id": -1,
                "tm_draft_cloud_user_id": -1,
                "tm_draft_create": now,
                "tm_draft_modified": now,
                "tm_draft_removed": 0,
                "tm_duration": duration,
            }
        )

        data["draft_ids"] = len(store)

        # Ghi file tạm rồi thay thế, để không hỏng file index nếu lỗi giữa chừng
        tmp = root_meta.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp.replace(root_meta)
        log.info(f"Đã đăng ký dự án '{draft_name}' vào root_meta_info.json")

    def _write_timeline_configs(self, timeline_folder: Path) -> None:
        """Tạo các file config bên trong thư mục timeline."""
        att = timeline_folder / "common_attachment"
        (att / "attachment_action_scene.json").write_text("{}", encoding="utf-8")
        (att / "attachment_gen_ai_info.json").write_text("{}", encoding="utf-8")
        (att / "attachment_id_mapping.json").write_text("{}", encoding="utf-8")
        (att / "attachment_pc_timeline.json").write_text("{}", encoding="utf-8")
        (att / "attachment_plugin_draft.json").write_text("{}", encoding="utf-8")
        (att / "attachment_script_video.json").write_text("{}", encoding="utf-8")
        (timeline_folder / "attachment_pc_common.json").write_text(
            json.dumps(
                {
                    "ai_packaging_infos": [],
                    "ai_packaging_report_info": {},
                    "broll": {"ai_packaging_infos": [], "ai_packaging_report_info": {}},
                    "commercial_music_category_ids": [],
                    "pc_feature_flag": 0,
                    "recognize_tasks": [],
                    "reference_lines_config": {
                        "horizontal_lines": [],
                        "is_lock": False,
                        "is_visible": False,
                        "vertical_lines": [],
                    },
                    "safe_area_type": 0,
                    "template_item_infos": [],
                    "unlock_template_ids": [],
                }
            ),
            encoding="utf-8",
        )

    def _strip_audio(self, src: Path, dst: Path) -> None:
        """Tách audio khỏi video, tạo video không tiếng."""
        import subprocess

        try:
            from . import video as _video_mod

            ffmpeg = _video_mod._ffmpeg_path()
        except Exception:
            ffmpeg = "ffmpeg"

        cmd = [ffmpeg, "-y", "-i", str(src), "-c:v", "copy", "-an", str(dst)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            tail = [l for l in (proc.stderr or "").splitlines() if l.strip()][-6:]
            raise RuntimeError("ffmpeg lỗi khi tách audio:\n" + "\n".join(tail))
        log.info(f"Đã tạo video không tiếng: {dst}")

    def _build_extra_refs_for_video(self, template: dict,
                                    size: tuple[int, int] = (1080, 1920)) -> list[dict]:
        """Tạo các extra material chuẩn cho một segment (speed, placeholder, mapping...)."""
        total = _microseconds(10.0)
        speed = {"id": _uuid(), "type": "speed", "speed": 1.0, "mode": 0}
        placeholder = {"id": _uuid(), "type": "placeholder_info", "text": ""}
        mapping = {"id": _uuid(), "type": "", "audio_channel_mapping": 0}
        vocal = {"id": _uuid(), "type": "vocal_separation", "choice": 0}
        canvas = {
            "id": _uuid(),
            "type": "canvas_color",
            "material_type": "",
            "height": size[1],
            "width": size[0],
            "duration": total,
            "path": "",
        }
        color = {"id": _uuid(), "type": None, "value": "#FFFFFF"}
        return [speed, placeholder, mapping, vocal, canvas, color]

    def _build_audio_extras(self) -> dict:
        """Tạo extra materials cho một segment audio."""
        return {
            "speeds": [{"id": _uuid(), "type": "speed", "speed": 1.0, "mode": 0}],
            "placeholders": [{"id": _uuid(), "type": "placeholder_info", "text": ""}],
            "sound_mappings": [{"id": _uuid(), "type": "", "audio_channel_mapping": 0}],
            "vocal_seps": [{"id": _uuid(), "type": "vocal_separation", "choice": 0}],
            "beats": [{"id": _uuid(), "type": "beats", "gear": 404, "enable_gear": False}],
        }

    def _build_audio_tracks(
        self,
        timeline: dict,
        audio_files: list[Path],
        seg_template: dict,
        template: dict,
    ) -> tuple[list[dict], list[dict], dict]:
        """Tạo track giọng, mỗi nhân vật một track riêng.

        Audio file được đặt tên theo thứ tự câu (line_XXX.wav trong audio/),
        khớp với idx trong timeline.json.
        """
        lines = timeline.get("lines", [])
        if not lines:
            return [], [], {"speeds": [], "placeholders": [], "sound_mappings": [],
                           "vocal_seps": [], "beats": []}

        # File giọng được đặt tên line_<idx:03d>.wav theo idx trong timeline
        by_idx: dict[int, Path] = {}
        for p in audio_files:
            stem = p.stem
            if stem.startswith("line_"):
                try:
                    by_idx[int(stem[5:])] = p
                except ValueError:
                    continue

        # Gom theo nhân vật, giữ thứ tự thời gian
        by_speaker: dict[str, list[dict]] = {}
        for ln in lines:
            speaker = ln.get("speaker") or "voice"
            by_speaker.setdefault(speaker, []).append(ln)

        tracks: list[dict] = []
        mats: list[dict] = []
        speeds, placeholders, mappings, vocals, beats = [], [], [], [], []

        for speaker, speaker_lines in by_speaker.items():
            segments = []
            for ln in speaker_lines:
                idx = ln.get("idx")
                src = by_idx.get(idx)
                if src is None:
                    continue
                start = _microseconds(ln["start"])
                dur = _microseconds(ln["duration"])

                mat_id = _uuid()
                mat = self._clone_material(self._tmpl_material(template, "audios"))
                mat["id"] = mat_id
                mat["type"] = "extract_music"
                mat["path"] = (
                    f"##_draftpath_placeholder_{CAPCUT_PLACEHOLDER_UUID}_##/media/{src.name}"
                )
                mat["name"] = src.stem
                mat["duration"] = dur
                mat["category_name"] = "local"
                mat["app_id"] = 0
                mat["local_material_id"] = ""
                mats.append(mat)

                extras = self._build_audio_extras()
                speeds += extras["speeds"]
                placeholders += extras["placeholders"]
                mappings += extras["sound_mappings"]
                vocals += extras["vocal_seps"]
                beats += extras["beats"]

                seg = self._clone_segment(seg_template)
                seg["id"] = _uuid()
                seg["material_id"] = mat_id
                seg["source_timerange"] = {"start": 0, "duration": dur}
                seg["target_timerange"] = {"start": start, "duration": dur}
                seg["extra_material_refs"] = [
                    extras["speeds"][0]["id"],
                    extras["placeholders"][0]["id"],
                    extras["beats"][0]["id"],
                    extras["sound_mappings"][0]["id"],
                    extras["vocal_seps"][0]["id"],
                ]
                segments.append(seg)

            if not segments:
                continue

            tracks.append(
                {
                    "id": _uuid(),
                    "type": "audio",
                    "attribute": 0,
                    "flag": 0,
                    "segments": segments,
                    "name": speaker,
                    "is_default_name": False,
                }
            )

        extras_all = {
            "speeds": speeds,
            "placeholders": placeholders,
            "sound_mappings": mappings,
            "vocal_seps": vocals,
            "beats": beats,
        }
        return tracks, mats, extras_all

    def _build_sfx_tracks(
        self,
        timeline: dict,
        sfx_files: dict[str, Path],
        seg_template: dict,
        template: dict,
    ) -> tuple[list[dict], list[dict], dict]:
        """Tạo track tiếng động: mỗi đoạn có tiếng động là một track riêng."""
        events: list[dict] = []

        # Tiếng động gắn với câu nói (đặt đầu câu)
        for ln in timeline.get("lines", []):
            if ln.get("sfx") and ln["sfx"] in sfx_files:
                events.append(
                    {
                        "name": ln["sfx"],
                        "start": ln["start"],
                        "duration": ln.get("sfx_duration") or 1.0,
                    }
                )

        # Tiếng động ở nhịp phản ứng
        for bt in timeline.get("beats", []):
            if bt.get("sfx") and bt["sfx"] in sfx_files:
                events.append(
                    {
                        "name": bt["sfx"],
                        "start": bt["start"],
                        "duration": bt.get("duration") or 1.0,
                    }
                )

        if not events:
            return [], [], {"speeds": [], "placeholders": [], "sound_mappings": [],
                           "vocal_seps": [], "beats": []}

        # Gom theo tên file: mỗi loại tiếng động một track
        by_name: dict[str, list[dict]] = {}
        for ev in events:
            by_name.setdefault(ev["name"], []).append(ev)

        tracks: list[dict] = []
        mats: list[dict] = []
        speeds, placeholders, mappings, vocals, beats = [], [], [], [], []

        for name, evs in by_name.items():
            src = sfx_files[name]
            segments = []
            for ev in evs:
                start = _microseconds(ev["start"])
                dur = _microseconds(ev["duration"])

                mat_id = _uuid()
                mat = self._clone_material(self._tmpl_material(template, "audios"))
                mat["id"] = mat_id
                mat["type"] = "extract_music"
                mat["path"] = (
                    f"##_draftpath_placeholder_{CAPCUT_PLACEHOLDER_UUID}_##/media/{src.name}"
                )
                mat["name"] = src.stem
                mat["duration"] = dur
                mat["category_name"] = "local"
                mat["app_id"] = 0
                mat["local_material_id"] = ""
                mats.append(mat)

                extras = self._build_audio_extras()
                speeds += extras["speeds"]
                placeholders += extras["placeholders"]
                mappings += extras["sound_mappings"]
                vocals += extras["vocal_seps"]
                beats += extras["beats"]

                seg = self._clone_segment(seg_template)
                seg["id"] = _uuid()
                seg["material_id"] = mat_id
                seg["source_timerange"] = {"start": 0, "duration": dur}
                seg["target_timerange"] = {"start": start, "duration": dur}
                seg["extra_material_refs"] = [
                    extras["speeds"][0]["id"],
                    extras["placeholders"][0]["id"],
                    extras["beats"][0]["id"],
                    extras["sound_mappings"][0]["id"],
                    extras["vocal_seps"][0]["id"],
                ]
                segments.append(seg)

            tracks.append(
                {
                    "id": _uuid(),
                    "type": "audio",
                    "attribute": 0,
                    "flag": 0,
                    "segments": segments,
                    "name": name,
                    "is_default_name": False,
                }
            )

        extras_all = {
            "speeds": speeds,
            "placeholders": placeholders,
            "sound_mappings": mappings,
            "vocal_seps": vocals,
            "beats": beats,
        }
        return tracks, mats, extras_all

    def _build_text_tracks(
        self, timeline: dict, template: dict, project_dir: Path
    ) -> tuple[list[dict], list[dict], dict]:
        """Tạo track phụ đề từ file .srt của tập."""
        srt_path = project_dir / "out" / "phude.srt"
        if not srt_path.exists():
            return [], [], {"animations": []}

        entries = _parse_srt(srt_path.read_text(encoding="utf-8"))
        if not entries:
            return [], [], {"animations": []}

        text_template = self._tmpl_material(template, "texts")
        text_seg_template = self._tmpl_segment(template, "text")
        font_path = text_template.get("font_path", "")

        segments = []
        mats = []
        animations = []

        for text, start_sec, dur_sec in entries:
            mat_id = _uuid()
            mat = self._clone_material(text_template)
            mat["id"] = mat_id
            mat["content"] = json.dumps(
                {
                    "styles": [
                        {
                            "fill": {
                                "alpha": 1.0,
                                "content": {
                                    "render_type": "solid",
                                    "solid": {"alpha": 1.0, "color": [1.0, 1.0, 1.0]},
                                },
                            },
                            "font": {"id": "", "path": font_path},
                            "range": [0, len(text)],
                            "size": 11.0,
                        }
                    ],
                    "text": text,
                },
                ensure_ascii=False,
            )
            mat["name"] = ""
            mat["group_id"] = f"import_{_now_microseconds() // 1000000}"
            mat["text_to_audio_ids"] = []
            mats.append(mat)

            anim_id = _uuid()
            animations.append(
                {
                    "id": anim_id,
                    "type": "sticker_animation",
                    "animations": [],
                    "multi_language_current": "none",
                }
            )

            start = _microseconds(start_sec)
            dur = _microseconds(dur_sec)
            seg = self._clone_segment(text_seg_template)
            seg["id"] = _uuid()
            seg["material_id"] = mat_id
            seg["source_timerange"] = None
            seg["target_timerange"] = {"start": start, "duration": dur}
            seg["extra_material_refs"] = [anim_id]
            segments.append(seg)

        tracks = [
            {
                "id": _uuid(),
                "type": "text",
                "attribute": 2,
                "flag": 1,
                "segments": segments,
                "name": "Phụ đề",
                "is_default_name": False,
            }
        ]
        return tracks, mats, {"animations": animations}

    def _build_draft_content(
        self,
        draft_id: str,
        draft_name: str,
        video_path: Path,
        audio_files: list[Path],
        sfx_files: dict[str, Path],
        timeline: dict,
        project_dir: Path,
    ) -> dict:
        """Tạo draft_content.json đầy đủ: video + giọng theo nhân vật + SFX + BGM + phụ đề."""
        # Đọc template từ dự án mẫu
        template_path = self.template_draft / "Timelines"
        template_tl_id = None
        for p in template_path.glob("*"):
            if p.is_dir() and (p / "draft_content.json").exists():
                template_tl_id = p.name
                break
        if not template_tl_id:
            # Dự án mẫu cũ chỉ có draft_content.json ở thư mục gốc
            legacy = self.template_draft / "draft_content.json"
            if legacy.exists():
                with open(legacy, encoding="utf-8") as f:
                    template = json.load(f)
            else:
                raise FileNotFoundError(
                    f"Không tìm thấy draft_content.json trong dự án mẫu: {self.template_draft}"
                )
        else:
            with open(template_path / template_tl_id / "draft_content.json", encoding="utf-8") as f:
                template = json.load(f)

        total_duration = _microseconds(timeline.get("total", 10.0))

        # === 1. Video track ===
        video_id = _uuid()
        video_mat = self._clone_material(self._tmpl_material(template, "videos"))
        video_mat["type"] = "video"
        video_mat["id"] = video_id
        video_mat["path"] = str(video_path).replace("\\", "/")
        video_mat["material_name"] = video_path.name
        video_mat["duration"] = total_duration
        video_mat["has_audio"] = False
        # khung theo video đã dựng (9:16, 16:9 hoặc 1:1)
        cw = int(timeline.get("width") or 1080)
        chh = int(timeline.get("height") or 1920)
        video_mat["width"], video_mat["height"] = cw, chh

        video_extra_refs = self._build_extra_refs_for_video(template, (cw, chh))
        video_seg = self._clone_segment(self._tmpl_segment(template, "video"))
        video_seg["id"] = _uuid()
        video_seg["material_id"] = video_id
        video_seg["source_timerange"] = {"start": 0, "duration": total_duration}
        video_seg["target_timerange"] = {"start": 0, "duration": total_duration}
        video_seg["extra_material_refs"] = [r["id"] for r in video_extra_refs]

        video_track = {
            "id": _uuid(),
            "type": "video",
            "attribute": 0,
            "flag": 0,
            "segments": [video_seg],
            "name": "",
            "is_default_name": True,
        }

        # === 2. Audio tracks (giọng theo nhân vật) ===
        audio_template_seg = self._tmpl_segment(template, "audio")
        audio_tracks, audio_mats, audio_extras = self._build_audio_tracks(
            timeline, audio_files, audio_template_seg, template
        )

        # === 3. SFX tracks (tiếng động) ===
        sfx_tracks, sfx_mats, sfx_extras = self._build_sfx_tracks(
            timeline, sfx_files, audio_template_seg, template
        )

        # === 4. Text tracks (phụ đề) ===
        text_tracks, text_mats, text_extras = self._build_text_tracks(timeline, template, project_dir)

        # === 5. BGM track (nhạc nền) — tạm bỏ qua nếu không có ===
        bgm_tracks, bgm_mats, bgm_extras = [], [], {
            "speeds": [],
            "placeholders": [],
            "sound_mappings": [],
            "vocal_seps": [],
            "beats": [],
        }

        # Gộp tất cả tracks
        all_tracks = [video_track] + audio_tracks + sfx_tracks + text_tracks + bgm_tracks

        # Gộp materials
        all_audio_mats = audio_mats + sfx_mats + bgm_mats
        all_text_mats = text_mats

        # Gộp extra materials
        all_speeds = [r for r in video_extra_refs if r["type"] == "speed"]
        all_speeds += audio_extras["speeds"] + sfx_extras["speeds"] + bgm_extras["speeds"]
        all_placeholders = [r for r in video_extra_refs if r["type"] == "placeholder_info"]
        all_placeholders += audio_extras["placeholders"] + sfx_extras["placeholders"] + bgm_extras["placeholders"]
        all_sound_mappings = [r for r in video_extra_refs if r.get("audio_channel_mapping") is not None]
        all_sound_mappings += audio_extras["sound_mappings"] + sfx_extras["sound_mappings"] + bgm_extras["sound_mappings"]
        all_vocal_seps = [r for r in video_extra_refs if r["type"] == "vocal_separation"]
        all_vocal_seps += audio_extras["vocal_seps"] + sfx_extras["vocal_seps"] + bgm_extras["vocal_seps"]
        all_beats = audio_extras["beats"] + sfx_extras["beats"] + bgm_extras["beats"]
        all_canvases = [r for r in video_extra_refs if r["type"] == "canvas_color"]
        all_material_colors = [r for r in video_extra_refs if r.get("value") is not None and "value" in r]
        all_material_animations = text_extras.get("animations", [])

        # Tạo draft_content
        content = {
            "id": draft_id,
            "version": template.get("version", 360000),
            "new_version": template.get("new_version", "110.0.0"),
            "name": draft_name,
            "duration": total_duration,
            "create_time": _now_microseconds(),
            "update_time": _now_microseconds(),
            "fps": 30.0,
            "is_drop_frame_timecode": False,
            "color_space": 0,
            "config": template.get("config", {}),
            "canvas_config": {"ratio": "original", "width": cw, "height": chh, "background": None},
            "tracks": all_tracks,
            "group_container": template.get("group_container", {}),
            "materials": {
                "videos": [video_mat],
                "audios": all_audio_mats,
                "texts": all_text_mats,
                "images": [],
                "effects": [],
                "stickers": [],
                "canvases": all_canvases,
                "transitions": [],
                "audio_effects": [],
                "audio_fades": [],
                "beats": all_beats,
                "material_animations": all_material_animations,
                "placeholders": [],
                "placeholder_infos": all_placeholders,
                "speeds": all_speeds,
                "common_mask": [],
                "chromas": [],
                "text_templates": [],
                "realtime_denoises": [],
                "audio_pannings": [],
                "audio_pitch_shifts": [],
                "video_trackings": [],
                "hsl": [],
                "drafts": [],
                "color_curves": [],
                "hsl_curves": [],
                "primary_color_wheels": [],
                "log_color_wheels": [],
                "video_effects": [],
                "ai_text_effects": [],
                "audio_balances": [],
                "handwrites": [],
                "manual_deformations": [],
                "manual_beautys": [],
                "plugin_effects": [],
                "sound_channel_mappings": all_sound_mappings,
                "green_screens": [],
                "shapes": [],
                "material_colors": all_material_colors,
                "digital_humans": [],
                "digital_human_model_dressing": [],
                "smart_crops": [],
                "ai_translates": [],
                "audio_track_indexes": [],
                "loudnesses": [],
                "vocal_beautifys": [],
                "vocal_separations": all_vocal_seps,
                "smart_relights": [],
                "time_marks": [],
                "multi_language_refs": [],
                "video_shadows": [],
                "video_strokes": [],
                "video_radius": [],
                "flowers": [],
                "tail_leaders": [],
            },
            "keyframes": template.get("keyframes", {}),
            "keyframe_graph_list": [],
            "platform": template.get("platform", {}),
            "last_modified_platform": template.get("last_modified_platform", {}),
            "mutable_config": template.get("mutable_config", {}),
            "cover": "",
            "retouch_cover": "",
            "extra_info": "",
            "relationships": [],
            "mixed_track_mode_on": False,
            "render_index_track_mode_on": False,
            "free_render_index_mode_on": True,
            "static_cover_image_path": "",
            "source": "default",
            "time_marks": [],
            "path": "",
            "lyrics_effects": [],
            "uneven_animation_template_info": {},
            "draft_type": "video",
            "smart_ads_info": {},
            "function_assistant_info": {},
        }

        return content

    def _build_draft_meta(
        self, draft_id: str, draft_name: str, draft_folder: Path, duration: int
    ) -> dict:
        """Tạo draft_meta_info.json."""
        now = _now_microseconds()
        return {
            "draft_id": draft_id,
            "draft_name": draft_name,
            "draft_fold_path": str(draft_folder).replace("\\", "/"),
            "draft_root_path": str(self.capcut_root).replace("\\", "/"),
            "draft_cover": "draft_cover.jpg",
            "tm_draft_create": now,
            "tm_draft_modified": now,
            "tm_draft_removed": 0,
            "tm_duration": duration,
            "cloud_draft_cover": False,
            "cloud_draft_sync": False,
            "draft_is_invisible": False,
            "draft_is_ai_shorts": False,
            "draft_is_cloud_temp_draft": False,
            "draft_is_infinite_canvas_draft": False,
            "draft_is_pippit_draft": False,
            "draft_is_web_article_video": False,
            "draft_cloud_last_action_download": False,
            "draft_cloud_purchase_info": "",
            "draft_cloud_template_id": "",
            "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "",
            "draft_cloud_package_type": "",
            "cloud_package_completed_time": "",
            "draft_cloud_capcut_purchase_info": "",
            "draft_type": "",
            "draft_web_article_video_enter_from": "",
            "draft_new_version": "",
            "pippit_id": "",
            "pippit_user_name": "",
            "pippit_avatar_url": "",
            "pippit_extra_info": "",
            "tm_draft_cloud_completed": "",
            "tm_draft_cloud_entry_id": -1,
            "tm_draft_cloud_modified": 0,
            "tm_draft_cloud_parent_entry_id": -1,
            "tm_draft_cloud_space_id": -1,
            "tm_draft_cloud_user_id": -1,
            "draft_materials": [],
            "draft_materials_copied_info": [],
            "draft_segment_extra_info": [],
            "draft_timeline_materials_size_": 0,
            "draft_removable_storage_device": "",
            "draft_need_rename_folder": False,
            "draft_deeplink_url": "",
            "draft_is_from_deeplink": "false",
            "draft_enterprise_info": {
                "draft_enterprise_id": "",
                "draft_enterprise_name": "",
                "draft_enterprise_extra": "",
                "enterprise_material": [],
            },
            "draft_is_ae_produce": False,
            "draft_is_ai_packaging_used": False,
            "draft_is_ai_translate": False,
            "draft_is_article_video_draft": False,
            "draft_has_unfinished_aigc_video_effect": False,
        }

    def _write_minimal_configs(self, draft_folder: Path) -> None:
        """Tạo các file config tối thiểu."""
        # draft_settings
        (draft_folder / "draft_settings").write_text(
            f"[General]\ndraft_create_time={_now_microseconds() // 1000000}\n"
            f"draft_last_edit_time={_now_microseconds() // 1000000}\n"
            f"real_edit_seconds=0\nreal_edit_keys=0\n",
            encoding="utf-8",
        )

        # draft_biz_config.json
        (draft_folder / "draft_biz_config.json").write_text("", encoding="utf-8")

        # draft_agency_config.json
        (draft_folder / "draft_agency_config.json").write_text(
            json.dumps(
                {
                    "is_auto_agency_enabled": False,
                    "is_auto_agency_popup": False,
                    "is_single_agency_mode": False,
                    "marterials": None,
                    "use_converter": False,
                    "video_resolution": 720,
                }
            ),
            encoding="utf-8",
        )

        # draft_virtual_store.json
        (draft_folder / "draft_virtual_store.json").write_text(
            json.dumps(
                {
                    "draft_materials": [],
                    "draft_virtual_store": [
                        {"type": 0, "value": []},
                        {"type": 1, "value": []},
                        {"type": 2, "value": []},
                    ],
                }
            ),
            encoding="utf-8",
        )

        # attachment_pc_common.json
        (draft_folder / "attachment_pc_common.json").write_text(
            json.dumps(
                {
                    "ai_packaging_infos": [],
                    "ai_packaging_report_info": {},
                    "broll": {"ai_packaging_infos": [], "ai_packaging_report_info": {}},
                    "commercial_music_category_ids": [],
                    "pc_feature_flag": 0,
                    "recognize_tasks": [],
                    "reference_lines_config": {
                        "horizontal_lines": [],
                        "is_lock": False,
                        "is_visible": False,
                        "vertical_lines": [],
                    },
                    "safe_area_type": 0,
                    "template_item_infos": [],
                    "unlock_template_ids": [],
                }
            ),
            encoding="utf-8",
        )

        # performance_opt_info.json
        (draft_folder / "performance_opt_info.json").write_text(
            json.dumps({"manual_cancle_precombine_segs": None, "need_auto_precombine_segs": None}),
            encoding="utf-8",
        )

    # ---- lấy mẫu từ dự án mẫu, thiếu thì dùng khung mặc định ----
    # Dự án mẫu của mỗi người khác nhau (có khi dùng ảnh thay video, thiếu
    # chữ/âm thanh, track chữ đứng đầu...). Trước đây code lấy thẳng [0] nên
    # thiếu một thứ là lỗi "list index out of range".

    def _tmpl_material(self, template: dict, kind: str) -> dict:
        mats = (template.get("materials") or {}).get(kind) or []
        if kind == "videos":
            vids = [m for m in mats if m.get("type") == "video"]
            mats = vids or mats
        if mats:
            return mats[0]
        return dict(DEFAULT_MATERIALS[kind])

    def _tmpl_segment(self, template: dict, track_type: str) -> dict:
        for t in template.get("tracks") or []:
            if t.get("type") == track_type and t.get("segments"):
                return t["segments"][0]
        seg = dict(DEFAULT_SEGMENT)
        if track_type == "text":
            seg["clip"] = {**DEFAULT_SEGMENT["clip"], "transform": {"x": 0.0, "y": -0.72}}
        if track_type == "audio":
            seg.pop("clip", None)
        return seg

    def _clone_material(self, src: dict) -> dict:
        """Deep copy material, đặt ID mới."""
        import copy

        return copy.deepcopy(src)

    def _clone_segment(self, src: dict) -> dict:
        """Deep copy segment, đặt ID mới."""
        import copy

        return copy.deepcopy(src)
