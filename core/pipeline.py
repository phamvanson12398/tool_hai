# -*- coding: utf-8 -*-
"""Nối toàn bộ quy trình: kịch bản -> giọng -> timeline -> video.

Thứ tự đúng như spec:
  1. Tạo giọng từng câu, đo độ dài thật, cắt bỏ khoảng im ở đầu và cuối.
  2. Xếp câu sau ngay sau câu trước, cách 0,1 giây; chỉ dừng lâu ở nhịp '>'.
  3. Miệng mở khi có tiếng, ngậm khi im (đo theo âm lượng giọng).
  4. Đổi biểu cảm, zoom vào người nói ở câu có zoom, chèn tiếng động.
  5. Tiêu đề cố định trên cùng; phụ đề vàng viền đen nhảy theo lời.
"""
from __future__ import annotations

import json
import logging
import shutil
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image

from . import assets, config, pacing, video, voice
from .script_parser import Script, parse_script

# Cử động (Bước D) — import được cả hai kiểu nhân vật (kit + ảnh tải lên)
try:
    from . import rig as rig_mod
    from . import gestures as gmod
    from . import photo_rig
    from .character_kit import CharSpec
    RIG_AVAILABLE = True
except Exception:  # pragma: no cover - phụ thuộc môi trường
    RIG_AVAILABLE = False

logger = logging.getLogger(__name__)


def _say(progress, frac: float, msg: str) -> None:
    if progress:
        progress(frac, msg)


# Câu đọc để tạo giọng mẫu (~5 giây, giọng bình thường) cho nhân vật chưa có mẫu
ANCHOR_TEXT = {
    "vi": "Xin chào, hôm nay trời đẹp quá. Mình đi dạo một vòng rồi về ăn cơm nhé.",
    "ko": "안녕하세요, 오늘 날씨 정말 좋네요. 잠깐 산책하고 와서 밥 먹을까요?",
    "en": "Hi there, it's a really nice day today. Let's take a quick walk and then grab some lunch.",
}


def _seed_of(name: str) -> int:
    import zlib
    return zlib.crc32(name.encode("utf-8")) % 100000


def voice_anchor(pdir: Path, name: str, language: str, instruct: str | None) -> dict | None:
    """Giọng mẫu cố định cho nhân vật CHƯA có giọng mẫu tải lên.

    Tạo giọng thẳng từ mô tả thì mỗi câu OmniVoice chọn ngẫu nhiên một giọng
    mới khớp mô tả -> mỗi câu một giọng. Nên tạo MỘT đoạn mẫu (seed cố định
    theo tên) rồi mọi câu nhân bản từ đoạn đó. Lưu trong thư mục tập để lần
    dựng sau giữ đúng giọng; đổi mô tả giọng thì tạo lại."""
    vdir = pdir / "audio" / "giong_mau"
    vdir.mkdir(parents=True, exist_ok=True)
    slug = assets.config_slug(name) or "nv"
    wav_p, meta_p = vdir / f"{slug}_{language}.wav", vdir / f"{slug}_{language}.json"
    text = ANCHOR_TEXT.get(language, ANCHOR_TEXT["en"])
    want = {"instruct": instruct or "", "language": language, "text": text}
    try:
        if wav_p.exists() and meta_p.exists() and json.loads(meta_p.read_text("utf-8")) == want:
            return {"ref": str(wav_p), "ref_text": text}
        wav, sr = voice.synthesize(text, language, instruct=instruct or None,
                                   seed=_seed_of(name))
        wav = voice.trim_silence(np.asarray(wav, dtype=np.float32), sr)
        if wav.size < sr:                        # dưới 1 giây: mẫu hỏng, bỏ
            return None
        sf.write(str(wav_p), wav, sr)
        meta_p.write_text(json.dumps(want, ensure_ascii=False), encoding="utf-8")
        return {"ref": str(wav_p), "ref_text": text}
    except Exception as e:  # noqa: BLE001
        logger.warning("Không tạo được giọng mẫu cho %s: %s", name, e)
        return None


