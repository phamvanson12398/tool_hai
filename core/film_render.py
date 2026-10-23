# -*- coding: utf-8 -*-
"""Dựng video chế độ Phim: đọc thoại (giọng riêng từng nhân vật) + vài câu người
kể, mô phỏng từng cảnh (core/film.py), ghép hình + tiếng + nhạc nền + phụ đề."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import subprocess
from pathlib import Path

import numpy as np

from . import config, film, story, video
from .story_render import FPS, _dim, _over, _subtitle

logger = logging.getLogger(__name__)

FADE = 0.35              # mờ ra đen rồi hiện cảnh mới (không hoà hình hai cảnh: hết "bóng ma")
OUTRO = 1.2
TAG_DUR = 2.5            # thẻ tên trên đầu khi nhân vật mới xuất hiện
VOICE_RMS = 0.09         # độ to chuẩn mọi câu thoại / lời kể
NIGHT = re.compile(r"\bđêm\b|\btối\b|khuya|trăng|đèn dầu")
DAY = re.compile(r"\bsáng\b|\btrưa\b|\bchiều\b|ban ngày|nắng")


def scenes(st: dict) -> list[tuple[int, dict]]:
    return story.all_scenes(st)


def f0_of(path) -> float | None:
    """Cao độ giọng trung bình (Hz) của một file: tự tương quan trên các đoạn có tiếng."""
    try:
        import soundfile as sf
        a, sr = sf.read(str(path), dtype="float32")
    except Exception:  # noqa: BLE001
        return None
    if a.ndim > 1:
        a = a.mean(axis=1)
    n, hop = int(sr * 0.04), int(sr * 0.01)
    if len(a) < n * 3:
        return None
    lo, hi = int(sr / 420), int(sr / 60)
    frames = [a[i:i + n] for i in range(0, len(a) - n, hop)]
    rms = np.array([float(np.sqrt(np.mean(f ** 2))) for f in frames])
    thr = 0.35 * float(np.percentile(rms, 90))
    f0s = []
    for f, r in zip(frames, rms):
        if r < thr:
            continue
        x = f - f.mean()
        spec = np.fft.rfft(x, 2 * n)
        ac = np.fft.irfft(spec * np.conj(spec))[:n]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        seg = ac[lo:hi]
        if not len(seg):
            continue
        best = float(seg.max())
        if best < 0.45:
            continue
        k = int(np.argmax(seg >= best * 0.9)) + lo         # chu kỳ ngắn nhất đủ mạnh (tránh nhầm quãng tám)
        f0s.append(sr / k)
    return float(np.median(f0s)) if len(f0s) >= 5 else None


def _f0_range(kit: dict | None) -> tuple[float, float]:
    k = kit or {}
    if k.get("age") == "child":
        return 180.0, 340.0
    if k.get("sex") == "female":
        return 160.0, 300.0
    return 75.0, 165.0                       # đàn ông: không được cao như giọng nữ / trẻ con


def narrator_cfg(st: dict) -> dict:
    """Người kể khác hẳn giọng nhân vật: chưa chọn giọng riêng thì dùng giọng nữ trầm
    ấm (truyện nhiều nhân vật nam) hoặc giọng nam (nhân vật chính là nữ)."""
    cfg = dict(st.get("narrator") or {})
    if cfg.get("voice"):
        return cfg
    chars = st.get("characters") or []
    kits = [c.get("kit") or {} for c in chars if (c.get("kit") or {}).get("species", "human") == "human"]
    own = (cfg.get("instruct") or "").strip()
    taken = {story.default_voice(k) for k in kits}
    if not own or own == story.DEFAULT_NARRATOR or own in taken:
        males = sum(1 for k in kits if k.get("sex") != "female")
        cfg["instruct"] = ("female, middle-aged, moderate pitch, warm storytelling voice"
                           if males >= len(kits) - males else "male, middle-aged, low pitch, calm storytelling voice")
    return cfg


def cast(st: dict, pdir: Path, language: str, ids: list, narr: bool = True) -> dict:
    """Giọng mẫu cho từng nhân vật + người kể, sao cho ai cũng nghe khác nhau: cao độ
    hợp tuổi / giới (đàn ông không ra giọng cao như nữ), các giọng không trùng cao độ.
    Giọng mẫu tạo từ mô tả mà không đạt thì thử giọng khác (tối đa 4 lần).
    Trả về {"nv_<id>" | "nguoi_ke": (cfg, ref)}."""
    chars = {c["id"]: c for c in st.get("characters") or []}
    todo = [(f"nv_{cid}", chars[cid].get("voice") or {"instruct": story.default_voice(chars[cid].get("kit"))},
             chars[cid].get("kit")) for cid in ids if cid in chars]
    # hai nhân vật cùng mô tả giọng (vd hai ông trung niên): đổi cao độ cho khác nhau
    seen: dict = {}
    for k, (key, cfg, kit) in enumerate(todo):
        ins = cfg.get("instruct") or ""
        if cfg.get("voice") or not ins:
            continue
        n = seen.get(ins, 0)
        seen[ins] = n + 1
        if n:
            alt = (["moderate pitch", "very low pitch", "slightly hoarse"] if "female" not in ins
                   else ["high pitch", "low pitch", "slightly husky"])[(n - 1) % 3]
            base = ", ".join(x for x in ins.split(", ") if "pitch" not in x)
            todo[k] = (key, dict(cfg, instruct=f"{base}, {alt}"), kit)
    if narr:
        todo.append(("nguoi_ke", narrator_cfg(st), None))
    # giọng chọn sẵn trong Thư viện / giọng nhân bản: giữ nguyên, chỉ để so
    out, used = {}, []
    for key, cfg, kit in sorted(todo, key=lambda r: not r[1].get("voice")):
        if cfg.get("voice"):
            ref = story._voice_ref(pdir, key, language, cfg)
            out[key] = (cfg, ref)
            f = f0_of(ref.get("ref")) if ref.get("ref") else None
            if f:
                used.append(f)
            continue
        lo, hi = _f0_range(kit) if kit else (75.0, 320.0)
        best = None
        for k in range(4):
            ref = story._voice_ref(pdir, key if k == 0 else f"{key}_{k}", language, cfg)
            if not ref:
                continue
            f = f0_of(ref["ref"]) if ref.get("ref") else None
            if f is None:
                score = 0.5
            else:
                score = max(0.0, lo - f) / lo + max(0.0, f - hi) / hi
                score += sum(max(0.0, 0.14 - abs(math.log2(f / u))) for u in used)
            if best is None or score < best[0]:
                best = (score, ref, f)
            if score <= 1e-6:
                break
        if best:
            out[key] = (cfg, best[1])
            if best[2]:
                used.append(best[2])
                logger.info("Giọng %s: %.0f Hz", key, best[2])
    return out


def level(a: np.ndarray, target: float = VOICE_RMS) -> np.ndarray:
    """Câu nào cũng to ngang nhau (RMS phần có tiếng), không vỡ tiếng."""
    peak = float(np.max(np.abs(a))) if len(a) else 0.0
    if peak < 1e-5:
        return a
    loud = a[np.abs(a) > peak * 0.08]
    rms = float(np.sqrt(np.mean(loud ** 2))) if len(loud) else peak
    a = a * min(8.0, target / max(rms, 1e-6))
    m = float(np.max(np.abs(a)))
    return (a * (0.97 / m) if m > 0.97 else a).astype(np.float32)


def sob(a: np.ndarray, sr: int) -> np.ndarray:
    """Câu nói lúc khóc: run run, nghẹn (rung âm lượng 5–6 lần/giây, nhỏ đi một chút)."""
    t = np.arange(len(a)) / sr
    trem = 1.0 - 0.38 * (0.5 + 0.5 * np.sin(2 * np.pi * 5.6 * t + 0.6 * np.sin(2 * np.pi * 0.7 * t)))
    return (a * trem * 0.92).astype(np.float32)


def voices(st: dict, pdir: Path, language: str = "vi", progress=None) -> dict:
    """Đọc lời người kể và thoại từng nhịp. Trả về {(id cảnh, chỉ số nhịp): file}.
    Câu không đổi thì dùng lại file cũ."""
    import soundfile as sf
    from . import voice
    adir = pdir / story.AUDIO_DIR
    adir.mkdir(parents=True, exist_ok=True)
    chars = {c["id"]: c for c in st.get("characters") or []}
    todo = [(sc, i, b) for _ci, sc in scenes(st) for i, b in enumerate(sc.get("beats") or [])
            if (b.get("t") in ("narr", "line") or (b.get("t") == "act" and b.get("text")))
            and (b.get("text") or "").strip()]
    speakers = {b["who"] for _sc, _i, b in todo if b.get("t") == "line" and b.get("who") in chars}
    narr = any(not (b.get("t") == "line" and b.get("who") in chars) for _sc, _i, b in todo)
    if progress and todo:
        progress(0.0, "chọn giọng riêng cho từng nhân vật")
    refs = cast(st, pdir, language, [c for c in chars if c in speakers], narr)
    out = {}
    for k, (sc, i, b) in enumerate(todo):
        if b.get("t") == "line" and b.get("who") in chars:
            key_v, speed = f"nv_{b['who']}", None
        else:
            key_v, speed = "nguoi_ke", story.NARRATION_SPEED
        cfg, ref = refs.get(key_v) or ({}, {})
        text = b["text"].strip()
        h = hashlib.md5(json.dumps([text, ref.get("ref"), cfg.get("instruct"), speed],
                                   ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        path = adir / f"film_{sc['id']}_{i}_{h}.wav"
        if not path.exists():
            if progress:
                progress(k / len(todo), f"đọc giọng {k + 1}/{len(todo)}")
            chunks, sr = [], config.SAMPLE_RATE
            for j, sent in enumerate(story._sentences(text)):
                wav, sr = voice.synthesize(sent, language,
                                           ref_wav=Path(ref["ref"]) if ref.get("ref") else None,
                                           ref_text=ref.get("ref_text"),
                                           instruct=None if ref.get("ref") else cfg.get("instruct"),
                                           speed=speed, seed=int(h[:6], 16) + j)
                chunks += [voice.trim_silence(np.asarray(wav, dtype=np.float32), sr),
                           np.zeros(int(sr * 0.25), dtype=np.float32)]
            full = np.concatenate(chunks[:-1]) if chunks else np.zeros(sr // 2, np.float32)
            for old in adir.glob(f"film_{sc['id']}_{i}_*.wav"):
                old.unlink(missing_ok=True)
            sf.write(str(path), full, sr)
        out[(sc["id"], i)] = path
    return out


def ambience(st: dict, scene: dict) -> tuple[str | None, bool]:
    """(tiếng nền, trong nhà?) theo địa điểm, giờ, thời tiết của cảnh."""
    from . import doodle_parts, scene_art, story_live
    places = {p["id"]: p for p in st.get("places") or []}
    place = places.get(scene.get("place"))
    kind = story_live.place_kind(place)
    custom = doodle_parts.get(kind)
    indoor = (custom.get("indoor", True) if custom else kind not in scene_art.OUTDOOR)
    night = story_live.scene_time(scene, place) == "dem"
    if scene.get("weather") == "rain":
        return "rain", indoor
    if night:
        return "crickets", indoor
    return "birds", indoor


def scene_time(ch: dict, sc: dict) -> str | None:
    """Ngày / đêm của cảnh: tên chương "Đêm tối" thì cảnh trong chương là ban đêm
    (trừ cảnh lời kể nói rõ sáng / trưa / chiều)."""
    narr = " ".join(b.get("text") or "" for b in sc.get("beats") or [] if b.get("t") == "narr").lower()
    title = " ".join([ch.get("title") or "", ch.get("summary") or ""]).lower()
    if NIGHT.search(narr):
        return "dem"
    if DAY.search(narr):
        return "ngay"
    if NIGHT.search(ch.get("title", "").lower()):
        return "dem"
    if sc.get("time") in ("ngay", "dem"):
        return sc["time"]
    return "dem" if NIGHT.search(title) and not DAY.search(title) else None


def name_tags(rows: list[dict]) -> dict:
    """{chỉ số cảnh: {id: (t0, t1)}}: thẻ tên lần đầu mỗi nhân vật lên hình."""
    seen, out = set(), {}
    for ri, row in enumerate(rows):
        plan = row["plan"]
        first = plan["beats"][0]["t0"] if plan["beats"] else 0.5
        for cid, tr in plan["tracks"].items():
            if cid in seen:
                continue
            t0 = None
            if 0 <= tr.x_at(first) <= plan["W"]:
                t0 = first
            else:
                ins = [m[1] for m in tr.moves if 0 <= m[3] <= plan["W"]]
                t0 = min(ins) if ins else None
            if t0 is None:
                continue
            sp = [s[0] for s in tr.speak if s[0] >= t0 - 0.01]
            t0 = min(sp) if sp and min(sp) - t0 < 6 else t0
            seen.add(cid)
            out.setdefault(ri, {})[cid] = (t0, t0 + TAG_DUR)
    return out


_VIG: dict = {}


def hook_look(frame: np.ndarray) -> np.ndarray:
    """Cảnh móc câu: nhạt màu, tối viền như hé lộ trước, để người xem biết là đoạn trích."""
    H, W = frame.shape[:2]
    if (W, H) not in _VIG:
        y, x = np.ogrid[:H, :W]
        r = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
        _VIG[(W, H)] = np.clip(1.08 - 0.32 * r ** 2, 0.55, 1.0).astype(np.float32)[..., None]
    f = frame.astype(np.float32)
    g = f.mean(axis=2, keepdims=True)
    f = (f * 0.7 + g * 0.3) * np.array([1.03, 1.0, 0.94], np.float32)
    return np.clip(f * _VIG[(W, H)], 0, 255).astype(np.uint8)


def plan_all(st: dict, size, audio: dict) -> list[dict]:
    """Mốc thời gian từng cảnh (đã mô phỏng)."""
    import soundfile as sf
    W, H = size
    T = film.char_T(size)
    chars = {c["id"]: c for c in st.get("characters") or []}
    for c in chars.values():
        if not c.get("kit"):
            from . import doodle
            c["kit"] = doodle.kit_from_look(c.get("name", ""), c.get("look", ""))
    allsc = [sc for ch in st.get("chapters") or [] for sc in ch.get("scenes") or []]
    hook = len(allsc) > 1 and bool(allsc[0].get("hook"))
    rows, t = [], 0.0                         # vào thẳng cảnh đầu, không có chữ giới thiệu
    for ci, ch in enumerate(st.get("chapters") or []):
        for k, sc in enumerate(ch.get("scenes") or []):
            durs, beats = {}, []
            for i, b in enumerate(sc.get("beats") or []):
                b = dict(b)
                p = audio.get((sc["id"], i))
                if p and Path(p).exists():
                    durs[i] = sf.info(str(p)).duration
                    b["path"] = str(p)
                beats.append(b)
            scn = dict(sc, beats=beats)
            scn["time"] = scene_time(ch, sc)
            amb, indoor = ambience(st, scn)
            plan = film.simulate(scn, chars, W, T, durs, lead=film.LEAD_IN, indoor=indoor)   # thẻ chương ở trên, diễn luôn
            rows.append({"sc": scn, "chapter": ci, "hook": hook and not rows, "start": t, "dur": plan["dur"],
                         "plan": plan, "ambience": amb})
            t += plan["dur"]
    return rows


def render(st: dict, pdir: Path, fmt: str, settings: dict, audio: dict, progress=None) -> Path:
    import soundfile as sf

    def say(f, m):
        if progress:
            progress(f, m)

    size = config.frame_size(fmt)
    W, H = size
    rows = plan_all(st, size, audio)
    if not rows:
        raise RuntimeError("Chưa có cảnh nào để dựng.")
    total = rows[-1]["start"] + rows[-1]["dur"] + OUTRO
    out_dir = pdir / "out"
    tmp = out_dir / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    chars = {c["id"]: c for c in st.get("characters") or []}

    # ---- âm thanh
    say(0.02, "ghép giọng")
    sr = config.SAMPLE_RATE
    track = np.zeros(int(total * sr) + sr, dtype=np.float32)
    subs_plan = []                    # (t0, t1, chữ)
    for row in rows:
        for b in row["plan"]["beats"]:
            p = b.get("path")
            if not p or not Path(p).exists():
                continue
            at = row["start"] + b["t0"] + (0.15 if b.get("t") == "line" else 0.1)
            a, asr = sf.read(p, dtype="float32")
            if a.ndim > 1:
                a = a.mean(axis=1)
            if asr != sr:
                a = np.interp(np.linspace(0, len(a), int(len(a) * sr / asr), endpoint=False),
                              np.arange(len(a)), a).astype(np.float32)
            a = level(a)
            if b.get("t") == "line" and b.get("act") == "cry":
                a = sob(a, sr)
            i0 = int(at * sr)
            track[i0:i0 + len(a)] += a[: max(0, len(track) - i0)]
            dur = len(a) / sr
            if b.get("t") == "line":
                name = (chars.get(b.get("who")) or {}).get("name") or b.get("who")
                subs_plan.append((at, at + dur + 0.2, f"{name}: {b['text']}"))
            else:                                  # lời kể: chia theo câu
                sents = story._sentences(b.get("text") or "")
                tot = sum(len(s) for s in sents) or 1
                acc = 0
                for s in sents:
                    a0 = at + acc / tot * dur
                    acc += len(s)
                    subs_plan.append((a0, at + acc / tot * dur, s))
    # tiếng động theo động tác + tiếng nền từng cảnh
    from . import film_sfx
    gain = float(settings.get("sfx_volume") if settings.get("sfx_volume") is not None else 0.8)
    if gain > 0:
        say(0.03, "thêm tiếng động")
        for row in rows:
            for at, name, vol in row["plan"].get("sfx") or []:
                film_sfx.put(track, name, row["start"] + at, vol * gain)
        if rows[0].get("hook") and len(rows) > 1:          # hết móc câu: vút về đầu chuyện
            film_sfx.put(track, "swoosh", rows[1]["start"] - 0.25, 0.5 * gain)
        # không lồng tiếng nền (chim, dế, mưa): chị muốn bỏ
    wav = tmp / "film_audio.wav"
    sf.write(str(wav), np.clip(track, -1, 1), sr)

    # ---- hình
    ff = video._ffmpeg_path()
    raw = tmp / "film_video_only.mp4"
    proc = subprocess.Popen(
        [ff, "-y", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{W}x{H}",
         "-framerate", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "20",
         "-pix_fmt", "yuv420p", "-preset", "veryfast", str(raw)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shots: dict = {}

    tags = name_tags(rows)

    def shot(i):
        if i not in shots:
            for k in [k for k in shots if k < i - 1]:
                del shots[k]
            shots[i] = film.FilmShot(st, rows[i]["sc"], rows[i]["plan"], size, pdir, FPS)
            shots[i].tags = tags.get(i, {})
        return shots[i]

    sub_cache: dict = {}
    sub_on = bool(st.get("subtitles"))
    n_frames = int(total * FPS)
    i = 0
    si = 0
    try:
        for fi in range(n_frames):
            t = fi / FPS
            while i < len(rows) - 1 and t >= rows[i + 1]["start"]:
                i += 1
            row = rows[i]
            lt = t - row["start"]
            frame = shot(i).frame(min(lt, row["dur"]))
            nxt = row["start"] + row["dur"]
            if i + 1 < len(rows) and t > nxt - FADE:             # mờ ra đen ...
                frame = _dim(frame, max(0.0, (nxt - t) / FADE))
            elif lt < FADE:                                      # ... rồi hiện cảnh mới
                frame = _dim(frame, max(0.0, lt / FADE))
            if row.get("hook"):                                  # móc câu: màu như ký ức
                frame = hook_look(frame)
            if sub_on:
                while si < len(subs_plan) - 1 and subs_plan[si][1] < t:
                    si += 1
                for k in range(max(0, si - 1), min(len(subs_plan), si + 2)):
                    a0, a1, txt = subs_plan[k]
                    if a0 <= t < a1:
                        if txt not in sub_cache:
                            if len(sub_cache) > 10:
                                sub_cache.clear()
                            sub_cache[txt] = _subtitle(size, txt)
                        frame = _over(frame, sub_cache[txt])
                        break
            end = total - OUTRO
            if t > end:
                frame = _dim(frame, max(0.0, 1 - (t - end) / OUTRO))
            proc.stdin.write(np.ascontiguousarray(frame).tobytes())
            if fi % max(1, n_frames // 60) == 0:
                say(0.05 + 0.85 * fi / n_frames, f"dựng hình {int(t // 60)}:{int(t % 60):02d} / "
                                                  f"{int(total // 60)}:{int(total % 60):02d}")
    finally:
        proc.stdin.close()
        proc.wait()

    say(0.93, "ghép âm thanh")
    mp4 = out_dir / "video.mp4"
    bgm = settings.get("bgm_file")
    vol = float(settings.get("bgm_volume") or 0)
    if bgm and Path(bgm).exists() and vol > 0:
        cmd = [ff, "-y", "-i", str(raw), "-i", str(wav), "-stream_loop", "-1", "-i", str(bgm),
               "-filter_complex",
               f"[2:a]volume={vol * 0.3:.3f},afade=t=out:st={max(0, total - 4):.2f}:d=4[b];"
               f"[1:a][b]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]",
               "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-shortest", str(mp4)]
    else:
        cmd = [ff, "-y", "-i", str(raw), "-i", str(wav), "-map", "0:v", "-map", "1:a",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg ghép tiếng lỗi: " + (r.stderr or "")[-400:])
    say(1.0, "xong")
    return mp4
