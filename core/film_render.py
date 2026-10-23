# -*- coding: utf-8 -*-
"""Dựng video chế độ Phim: đọc thoại (giọng riêng từng nhân vật) + vài câu người
kể, mô phỏng từng cảnh (core/film.py), ghép hình + tiếng + nhạc nền + phụ đề."""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from pathlib import Path

import numpy as np

from . import config, film, story, video
from .story_render import FPS, _card, _dim, _mix, _over, _subtitle

logger = logging.getLogger(__name__)

INTRO = 4.0
CHAPTER_CARD = 2.6
FADE = 0.5
OUTRO = 2.0


def scenes(st: dict) -> list[tuple[int, dict]]:
    return story.all_scenes(st)


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
    refs: dict = {}
    out = {}
    for k, (sc, i, b) in enumerate(todo):
        if b.get("t") == "line" and b.get("who") in chars:
            c = chars[b["who"]]
            cfg = c.get("voice") or {"instruct": story.default_voice(c.get("kit"))}
            key_v, speed = f"nv_{b['who']}", None
        else:
            cfg = st.get("narrator") or {}
            key_v, speed = "nguoi_ke", story.NARRATION_SPEED
        if key_v not in refs:
            refs[key_v] = story._voice_ref(pdir, key_v, language, cfg)
        ref = refs[key_v]
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
    rows, t = [], INTRO
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
            card = CHAPTER_CARD if k == 0 else 0.0
            scn = dict(sc, beats=beats)
            plan = film.simulate(scn, chars, W, T, durs, lead=film.LEAD_IN + card)
            rows.append({"sc": scn, "chapter": ci, "card": card, "start": t, "dur": plan["dur"],
                         "plan": plan})
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

    def shot(i):
        if i not in shots:
            for k in [k for k in shots if k < i - 1]:
                del shots[k]
            shots[i] = film.FilmShot(st, rows[i]["sc"], rows[i]["plan"], size, pdir, FPS)
        return shots[i]

    intro = _card(size, st.get("title") or "", st.get("author") or "")
    cards: dict = {}
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
            if t < row["start"]:
                frame = shot(0).frame(0.0)
                a = min(1.0, t / 0.8, (INTRO - t) / 0.8)
                frame = _over(_dim(frame, 0.55), intro, max(0.0, a))
            else:
                lt = t - row["start"]
                frame = shot(i).frame(min(lt, row["dur"]))
                nxt = row["start"] + row["dur"]
                if i + 1 < len(rows) and t > nxt - FADE:
                    frame = _mix(frame, shot(i + 1).frame(0.0), (t - (nxt - FADE)) / FADE)
                if row["card"] and film.LEAD_IN * 0.2 < lt < film.LEAD_IN * 0.2 + row["card"]:
                    ci = row["chapter"]
                    if ci not in cards:
                        cards[ci] = _card(size, st["chapters"][ci]["title"], f"Chương {ci + 1}")
                    u = lt - film.LEAD_IN * 0.2
                    frame = _over(frame, cards[ci], min(1.0, u / 0.4, (row["card"] - u) / 0.4))
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