def synth_lines(script: Script, pdir: Path, voices: dict,
                progress=None) -> list[dict]:
    """Tạo giọng từng câu. voices: {tên: {"ref": path|None, "ref_text": str,
    "instruct": str|None}}"""
    audio_dir = pdir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    out = []
    # nhân vật chưa có giọng mẫu: tạo một đoạn mẫu cố định, mọi câu nhân bản từ đó
    voices = {k: dict(v) for k, v in voices.items()}
    for name in dict.fromkeys(b.speaker for b in script.beats if b.kind == "line"):
        vcfg = voices.setdefault(name, {})
        if vcfg.get("ref") and Path(vcfg["ref"]).exists():
            continue
        _say(progress, 0.03, f"tạo giọng mẫu cố định cho {name}")
        anchor = voice_anchor(pdir, name, script.language, vcfg.get("instruct"))
        if anchor:
            vcfg.update(anchor)
    beats = script.beats
    n_lines = len([b for b in beats if b.kind == "line"])
    done = 0

    for i, b in enumerate(beats):
        if b.kind != "line":
            out.append({"kind": "react", "beat": b})
            continue

        vcfg = voices.get(b.speaker, {})
        ref = vcfg.get("ref")
        wav, sr = voice.synthesize(
            b.text,
            script.language,
            ref_wav=Path(ref) if ref else None,
            ref_text=vcfg.get("ref_text") or None,
            instruct=vcfg.get("instruct") or None,
            seed=_seed_of(b.speaker) + i,        # dựng lại vẫn ra đúng câu đó
        )
        wav = voice.trim_silence(np.asarray(wav, dtype=np.float32), sr)
        if wav.size == 0:
            wav = np.zeros(int(sr * config.MIN_LINE_SECONDS), dtype=np.float32)

        path = audio_dir / f"line_{i:03d}.wav"
        sf.write(str(path), wav, sr)
        dur = len(wav) / float(sr)
        out.append({"kind": "line", "beat": b, "audio": path,
                    "duration": dur, "sr": sr})
        done += 1
        _say(progress, 0.05 + 0.45 * done / max(1, n_lines),
             f"tạo giọng {done}/{n_lines}: {b.speaker}")
    return out


def _natural_gaps(segments: list[dict], gap: float, natural: bool) -> list[float]:
    """Khoảng nghỉ sau mỗi câu (0 cho nhịp '>')."""
    beats = [s["beat"] for s in segments]
    out = []
    for i, b in enumerate(beats):
        if b.kind != "line":
            out.append(0.0)
        elif natural:
            out.append(pacing.natural_gap(b.text, b.speaker,
                                          pacing.next_speaker_of(beats, i), gap))
        else:
            out.append(gap)
    return out


def build_timeline(script: Script, segments: list[dict], gap: float,
                   target: float | None = None,
                   natural: bool = True) -> video.Timeline:
    """Xếp các câu; nhịp '>' là khoảng lặng có chủ đích.

    natural: khoảng nghỉ đổi theo ngữ cảnh như nói chuyện thật (core/pacing).
    target: thời lượng đích (giây); video ngắn hơn thì giãn nhẹ các khoảng
    nghỉ và nhịp phản ứng cho sát đích, không kéo chậm giọng.

    Video bắt đầu sau VIDEO_START_DELAY giây và giữ khung cuối
    VIDEO_END_HOLD giây, nên tổng thời lượng = nội dung + delay + hold.
    """
    gaps = _natural_gaps(segments, gap, natural)
    reacts = [s["beat"].duration or config.DEFAULT_REACT_SECONDS
              for s in segments if s["kind"] == "react"]
    raw = (config.VIDEO_START_DELAY + config.VIDEO_END_HOLD + sum(gaps) + sum(reacts)
           + sum(max(s["duration"], config.MIN_LINE_SECONDS) + (s["beat"].pause or 0.0)
                 for s in segments if s["kind"] == "line"))
    gx, rx = pacing.fit_extra(target, raw, gaps, reacts)
    rx_iter = iter(rx)

    tl = video.Timeline()
    tl.scene_cast = [list(c) if c else None for c in getattr(script, "scene_cast", [])]
    t = config.VIDEO_START_DELAY
    for idx, seg in enumerate(segments):
        b = seg["beat"]
        if seg["kind"] == "react":
            dur = (b.duration or config.DEFAULT_REACT_SECONDS) + next(rx_iter)
            tl.beats.append(video.Beat(
                idx=idx, actor=b.speaker, expression=b.expression, zoom=b.zoom,
                sfx=_sfx_file(b.sfx), start=t, duration=dur, scene=b.scene,
                gestures=list(b.gestures), effects=list(b.effects),
                props=dict(b.props), shot=b.shot,
            ))
            # nhịp phản ứng: giữ nguyên độ dài, không cộng thêm gap
            t += dur
        else:
            dur = max(seg["duration"], config.MIN_LINE_SECONDS)
            ln = video.Line(
                idx=idx, speaker=b.speaker, text=b.text,
                expression=b.expression, zoom=b.zoom,
                sfx=_sfx_file(b.sfx), start=t, duration=dur,
                audio=seg["audio"],
                gestures=list(b.gestures),
                effects=list(b.effects),
                scene=b.scene,
                props=dict(b.props),
                shot=b.shot,
            )
            ln.words = _phrase_times(b.text, t, dur)
            # tuỳ chọn thay đổi biểu cảm người nghe ngay khi câu bắt đầu
            if b.other_expr:
                ln.other_expr = dict(b.other_expr)
            # tuỳ chọn zoom=Tên (zoom vào người khác, không phải người nói)
            if b.zoom_target:
                ln.zoom_target = b.zoom_target
            tl.lines.append(ln)
            t += dur + gaps[idx] + gx[idx] + (b.pause or 0.0)
    # giữ khung cuối thêm một lúc
    t += config.VIDEO_END_HOLD
    tl.total = max(t, 1.0)
    return tl


def _sfx_file(name: str | None) -> str | None:
    """Tìm file tiếng động trong data/sfx (bỏ qua nếu chưa có)."""
    if not name:
        return None
    config.SFX_DIR.mkdir(parents=True, exist_ok=True)
    for ext in (".wav", ".mp3", ".ogg", ".m4a"):
        p = config.SFX_DIR / f"{name}{ext}"
        if p.exists():
            return p.name
    return None


def _phrase_times(text: str, start: float, dur: float) -> list[tuple[str, float, float]]:
    """Chia câu thành từng từ, trải đều theo độ dài giọng.

    Phụ đề nhảy theo lời: mỗi từ có khoảng thời gian riêng, nên cụm hiện ra
    lần lượt thay vì hiện cả câu một lúc.
    """
    words = text.split()
    if not words:
        return []
    lengths = [max(1, len(w)) for w in words]
    total = sum(lengths)
    out = []
    t = start
    for w, ln in zip(words, lengths):
        d = dur * (ln / total)
        out.append((w, t, t + d))
        t += d
    return out


def resolve_characters(script: Script, chars_cfg: list[dict],
                       enable_rig: bool = False) -> list[video.Character]:
    """Chuyển cấu hình nhân vật thành đối tượng để dựng hình.

    Nếu enable_rig và RIG_AVAILABLE: gắn rig animator cho mỗi nhân vật
    (kit dùng RigRenderer/CharacterAnimator, ảnh tải lên dùng PhotoCharacter).
    """
    side_map = {"trai": "left", "phai": "right", "giua": "center",
                "left": "left", "right": "right", "center": "center"}
    out = []
    for c in chars_cfg:
        name = c["name"]
        side = side_map.get(str(script.sides.get(name, c.get("side", "center"))).lower(),
                            "center")
        img = c.get("image")
        mo = c.get("mouth_open")
        dong = c.get("mouth_closed")
        images = c.get("images") or {}
        if not img and images:
            first = next(iter(images.values()))
            img = first.get("dong") or first.get("mo")
            mo = first.get("mo")
            dong = first.get("dong")
        if not img:
            continue
        mp = c.get("mouth_pos")
        char = video.Character(
            name=name, side=side, image=Path(img),
            mouth_open=Path(mo) if mo else None,
            mouth_closed=Path(dong) if dong else None,
            images=images,
            mouth_pos=tuple(mp) if mp and len(mp) == 2 else None,
            scale=float(c.get("scale", 1.0) or 1.0),
        )
        # ----- gắn rig animator nếu bật cử động -----
        if enable_rig and RIG_AVAILABLE:
            try:
                _attach_rig_animator(char, c, name)
            except Exception as e:  # gắn rig lỗi -> vẫn dùng ảnh tĩnh
                config.log_render(
                    f"Không gắn được cử động cho nhân vật '{name}': {e}. "
                    f"Chuyển sang dựng ảnh tĩnh (cách cũ).", "warning")
        out.append(char)

    # xếp theo vị trí trong khung: trái -> giữa -> phải
    order = {"left": 0, "center": 1, "right": 2}
    out.sort(key=lambda c: order.get(c.side, 1))
    return out


# ------------------------------------------------------------------ cử động (Bước D)

def _attach_rig_animator(char: video.Character, c: dict, name: str) -> None:
    """Gắn rig animator vào một nhân vật (kit hoặc ảnh tải lên)."""
    mode = str(c.get("mode", ""))
    img_path = Path(char.image) if char.image else None

    if mode == "kit" or c.get("spec"):
        # Nhân vật vẽ bằng bộ ghép: dựng RigRenderer từ spec + thư mục parts
        spec_d = dict(c.get("spec") or {})
        spec_d.setdefault("name", name)
        spec = CharSpec.from_dict(spec_d)
        # Mỗi nhân vật một thư mục rig riêng cạnh bộ ảnh của nó (trước đây
        # dùng thư mục cha chung nên mọi nhân vật ăn chung một rig.json).
        if img_path and img_path.exists():
            base_dir = img_path.parent / "_rig"
        else:
            base_dir = config.DATA / "tmp" / "rig_kit" / assets.config_slug(name)
        rig_path = base_dir / "rig.json"
        rig = rig_mod.load_rig(rig_path) if rig_path.exists() else None
        if rig is None or rig.spec != spec.to_dict():
            # chưa có, hoặc ngoại hình đã đổi -> dựng lại từ spec
            rig = rig_mod.build_rig(spec, base_dir)
        char.rig_animator = rig_mod.CharacterAnimator(rig, base_dir, name)
    else:
        # Nhân vật tải lên 1 ảnh: dùng PhotoCharacter (tách nền + ước khớp)
        src = c.get("image") or (str(img_path) if img_path else None)
        if not src or not Path(src).exists():
            return
        pchar = photo_rig.PhotoCharacter.load(name, Path(src))
        char.rig_animator = _PhotoRigAnimator(pchar)


class _PhotoRigAnimator:
    """Wrapper làm PhotoCharacter có render_frame(t, speaking, mouth_open)
    tương tự CharacterAnimator (dùng cho ảnh tải lên)."""

    def __init__(self, pchar: photo_rig.PhotoCharacter):
        self.pchar = pchar
        self.name = pchar.name
        self.current_gesture = None
        self.current_effect = None
        self.gesture_start = None

    def set_props(self, change, t: float) -> None:
        """Ảnh tải lên chưa hỗ trợ đạo cụ — bỏ qua."""
        return None

    def set_gesture(self, name: str | None, effect: str | None,
                    start_time: float) -> None:
        gmod.switch_gesture(self, name, effect, start_time)

    def _angles_at(self, t: float, speaking: bool) -> dict[str, float]:
        angles = gmod.breathe_angles(t, gmod.stable_seed(self.name))
        if speaking:
            angles = gmod.merge_angles(angles, gmod.idle_arm_angles(t,
                                       gmod.stable_seed(self.name)))
        if self.current_effect:
            angles = gmod.merge_angles(angles,
                                       gmod.effect_angles(self.current_effect,
                                                          t, gmod.stable_seed(self.name)))
        angles = gmod.merge_angles(angles, gmod.base_pose(self))
        angles = gmod.merge_angles(angles, gmod.fade_pose(getattr(self, "_fade_from", None),
                                                          getattr(self, "_fade_t0", 0.0), t))
        if self.current_gesture is not None and self.gesture_start is not None:
            pose = gmod.gesture_pose(self.current_gesture, t - self.gesture_start)
            if pose:
                angles = gmod.merge_angles(angles, pose)
        return angles

    def render_frame(self, t: float, speaking: bool, mouth_open: bool,
                     expression: str | None = None) -> Image.Image:
        angles = self._angles_at(t, speaking)
        self.last_angles = angles
        # có lề để tay giơ ra ngoài ảnh không bị cắt; frame_origin/frame_size
        # cho biết ảnh gốc nằm đâu để đặt nhân vật đúng chỗ
        img, self.frame_origin = self.pchar.render_padded(angles)
        self.frame_size = self.pchar.rgba.size
        return img


# ================================================================== render


def render_episode(pdir: Path, script: Script, chars_cfg: list[dict],
                   bg_path: Path | None, voices: dict, settings: dict,
                   progress=None, scene_bgs: dict[int, Path] | None = None,
                   scene_kinds: dict[int, dict] | None = None) -> dict:
    """Chạy toàn bộ: giọng -> timeline -> video -> bộ file rời.

    bg_path: ảnh nền chung; scene_bgs: {chỉ số cảnh: ảnh nền} cho kịch bản
    nhiều bối cảnh (cảnh không có ảnh riêng thì dùng bg_path).
    """
    _say(progress, 0.02, "chuẩn bị")
    segments = synth_lines(script, pdir, voices, progress)
    gap = float(settings.get("gap_between_lines", config.GAP_BETWEEN_LINES))
    target = settings.get("target_duration") or None
    tl = build_timeline(script, segments, gap, target=target,
                        natural=bool(settings.get("natural_pacing", True)))
    msg = f"độ dài video: {tl.total:.1f} giây"
    if target and tl.total < target * 0.93:
        msg += (f" (ngắn hơn đích {target:.0f} giây — kịch bản ít lời, "
                f"nên thêm vài câu)")
    _say(progress, 0.52, msg)

    chars = resolve_characters(script, chars_cfg,
                               enable_rig=bool(settings.get("enable_rig")))
    if not chars:
        raise RuntimeError("Chưa có ảnh nhân vật nào để dựng hình.")

    stage = video.Stage(*config.frame_size(settings.get("video_format")))
    if stage.h > stage.w and settings.get("wide_stage", True):
        # khung dọc: sân khấu rộng, nhân vật đứng giãn ra, máy quay lia theo người nói
        stage.set_world(video.WIDE_FACTOR)
    if bg_path and Path(bg_path).exists():
        stage.set_background(Path(bg_path))
    if scene_bgs:
        stage.set_scene_backgrounds(scene_bgs)
    if stage.wide:
        # bối cảnh AI vẽ: vẽ lại bản rộng (đồ đạc trải dài như khung ngang) thay
        # vì phóng to ảnh khung dọc; ảnh chị tải lên thì phóng + cắt cho vừa
        from . import scene_art
        size, lay = (stage.world_w, stage.h), (stage.w, stage.h)
        try:
            if settings.get("bg_spec"):
                stage.bg = scene_art.render_spec(settings["bg_spec"], size, lay)
            for i, info in (scene_kinds or {}).items():
                if info.get("spec"):
                    stage.scene_bgs[i] = scene_art.render_spec(info["spec"], size, lay)
        except Exception as e:  # noqa: BLE001
            logger.warning("Không vẽ lại được bối cảnh rộng: %s", e)
    if settings.get("enable_rig") and settings.get("auto_seat", True):
        # văn phòng, lớp học, quán, phòng khách... có bàn ghế, nhân vật ngồi sẵn
        from . import furniture
        stage.seat_fallback = True
        for i, info in (scene_kinds or {}).items():
            seat = furniture.seat_type(info.get("kind"), info.get("desc") or "")
            if seat:
                stage.scene_seats[i] = seat
                if info.get("accent"):
                    stage.scene_colors[i] = tuple(info["accent"][:3])
    stage.title = settings.get("title_text") or script.title
    stage.subtitle_pos = "duoi" if settings.get("subtitle_position") == "duoi" else "tren"
    stage.subtitle_style = config.SUBTITLE_STYLES.get(
        settings.get("subtitle_style", "yellow"), config.SUBTITLE_STYLES["yellow"]
    )

    out_dir = pdir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4 = out_dir / "video.mp4"

    def vp(frac: float, msg: str) -> None:
        _say(progress, 0.55 + 0.4 * frac, msg)

    video.render_video(tl, chars, mp4, stage, settings, progress=vp)
    srt = video.write_srt(tl, out_dir / "phude.srt")

    _say(progress, 0.97, "đóng gói file rời")
    all_bgs = [Path(bg_path)] if bg_path else []
    all_bgs += [Path(p) for p in (scene_bgs or {}).values() if p]
    pack = _make_pack(pdir, tl, chars, all_bgs, mp4, srt, script,
                      size=(stage.w, stage.h))
    _say(progress, 1.0, "xong")

    return {
        "video": str(mp4),
        "srt": str(srt),
        "pack": str(pack),
        "duration": tl.total,
        "lines": len(tl.lines),
        "beats": len(tl.beats),
    }


def _make_pack(pdir: Path, tl: video.Timeline, chars: list[video.Character],
               bg_paths: list[Path], mp4: Path, srt: Path, script: Script,
               size: tuple[int, int] = (config.WIDTH, config.HEIGHT)) -> Path:
    """Bộ file rời để chỉnh trong CapCut + xuất file đầy đủ ra thư mục out."""
    out_dir = pdir / "out"

    # 1. Lưu kịch bản xác nhận
    kich_ban = out_dir / "kich_ban.txt"
    kich_ban.write_text(script.raw, encoding="utf-8")

    # 2. Lưu timeline JSON (mốc thời gian để dựng lại nhanh)
    timeline_json = out_dir / "timeline.json"
    tl_data = {
        "total": tl.total,
        "width": size[0],
        "height": size[1],
        "lines": [
            {
                "idx": ln.idx,
                "speaker": ln.speaker,
                "text": ln.text,
                "expression": ln.expression,
                "zoom": ln.zoom,
                "zoom_target": ln.zoom_target or "",
                "sfx": ln.sfx or "",
                "start": ln.start,
                "duration": ln.duration,
                "audio": str(ln.audio) if ln.audio else None,
                "scene": ln.scene,
                "words": [(w, s, e) for w, s, e in ln.words],
                "other_expr": dict(ln.other_expr),
            }
            for ln in tl.lines
        ],
        "beats": [
            {
                "idx": b.idx,
                "actor": b.actor,
                "expression": b.expression,
                "zoom": b.zoom,
                "sfx": b.sfx or "",
                "start": b.start,
                "duration": b.duration,
                "scene": b.scene,
            }
            for b in tl.beats
        ],
        "scenes": list(script.scenes),
        "scene_cast": [list(c) if c else None for c in script.scene_cast],
    }
    timeline_json.write_text(json.dumps(tl_data, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    # 3. Copy ảnh nhân vật và bối cảnh ra out/
    asset_dir = out_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    seen = set()
    for c in chars:
        for p in c.all_images():
            if p and Path(p).exists() and str(p) not in seen:
                seen.add(str(p))
                dst = asset_dir / Path(p).name
                if not dst.exists():
                    shutil.copy2(p, dst)
    for bg_path in bg_paths:
        if Path(bg_path).exists():
            dst = asset_dir / Path(bg_path).name
            if not dst.exists():
                shutil.copy2(bg_path, dst)

    # 3b. Giọng từng câu, đánh số theo thứ tự: 01_<tên>.wav, 02_<tên>.wav ...
    voice_dir = out_dir / "giong"
    voice_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for ln in tl.lines:
        if not (ln.audio and Path(ln.audio).exists()):
            continue
        n += 1
        safe_speaker = assets.config_slug(ln.speaker or "voice")
        dst = voice_dir / f"{n:02d}_{safe_speaker}.wav"
        if not dst.exists():
            shutil.copy2(ln.audio, dst)

    # 4. Đóng gói CapCut
    pack = out_dir / "capcut_pack.zip"
    zipped: set[str] = set()
    with zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as z:
        if mp4.exists():
            z.write(mp4, "video.mp4")
        if srt.exists():
            z.write(srt, "phude.srt")
        if kich_ban.exists():
            z.write(kich_ban, "kich_ban.txt")
        if timeline_json.exists():
            z.write(timeline_json, "timeline.json")
        for ln in tl.lines:
            if ln.audio and Path(ln.audio).exists():
                z.write(ln.audio, f"giong/{Path(ln.audio).name}")
        for c in chars:
            for p in c.all_images():
                if p and Path(p).exists():
                    arc = f"nhan_vat/{Path(p).name}"
                    if arc not in zipped:
                        zipped.add(arc)
                        z.write(p, arc)
        for bg_path in bg_paths:
            arc = f"boi_canh/{Path(bg_path).name}"
            if Path(bg_path).exists() and arc not in zipped:
                zipped.add(arc)
                z.write(bg_path, arc)
    return pack
