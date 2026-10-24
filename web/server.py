# -*- coding: utf-8 -*-
"""Web server chạy trên máy chị: http://127.0.0.1:8766

Ba màn hình: Tập mới / Thư viện / Cài đặt. Mọi việc nặng (tạo giọng, dựng
video, gọi Claude) chạy ở luồng nền để giao diện không bị treo.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows: console mặc định dùng cp1252, in tiếng Hàn ra ký tự hỏng.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

from flask import (Flask, jsonify, request, send_file,  # noqa: E402
                   send_from_directory)

from core import assets, character_kit, claude_cli, config, pipeline  # noqa: E402
from core import capcut_export, photo_rig, rig as core_rig, scene_art, style_lib  # noqa: E402
from core.comedy_lib import (COMEDY_KINDS, MARKETS, VALID_EXPRESSIONS,  # noqa: E402
                             VALID_SFX)
from core.gestures import breathe_angles  # noqa: E402
from core.script_parser import estimate_duration, parse_script  # noqa: E402
from core import comedy_kinds_lib  # noqa: E402
from core import tts_plugin  # noqa: E402

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024   # 512 MB

# trạng thái từng project đang dựng
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


# ----------------------------------------------------------------- tiện ích

def _err(msg: str, code: int = 400):
    return jsonify({"error": str(msg)}), code


def _project_file(pid: str) -> Path:
    return config.project_dir(pid) / "project.json"


def _load_project(pid: str) -> dict:
    if not (config.PROJECTS / pid / "project.json").exists():   # đừng tạo lại thư mục tập đã xoá
        raise FileNotFoundError(f"Không thấy tập '{pid}'")
    p = _project_file(pid)
    if not p.exists():
        raise FileNotFoundError(f"Không thấy tập '{pid}'")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------- nhiều bối cảnh
# Bối cảnh chung của tập ở assets.background (như cũ); bối cảnh từng cảnh
# ('## canh: ...') ở assets.backgrounds, khoá theo mô tả cảnh (viết thường),
# nên cảnh lặp lại dùng chung một ảnh.

def _scene_key(desc: str) -> str:
    return (desc or "").strip().lower()


def _scene_bg(data: dict, desc: str) -> dict | None:
    """Bản ghi ảnh nền của một cảnh (None nếu cảnh chưa có ảnh riêng)."""
    if not _scene_key(desc):
        return data["assets"].get("background")
    return (data["assets"].get("backgrounds") or {}).get(_scene_key(desc))


def _set_scene_bg(data: dict, desc: str, rec: dict) -> None:
    rec["scene"] = desc
    if not _scene_key(desc):
        data["assets"]["background"] = rec
    else:
        data["assets"].setdefault("backgrounds", {})[_scene_key(desc)] = rec


def _scene_bg_paths(data: dict, s) -> dict[int, Path]:
    """{chỉ số cảnh: ảnh nền} cho các cảnh có ảnh riêng."""
    out: dict[int, Path] = {}
    for i, desc in enumerate(s.scenes):
        rec = _scene_bg(data, desc) if _scene_key(desc) else None
        img = (rec or {}).get("image")
        if img and Path(img).exists():
            out[i] = Path(img)
    return out


def _scene_kinds(data: dict, s) -> dict[int, dict]:
    """{chỉ số cảnh: {"kind": mẫu bối cảnh, "accent": màu}} để vẽ bàn ghế và
    cho nhân vật ngồi đúng chỗ. Ảnh chị tự tải lên thì đoán từ mô tả cảnh."""
    from core import furniture
    general = data["assets"].get("background") or {}
    out: dict[int, dict] = {}
    for i, desc in enumerate(s.scenes or [""]):
        rec = (_scene_bg(data, desc) if _scene_key(desc) else None) or {}
        own = bool(rec.get("image")) and _scene_key(desc)
        if not rec.get("image") and not _scene_key(desc):
            rec = general
        kind = rec.get("kind") or furniture.kind_from_desc(desc) \
            or furniture.kind_from_desc(rec.get("desc") or "")
        if not kind and not rec.get("image"):
            kind = general.get("kind") or furniture.kind_from_desc(general.get("desc") or "")
        if kind or desc:
            out[i] = {"kind": kind, "desc": desc,
                      "accent": (rec.get("spec") or {}).get("accent"),
                      # bối cảnh AI vẽ: vẽ lại được bản rộng cho sân khấu lia ngang
                      "spec": rec.get("spec") if own else None}
    return out


def _short_err(e: Exception, n: int = 220) -> str:
    """Lỗi AI rút gọn cho thông báo (AI có thể trả cả đoạn văn dài)."""
    t = " ".join(str(e).split())
    return t if len(t) <= n else t[:n] + "…"


def _draw_scene_bg(data: dict, pdir: Path, desc: str, hint: str = "") -> tuple[dict, str | None]:
    """Claude chọn mẫu + màu cho cảnh, tool vẽ và lưu. Trả về (bản ghi, cảnh báo)."""
    from core import scene_art
    warn = None
    try:
        bg = claude_cli.design_background(data.get("script", ""),
                                          data.get("language", "ko"),
                                          desc or hint)
    except Exception as e:  # noqa: BLE001
        warn = f"AI chọn bối cảnh '{desc or 'chung'}' lỗi ({_short_err(e)}); dùng mẫu mặc định."
        bg = {}
    if not bg:
        bg = {"name": desc or "boi_canh", "kind": "phong_khach", "time": "ngay"}
    bg["art"] = _bg_style(data)
    size = config.frame_size(data.get("format"))
    slug = assets.config_slug(desc or "chung") or "chung"
    out = scene_art.save_scene(bg, pdir / "assets" / f"bg_{slug}_{uuid.uuid4().hex[:4]}.png",
                               size=size)
    rec = assets.save_background(out, bg.get("name") or desc or "boi_canh")
    rec["desc"] = bg.get("desc", desc)
    rec["kind"] = bg.get("kind")
    rec["time"] = bg.get("time")
    rec["spec"] = bg
    rec["size"] = list(size)
    return rec, warn


def _bg_style(data: dict) -> str:
    from core import scene_art
    st = data.get("bg_style") or config.load_settings().get("bg_style") or "flat"
    return st if st in scene_art.ART_STYLES else "flat"


def _char_style(data: dict, language: str) -> str:
    """Kiểu nhân vật của tập (chọn ở trang Tập mới), không có thì theo Cài đặt."""
    style = data.get("char_style") or config.load_settings().get("char_style") or "auto"
    if style not in character_kit.STYLES:      # "auto": theo ngôn ngữ của tập
        style = "khand" if language == "ko" else "gray"   # Anh, Việt -> người xám TikTok
    return style


def _build_kit_char(pdir: Path, s, name: str, spec_d: dict, style: str,
                    side: str) -> dict:
    """Ghép một nhân vật bằng bộ ghép, trả về bản ghi nhân vật của tập."""
    spec_d = dict(spec_d)
    spec_d["name"] = name
    spec_d["style"] = style
    spec = character_kit.CharSpec.from_dict(spec_d)
    exprs = sorted({b.expression for b in s.beats if b.speaker == name} | {"neutral"})
    sheet = character_kit.build_sheet(
        spec, pdir / "assets" / "kit" / assets.config_slug(name), exprs
    )
    first = sheet.get("neutral") or next(iter(sheet.values()))
    return {
        "name": name,
        "side": side,
        "mode": "kit",
        "spec": spec.to_dict(),
        "images": sheet,
        "expressions": list(sheet),
        "image": first.get("dong"),
        "mouth_open": first.get("mo"),
        "mouth_closed": first.get("dong"),
    }


def _project_language(data: dict, s) -> str:
    # kịch bản có '# ngon_ngu:' thì theo kịch bản (chọn kiểu nhân vật Hàn/Mỹ)
    return s.language if "ngon_ngu" in (data.get("script") or "") \
        else data.get("language", "ko")


def _restyle_kit_chars(data: dict, pdir: Path) -> list[str]:
    """Đổi kiểu nhân vật của tập: ghép lại các nhân vật bộ ghép (giữ tóc, áo...)."""
    s = parse_script(data.get("script", ""))
    style = _char_style(data, _project_language(data, s))
    done = []
    chars = data["assets"].get("characters") or []
    for i, c in enumerate(chars):
        if c.get("mode") != "kit" or (c.get("spec") or {}).get("style") == style:
            continue
        rec = _build_kit_char(pdir, s, c["name"], c.get("spec") or {}, style,
                              c.get("side") or "giua")
        for k in ("ref_image", "ref_note"):
            if c.get(k):
                rec[k] = c[k]
        chars[i] = rec
        done.append(c["name"])
    return done


def _fit_scene_bgs(data: dict, pdir: Path) -> bool:
    """Đổi khung (9:16 <-> 16:9...) hoặc phong cách vẽ thì vẽ lại các nền do
    tool vẽ (ảnh tải lên thì để nguyên, lúc dựng sẽ cắt cho vừa).
    Trả về True nếu có nền được vẽ lại."""
    from core import scene_art
    size = list(config.frame_size(data.get("format")))
    art = _bg_style(data)
    recs = [data["assets"].get("background")]
    recs += list((data["assets"].get("backgrounds") or {}).values())
    changed = False
    for rec in recs:
        if not rec or not rec.get("kind"):
            continue
        spec = rec.get("spec") or {"kind": rec.get("kind"), "time": rec.get("time"),
                                   "name": rec.get("name", "")}
        if rec.get("size") == size and Path(rec.get("image") or "").exists() \
                and (spec.get("art") or "flat") == art:
            continue
        spec["art"] = art
        rec["spec"] = spec
        slug = assets.config_slug(rec.get("scene") or rec.get("name") or "chung") or "chung"
        out = scene_art.save_scene(
            spec, pdir / "assets" / f"bg_{slug}_{size[0]}x{size[1]}_{uuid.uuid4().hex[:4]}.png",
            size=tuple(size))
        rec["image"] = str(out)
        rec["size"] = size
        changed = True
    return changed


def _save_project(pid: str, data: dict) -> None:
    _project_file(pid).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _status(pid: str) -> dict:
    with JOBS_LOCK:
        return dict(JOBS.get(pid) or {"state": "draft", "progress": 0.0,
                                      "message": "", "log": []})


def _set_status(pid: str, **kw) -> None:
    with JOBS_LOCK:
        cur = JOBS.setdefault(pid, {"state": "draft", "progress": 0.0,
                                    "message": "", "log": []})
        msg = kw.get("message")
        if msg:
            cur.setdefault("log", []).append(msg)
            cur["log"] = cur["log"][-60:]
        cur.update(kw)


def _history() -> list[dict]:
    p = config.DATA / "history.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return _dedupe_history(d) if isinstance(d, list) else []
        except Exception:
            return []
    return []


def _dedupe_history(items: list[dict]) -> list[dict]:
    """Gộp các bản ghi trùng tập (bản cũ bị ghi lặp khi trang tải lại liên
    tục): giữ một bản mỗi tập, đủ trường nhất, ở vị trí lần ghi cuối."""
    merged: dict[str, dict] = {}
    order: list[str] = []
    out_noid: list[dict] = []
    for h in items:
        if not isinstance(h, dict):
            continue
        pid = h.get("id")
        if not pid:
            out_noid.append(h)
            continue
        cur = merged.setdefault(pid, {})
        for k, v in h.items():
            if v or k not in cur:
                cur[k] = v
        if pid in order:
            order.remove(pid)
        order.append(pid)
    return out_noid + [merged[i] for i in order]


def _save_history(items: list[dict]) -> None:
    (config.DATA / "history.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ------------------------------------------------------------------- trang

@app.route("/")
def index():
    return send_from_directory(app.template_folder, "index.html")


@app.route("/static/<path:name>")
def static_files(name):
    return send_from_directory(app.static_folder, name)


# -------------------------------------------------------------------- meta

@app.get("/api/meta")
def api_meta():
    return jsonify({
        "claude_calls": claude_cli.call_count(),
        "ai_calls": claude_cli.call_counts(),
        "ai_tasks": [{"id": k, "label": v[0], "default": v[1],
                      "engines": claude_cli.engines_for_task(k)}
                     for k, v in claude_cli.AI_TASKS.items()],
        "ai_engines": [{"id": k, "label": v} for k, v in claude_cli.ENGINES.items()],
        "languages": [{"code": k, "label": v["label"]}
                      for k, v in config.LANGUAGES.items()],
        "expressions": sorted(VALID_EXPRESSIONS),
        "sfx": sorted(VALID_SFX),
        "comedy_kinds": {
            lang: [{"id": kid, "name": nm, "how": how}
                   for kid, nm, how in
                   [(k["id"], k["name"], k["how"])
                    for k in comedy_kinds_lib.list_kinds(lang)]]
            for lang in config.LANGUAGES
        },
        "markets": {k: {"label": v["label"],
                        "trend_sources": v["trend_sources"],
                        "avoid": v["avoid"]}
                    for k, v in MARKETS.items()},
        "subtitle_styles": list(config.SUBTITLE_STYLES),
        "target_duration": list(config.TARGET_DURATION),
        "character_kit": character_kit.options(),
        "bg_styles": [[k, v] for k, v in scene_art.ART_STYLES.items()],  # giữ thứ tự
        "tts_engines": tts_plugin.list_engines(),
    })


@app.get("/api/claude-calls")
def api_claude_calls():
    """Số lần đã gọi Claude trong phiên làm việc của server."""
    return jsonify({"count": claude_cli.call_count(),
                    "counts": claude_cli.call_counts()})


@app.get("/api/settings")
def api_get_settings():
    return jsonify(config.load_settings())


@app.route("/api/settings", methods=["POST", "PUT"])
def api_set_settings():
    cur = config.load_settings()
    if request.files:
        f = request.files.get("bgm_file")
        if f and f.filename:
            dest = config.DATA / "bgm"
            dest.mkdir(parents=True, exist_ok=True)
            p = dest / f.filename
            f.save(str(p))
            cur["bgm_file"] = str(p)
        for k, v in request.form.items():
            cur[k] = _coerce(k, v)
    else:
        body = request.get_json(silent=True) or {}
        for k, v in body.items():
            cur[k] = v
    config.save_settings(cur)
    from core import agy_cli
    agy_cli.reset()           # đổi cài đặt / vừa đăng nhập: thử lại Antigravity
    return jsonify(cur)


@app.get("/api/check-system")
def api_check_system():
    """Kiểm tra: GPU NVIDIA, ffmpeg, Claude CLI, Antigravity CLI."""
    import subprocess
    import os

    results = []
    settings = config.load_settings()

    # 1. GPU NVIDIA
    try:
        import torch
        has_cuda = torch.cuda.is_available()
        if has_cuda:
            gpu_name = torch.cuda.get_device_name(0)
            results.append({
                "item": "GPU NVIDIA",
                "status": "ok",
                "message": f"Có — {gpu_name}"
            })
        else:
            results.append({
                "item": "GPU NVIDIA",
                "status": "warn",
                "message": "Không có hoặc chưa cài driver CUDA. OmniVoice sẽ chạy chậm."
            })
    except Exception as e:
        results.append({
            "item": "GPU NVIDIA",
            "status": "error",
            "message": f"Không kiểm tra được: {e}"
        })

    # 2. ffmpeg
    ffmpeg_bin = (settings.get("ffmpeg_bin") or "").strip() or "ffmpeg"
    try:
        proc = subprocess.run(
            [ffmpeg_bin, "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if proc.returncode == 0:
            first_line = (proc.stdout or "").split("\n")[0]
            results.append({
                "item": "ffmpeg",
                "status": "ok",
                "message": f"Có — {first_line[:80]}"
            })
        else:
            results.append({
                "item": "ffmpeg",
                "status": "error",
                "message": f"Lỗi khi chạy: mã {proc.returncode}"
            })
    except FileNotFoundError:
        results.append({
            "item": "ffmpeg",
            "status": "error",
            "message": f"Không tìm thấy lệnh '{ffmpeg_bin}'. Cần cài ffmpeg."
        })
    except Exception as e:
        results.append({
            "item": "ffmpeg",
            "status": "error",
            "message": f"Không kiểm tra được: {e}"
        })

    # 3. Claude CLI
    claude_bin = (settings.get("claude_bin") or "").strip() or os.environ.get("CLAUDE_BIN", "claude")
    try:
        proc = subprocess.run(
            [claude_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if proc.returncode == 0:
            ver = (proc.stdout or "").strip()
            results.append({
                "item": "Claude CLI",
                "status": "ok",
                "message": f"Có — {ver[:80]}"
            })
        else:
            results.append({
                "item": "Claude CLI",
                "status": "warn",
                "message": "Lệnh chạy nhưng không trả về phiên bản. Có thể chưa đăng nhập."
            })
    except FileNotFoundError:
        results.append({
            "item": "Claude CLI",
            "status": "error",
            "message": f"Không tìm thấy lệnh '{claude_bin}'. Cần cài Claude Code CLI."
        })
    except Exception as e:
        results.append({
            "item": "Claude CLI",
            "status": "error",
            "message": f"Không kiểm tra được: {e}"
        })

    # 4. Antigravity CLI (cho các việc chọn Antigravity ở mục Trợ lý AI)
    from core import agy_cli
    ok, msg = agy_cli.version()
    uses = [v[0] for k, v in claude_cli.AI_TASKS.items()
            if claude_cli.engine_for(k) == "agy"]
    results.append({
        "item": "Antigravity CLI (agy)",
        "status": "ok" if ok else ("error" if uses else "warn"),
        "message": (f"Có — {msg}" if ok else
                    msg + (" (đang được chọn cho: " + ", ".join(uses) +
                           ("; tạm thời tool sẽ dùng Claude thay)"
                            if settings.get("ai_fallback", True) else ")")
                           if uses else "")),
    })

    # 5. Vẽ bối cảnh 3D (Truyện kể) — không bắt buộc
    from core import bg3d
    ok, msg = bg3d.check() if bg3d.installed() else (False, "Chưa cài (không bắt buộc) — "
                                                            "muốn bối cảnh 3D thì chạy cai_3d.bat")
    results.append({"item": "Vẽ bối cảnh 3D (Stable Diffusion)",
                    "status": "ok" if ok else "warn",
                    "message": ("Có — " + msg) if ok else msg})

    return jsonify({"checks": results})


def _coerce(key: str, val: str):
    if key in ("gap_between_lines", "bgm_volume", "sfx_volume"):
        try:
            return float(val)
        except ValueError:
            return val
    if val in ("true", "false"):
        return val == "true"
    return val


@app.post("/api/parse-script")
def api_parse_script():
    body = request.get_json(silent=True) or {}
    s = parse_script(body.get("script", ""))
    return jsonify({
        "errors": s.errors,
        "warnings": s.warnings,
        "title": s.title,
        "language": s.language,
        "cast": s.cast,
        "sides": s.sides,
        "beats": [
            {"kind": b.kind, "speaker": b.speaker, "expression": b.expression,
             "zoom": b.zoom, "sfx": b.sfx, "text": b.text,
             "duration": b.duration, "line_no": b.line_no,
             "pause": b.pause, "zoom_target": b.zoom_target,
             "other_expr": b.other_expr, "translation": b.translation,
             "scene": b.scene}
            for b in s.beats
        ],
        "scenes": s.scenes,
        "scene_cast": s.scene_cast,
        "estimate_duration": round(estimate_duration(s), 1),
    })


# ----------------------------------------------------------------- thư viện

@app.get("/api/library")
def api_library():
    return jsonify({
        "characters": assets.list_characters(),
        "backgrounds": assets.list_backgrounds(),
        "voices": assets.list_voices(),
        "sfx": assets.list_sfx(),
    })


# ---------------------------------------------- thư viện: đổi tên / xoá

@app.post("/api/library/character/<path:name>/rename")
def api_lib_character_rename(name):
    body = request.get_json(silent=True) or {}
    try:
        rec = assets.rename_character(name, (body.get("name") or "").strip())
    except ValueError as e:
        return _err(str(e))
    return jsonify(rec)


@app.delete("/api/library/character/<path:name>")
def api_lib_character_delete(name):
    if not assets.delete_character(name):
        return _err(f"Không có nhân vật '{name}' trong thư viện.", 404)
    return jsonify({"ok": True})


@app.post("/api/library/background/<path:bid>/rename")
def api_lib_background_rename(bid):
    body = request.get_json(silent=True) or {}
    try:
        rec = assets.rename_background(bid, (body.get("name") or "").strip())
    except ValueError as e:
        return _err(str(e))
    return jsonify(rec)


@app.delete("/api/library/background/<path:bid>")
def api_lib_background_delete(bid):
    if not assets.delete_background(bid):
        return _err("Không có bối cảnh này trong thư viện.", 404)
    return jsonify({"ok": True})


@app.post("/api/library/voice/<path:name>/rename")
def api_lib_voice_rename(name):
    body = request.get_json(silent=True) or {}
    try:
        rec = assets.rename_voice(name, (body.get("name") or "").strip())
    except ValueError as e:
        return _err(str(e))
    return jsonify(rec)


@app.delete("/api/library/voice/<path:name>")
def api_lib_voice_delete(name):
    if not assets.delete_voice(name):
        return _err(f"Không có giọng mẫu '{name}' trong thư viện.", 404)
    return jsonify({"ok": True})


@app.post("/api/library/sfx/<path:name>/rename")
def api_lib_sfx_rename(name):
    body = request.get_json(silent=True) or {}
    try:
        rec = assets.rename_sfx(name, (body.get("name") or "").strip())
    except ValueError as e:
        return _err(str(e))
    return jsonify(rec)


@app.delete("/api/library/sfx/<path:name>")
def api_lib_sfx_delete(name):
    if not assets.delete_sfx(name):
        return _err(f"Không có tiếng động '{name}'.", 404)
    return jsonify({"ok": True})


@app.get("/api/library/sfx/<path:name>/audio")
def api_lib_sfx_audio(name):
    p = config.SFX_DIR / f"{name}.wav"
    if not p.exists():
        return _err("Không có tiếng động này.", 404)
    return send_file(str(p), mimetype="audio/wav")


# ------------------------------------------- thư viện kiểu hài (chỉnh sửa)

@app.get("/api/comedy-kinds")
def api_comedy_kinds_get():
    lang = request.args.get("lang", "en")
    return jsonify({"lang": lang, "kinds": comedy_kinds_lib.list_kinds(lang)})


@app.post("/api/comedy-kinds")
def api_comedy_kinds_post():
    body = request.get_json(silent=True) or {}
    lang = body.get("lang") or "en"
    try:
        rec = comedy_kinds_lib.upsert_kind(
            lang, (body.get("id") or "").strip(),
            (body.get("name") or "").strip(), (body.get("how") or "").strip(),
        )
    except ValueError as e:
        return _err(str(e))
    return jsonify(rec)


@app.delete("/api/comedy-kinds/<path:kind_id>")
def api_comedy_kinds_delete(kind_id):
    lang = request.args.get("lang", "en")
    try:
        ok = comedy_kinds_lib.delete_kind(lang, kind_id)
    except ValueError as e:
        return _err(str(e))
    if not ok:
        return _err("Không có kiểu hài này.", 404)
    return jsonify({"ok": True})



@app.post("/api/library/character")
def api_lib_character():
    name = (request.form.get("name") or "").strip()
    side = (request.form.get("side") or "center").strip()
    files = request.files.getlist("files")
    if not files:
        return _err("Chưa chọn ảnh nào.")

    tmp = config.DATA / "tmp" / uuid.uuid4().hex[:8]
    tmp.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for f in files:
        if not f.filename:
            continue
        p = tmp / Path(f.filename).name
        f.save(str(p))
        if p.suffix.lower() == ".zip":
            paths += assets.extract_zip(p, tmp)
        else:
            paths.append(p)

    parsed = assets.parse_character_files(paths)
    if not name:
        if len(parsed["characters"]) == 1:
            name = next(iter(parsed["characters"]))
        else:
            return _err("Nhiều nhân vật trong lần tải này — cần ghi rõ tên.")
    try:
        rec = assets.save_character(name, side, paths, to_library=False)
    except ValueError as e:
        return _err(str(e))
    rec["warnings"] = parsed["warnings"]
    return jsonify(rec)


@app.post("/api/library/character/<name>/save")
def api_lib_character_save(name):
    idx_path = config.LIBRARY / "characters.json"
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    except Exception:
        idx = {}
    body = request.get_json(silent=True) or {}
    rec = body or idx.get(name)
    if not rec:
        return _err(f"Không có dữ liệu nhân vật '{name}' để lưu.")
    rec["name"] = name
    idx[name] = rec
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return jsonify({"ok": True, "name": name})


@app.post("/api/library/character/<name>/mouth")
def api_lib_character_mouth(name):
    """Lưu tọa độ miệng (chấm trên ảnh) cho nhân vật 1 ảnh."""
    body = request.get_json(silent=True) or {}
    try:
        x = int(body.get("x"))
        y = int(body.get("y"))
    except (TypeError, ValueError):
        return _err("Thiếu toạ độ x, y.")
    idx_path = config.LIBRARY / "characters.json"
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    except Exception:
        idx = {}
    rec = idx.get(name)
    if not rec:
        return _err(f"Không có nhân vật '{name}' trong thư viện.", 404)
    rec["mouth_pos"] = [x, y]
    idx[name] = rec
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return jsonify({"ok": True, "name": name, "mouth_pos": [x, y]})


@app.post("/api/library/background")
def api_lib_background():
    files = request.files.getlist("files") or ([request.files["file"]]
                                               if "file" in request.files else [])
    if not files:
        return _err("Chưa chọn ảnh bối cảnh.")
    tmp = config.DATA / "tmp" / uuid.uuid4().hex[:8]
    tmp.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        if not f.filename:
            continue
        p = tmp / Path(f.filename).name
        f.save(str(p))
        out.append(assets.save_background(p, Path(f.filename).stem))
    if not out:
        return _err("Không đọc được ảnh nào.")
    return jsonify(out[0] if len(out) == 1 else out)


@app.post("/api/library/voice")
def api_lib_voice():
    f = request.files.get("file")
    if not f or not f.filename:
        return _err("Chưa chọn file giọng mẫu.")
    name = (request.form.get("name") or Path(f.filename).stem).strip()
    language = (request.form.get("language") or "ko").strip()
    text = (request.form.get("text") or "").strip()

    tmp = config.DATA / "tmp" / uuid.uuid4().hex[:8]
    tmp.mkdir(parents=True, exist_ok=True)
    p = tmp / Path(f.filename).name
    f.save(str(p))
    try:
        rec = assets.save_voice(name, language, p, text)
    except Exception as e:  # noqa: BLE001
        return _err(f"Không đọc được file giọng: {e}")
    info = rec["languages"].get(language, {})
    return jsonify({"name": name, "language": language,
                    "duration": info.get("duration"), "text": info.get("text"),
                    "file": info.get("file")})


@app.post("/api/library/voice/design")
def api_lib_voice_design():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    language = body.get("language") or "ko"
    instruct = (body.get("instruct") or "").strip()
    if not name:
        return _err("Thiếu tên nhân vật.")
    if not instruct:
        return _err("Thiếu mô tả giọng.")

    from core import voice as voice_mod
    items = voice_mod.parse_instruct(instruct)
    if not items:
        return _err(
            "Mô tả giọng chưa khớp từ vựng OmniVoice hỗ trợ. Ví dụ: "
            "female, young adult, high pitch / male, elderly, low pitch."
        )
    sample = {"ko": "안녕하세요, 목소리 테스트입니다.",
              "vi": "Xin chào, đây là giọng đọc thử nhé."}.get(
        language, "Hi there, this is a voice test.")
    try:
        wav, sr = voice_mod.synthesize(sample, language, instruct=", ".join(items))
    except Exception as e:  # noqa: BLE001
        return _err(f"OmniVoice lỗi: {e}", 500)

    import soundfile as sf
    dest = assets.VOICE_DIR / assets.config_slug(name)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{language}.wav"
    sf.write(str(out), wav, sr)

    idx_path = config.LIBRARY / "voices.json"
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    except Exception:
        idx = {}
    rec = idx.get(name) or {"name": name, "languages": {}}
    rec["languages"][language] = {
        "file": str(out), "duration": round(len(wav) / sr, 2),
        "text": sample, "instruct": ", ".join(items), "mode": "design",
    }
    idx[name] = rec
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return jsonify({"name": name, "language": language,
                    "duration": round(len(wav) / sr, 2),
                    "file": str(out), "resolved_instruct": ", ".join(items)})


@app.get("/api/library/voice/<name>/audio")
def api_lib_voice_audio(name):
    lang = request.args.get("lang", "ko")
    p = assets.voice_path(name, lang)
    if not p:
        return _err("Chưa có giọng mẫu cho nhân vật này.", 404)
    return send_file(str(p), mimetype="audio/wav")


@app.get("/api/library/image/<path:image_id>")
def api_lib_image(image_id):
    p = Path(image_id)
    if not p.is_absolute() and Path("/" + image_id).is_absolute():
        p = Path("/" + image_id)          # Linux/macOS: dấu '/' đầu bị bỏ khi ghép URL
    if p.is_absolute() and p.exists():
        # chỉ trả ảnh nằm trong thư mục của tool (không cho đọc file khác trên máy)
        try:
            p.resolve().relative_to(config.ROOT.resolve())
        except ValueError:
            return _err("Không thấy ảnh.", 404)
        return send_file(str(p))
    found = assets.find_image(image_id)
    if not found:
        return _err("Không thấy ảnh.", 404)
    return send_file(str(found))


# ------------------------------------------------------------------ project

@app.post("/api/project")
def api_project_new():
    body = request.get_json(silent=True) or {}
    pid = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    data = {
        "id": pid,
        "title": (body.get("title") or "").strip(),
        "language": body.get("language") or "ko",
        "kind": body.get("kind") or "",
        "format": _norm_format(body.get("format")),
        "duration": _norm_duration(body.get("duration")),
        "script": "",
        "assets": {"characters": [], "background": None, "voices": {}},
        "state": "draft",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    config.project_dir(pid)
    _save_project(pid, data)
    return jsonify(data)


def _norm_format(v) -> str:
    v = str(v or "").strip()
    return v if v in config.FORMATS else config.DEFAULT_FORMAT


def _norm_duration(v) -> int | None:
    """Số giây đích của tập (15–600), None = để AI tự chọn 30–90 giây."""
    try:
        d = int(float(v))
    except (TypeError, ValueError):
        return None
    return max(15, min(600, d)) if d > 0 else None


@app.post("/api/project/<pid>/meta")
def api_project_meta(pid):
    """Đổi khung video và thời lượng đích của tập."""
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    body = request.get_json(silent=True) or {}
    if "format" in body:
        data["format"] = _norm_format(body.get("format"))
    if "duration" in body:
        data["duration"] = _norm_duration(body.get("duration"))
    from core import scene_art
    # "" = theo Cài đặt
    for key, ok in (("bg_style", scene_art.ART_STYLES),
                    ("char_style", list(character_kit.STYLES) + ["auto"])):
        if key in body:
            if body[key] in ok:
                data[key] = body[key]
            else:
                data.pop(key, None)
    pdir = config.project_dir(pid)
    redrawn = _fit_scene_bgs(data, pdir)
    restyled = _restyle_kit_chars(data, pdir) if "char_style" in body else []
    _save_project(pid, data)
    return jsonify({"ok": True, "format": data.get("format"),
                    "duration": data.get("duration"), "redrawn": redrawn,
                    "restyled": restyled})


@app.get("/api/project/<pid>")
def api_project_get(pid):
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    s = parse_script(data.get("script", ""))
    data["parse"] = {"errors": s.errors, "warnings": s.warnings,
                     "cast": s.cast, "sides": s.sides, "scenes": s.scenes,
                     "scene_cast": s.scene_cast}
    data["estimate_duration"] = round(estimate_duration(s), 1)
    data["status"] = _status(pid)
    data.setdefault("format", config.DEFAULT_FORMAT)
    data.setdefault("duration", None)
    return jsonify(data)


@app.post("/api/project/<pid>/script")
def api_project_script(pid):
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    body = request.get_json(silent=True) or {}
    data["script"] = body.get("script", "")
    s = parse_script(data["script"])
    if s.title:
        data["title"] = s.title
    data["language"] = s.language
    _save_project(pid, data)
    return jsonify({"ok": True, "errors": s.errors, "warnings": s.warnings,
                    "estimate_duration": round(estimate_duration(s), 1)})


@app.post("/api/project/<pid>/write")
def api_project_write(pid):
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or data.get("title") or "").strip()
    language = body.get("language") or data.get("language") or "ko"
    kind = body.get("kind") or data.get("kind") or ""
    hints = body.get("hints") or ""
    if "duration" in body:
        data["duration"] = _norm_duration(body.get("duration"))
    if not title:
        return _err("Cần có tiêu đề để AI viết kịch bản.")
    try:
        script = claude_cli.write_script(title, language, kind or None, hints,
                                         duration=data.get("duration"))
    except RuntimeError as e:
        return _err(str(e), 502)
    data.update({"title": title, "language": language, "kind": kind,
                 "script": script})
    _save_project(pid, data)
    s = parse_script(script)
    return jsonify({"script": script, "errors": s.errors,
                    "warnings": s.warnings,
                    "estimate_duration": round(estimate_duration(s), 1)})


@app.post("/api/project/<pid>/ideas")
def api_project_ideas(pid):
    body = request.get_json(silent=True) or {}
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    title = (body.get("title") or data.get("title") or "").strip()
    language = body.get("language") or data.get("language") or "ko"
    if not title:
        return _err("Cần có tiêu đề để gợi ý hướng.")
    try:
        ideas = claude_cli.three_ideas(title, language)
    except RuntimeError as e:
        return _err(str(e), 502)
    return jsonify({"ideas": ideas})


@app.post("/api/project/<pid>/trends")
def api_project_trends(pid):
    body = request.get_json(silent=True) or {}
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    language = body.get("language") or data.get("language") or "ko"
    try:
        ideas = claude_cli.find_trends(language, data.get("title", ""))
    except RuntimeError as e:
        return _err(str(e), 502)
    return jsonify({"ideas": ideas})


@app.post("/api/project/<pid>/review")
def api_project_review(pid):
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    script = data.get("script", "")
    if not script.strip():
        return _err("Chưa có kịch bản để rà soát.")
    try:
        sugg = claude_cli.review_script(script, data.get("language", "ko"),
                                        duration=data.get("duration"))
    except RuntimeError as e:
        return _err(str(e), 502)
    data["suggestions"] = sugg
    _save_project(pid, data)
    return jsonify({"suggestions": sugg})


@app.post("/api/project/<pid>/apply")
def api_project_apply(pid):
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    body = request.get_json(silent=True) or {}
    # Giao diện gửi kèm nội dung góp ý đã chọn: dùng luôn, không phụ thuộc bản
    # lưu trên server (bản lưu có thể bị một lần lưu khác ghi đè trong lúc
    # Claude đang rà soát).
    sugg = []
    for it in body.get("items") or []:
        if isinstance(it, dict) and (it.get("suggestion") or it.get("quote")):
            sugg.append({k: str(it.get(k, ""))[:1000]
                         for k in ("category", "quote", "suggestion", "severity")})
    if not sugg:
        ids = {str(i) for i in (body.get("ids") or [])}
        sugg = [s for s in (data.get("suggestions") or []) if str(s.get("id")) in ids]
    if not sugg:
        return _err("Chưa chọn góp ý nào.")
    if isinstance(body.get("script"), str) and body["script"].strip():
        data["script"] = body["script"]          # bản đang hiện trên màn hình
    try:
        new_script = claude_cli.apply_suggestions(data.get("script", ""), sugg)
    except RuntimeError as e:
        return _err(str(e), 502)
    data["script"] = new_script
    _save_project(pid, data)
    s = parse_script(new_script)
    return jsonify({"script": new_script, "errors": s.errors,
                    "warnings": s.warnings,
                    "estimate_duration": round(estimate_duration(s), 1)})


@app.post("/api/project/<pid>/assets")
def api_project_assets(pid):
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)

    pdir = config.project_dir(pid)
    adir = pdir / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    # --- nhân vật ---
    cfiles = request.files.getlist("characters")
    if cfiles:
        tmp = adir / "chars_in"
        tmp.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for f in cfiles:
            if not f.filename:
                continue
            p = tmp / Path(f.filename).name
            f.save(str(p))
            if p.suffix.lower() == ".zip":
                paths += assets.extract_zip(p, tmp)
            else:
                paths.append(p)
        parsed = assets.parse_character_files(paths)
        warnings += parsed["warnings"]
        chars = []
        for name, rec in parsed["characters"].items():
            try:
                saved = assets.save_character(name, "", paths, to_library=False)
                chars.append(saved)
            except ValueError as e:
                warnings.append(str(e))
        if chars:
            existing = {c["name"]: c for c in data["assets"].get("characters", [])}
            for c in chars:
                existing[c["name"]] = c
            data["assets"]["characters"] = list(existing.values())

    # --- bối cảnh ---
    bg = request.files.get("background")
    if bg and bg.filename:
        p = adir / ("bg_" + Path(bg.filename).name)
        bg.save(str(p))
        rec = assets.save_background(p, Path(bg.filename).stem)
        data["assets"]["background"] = rec

    # --- giọng mẫu ---
    vfiles = request.files.getlist("voices")
    if vfiles:
        lang = data.get("language", "ko")
        for f in vfiles:
            if not f.filename:
                continue
            name = Path(f.filename).stem
            p = adir / ("voice_" + Path(f.filename).name)
            f.save(str(p))
            try:
                rec = assets.save_voice(name, lang, p, "")
                info = rec["languages"].get(lang, {})
                data["assets"].setdefault("voices", {})[name] = {
                    "ref": info.get("file"), "ref_text": info.get("text", ""),
                    "duration": info.get("duration"), "mode": "upload",
                }
            except Exception as e:  # noqa: BLE001
                warnings.append(f"'{f.filename}': {e}")

    _save_project(pid, data)
    return jsonify({"assets": data["assets"], "warnings": warnings})


@app.post("/api/project/<pid>/scene-bg")
def api_project_scene_bg(pid):
    """Tải ảnh nền cho một cảnh (form: scene = mô tả cảnh, file = ảnh)."""
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    f = request.files.get("file")
    if not f or not f.filename:
        return _err("Chưa chọn ảnh.")
    desc = (request.form.get("scene") or "").strip()
    adir = config.project_dir(pid) / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    p = adir / ("bg_" + uuid.uuid4().hex[:6] + "_" + Path(f.filename).name)
    f.save(str(p))
    rec = assets.save_background(p, Path(f.filename).stem)
    _set_scene_bg(data, desc, rec)
    _save_project(pid, data)
    return jsonify({"assets": data["assets"]})


@app.post("/api/project/<pid>/generate")
def api_project_generate(pid):
    """Claude tạo phần còn thiếu: bộ ghép nhân vật, bối cảnh, mô tả giọng."""
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)

    body = request.get_json(silent=True) or {}
    s = parse_script(data.get("script", ""))
    language = _project_language(data, s)
    pdir = config.project_dir(pid)
    want_chars = body.get("characters")
    if want_chars is None:
        have = {c["name"] for c in data["assets"].get("characters", [])}
        want_chars = [n for n in (s.cast or s.speakers_in_order())
                      if n not in have]
    warnings: list[str] = []

    # --- nhân vật bằng bộ ghép ---
    made = []
    if want_chars:
        try:
            specs = claude_cli.pick_character_specs(
                want_chars, data.get("script", ""), language
            )
        except Exception as e:  # noqa: BLE001
            warnings.append(f"AI chọn bộ ghép lỗi ({_short_err(e)}); dùng mặc định.")
            specs = {}
        # nghề rõ trong kịch bản mà AI chưa cho mặc đồng phục -> tự mặc
        jobs = character_kit.guess_jobs(list(s.cast or want_chars),
                                        [(b.speaker, b.text) for b in s.beats if b.kind == "line"])
        for n in want_chars:
            sp = specs.setdefault(n, {})
            if n in jobs and sp.get("outfit") not in character_kit.JOB_OUTFITS:
                sp["outfit"] = jobs[n]
        # mỗi người một màu áo, kiểu tóc (kể cả so với nhân vật đã có trong tập)
        taken = [c.get("spec") or {} for c in data["assets"].get("characters", [])
                 if c.get("name") not in want_chars]
        specs = character_kit.make_distinct(specs, want_chars, taken)
        style = _char_style(data, language)
        for i, name in enumerate(want_chars):
            made.append(_build_kit_char(
                pdir, s, name, specs.get(name) or {}, style,
                s.sides.get(name, ["trai", "phai", "giua"][min(i, 2)])))
        existing = {c["name"]: c for c in data["assets"].get("characters", [])}
        for c in made:
            existing[c["name"]] = c
        data["assets"]["characters"] = list(existing.values())

    # --- bối cảnh: mỗi cảnh ('## canh:') một ảnh ---
    # body.scenes: danh sách mô tả cảnh cần vẽ (lại); không có thì vẽ các
    # cảnh còn thiếu ảnh. body.background (chuỗi): gợi ý cho bối cảnh chung.
    hint = body.get("background") if isinstance(body.get("background"), str) else ""
    scenes = s.scenes or [""]
    if isinstance(body.get("scenes"), list):
        targets = [str(x) for x in body["scenes"]]
    else:
        targets = [d for d in scenes if not _scene_bg(data, d)]
        # kịch bản nhiều cảnh mà cảnh nào cũng có ảnh riêng: không cần nền chung
    for desc in targets:
        rec, warn = _draw_scene_bg(data, pdir, desc, hint)
        if warn:
            warnings.append(warn)
        _set_scene_bg(data, desc, rec)

    # --- mô tả giọng ---
    if body.get("voices"):
        need = [n for n in (s.cast or s.speakers_in_order())
                if n not in (data["assets"].get("voices") or {})]
        if need:
            try:
                vdesc = claude_cli.describe_voices(need, data.get("script", ""), language)
            except Exception as e:  # noqa: BLE001
                warnings.append(f"AI mô tả giọng lỗi ({_short_err(e)}).")
                vdesc = {}
            from core import voice as voice_mod
            for name in need:
                instruct = vdesc.get(name, "female, young adult, moderate pitch")
                items = voice_mod.parse_instruct(instruct)
                data["assets"].setdefault("voices", {})[name] = {
                    "ref": None, "instruct": ", ".join(items) or
                    "female, young adult, moderate pitch",
                    "mode": "design",
                }

    _save_project(pid, data)
    return jsonify({"assets": data["assets"], "warnings": warnings})


@app.post("/api/project/<pid>/character_photo")
def api_project_character_photo(pid):
    """Tạo nhân vật bộ ghép giống ảnh chị tải lên: Claude xem ảnh, chọn tóc,
    màu da, áo, trang phục... rồi tool ghép theo kiểu nhân vật của tập."""
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    name = (request.form.get("name") or "").strip()
    f = request.files.get("file")
    if not name:
        return _err("Chưa chọn nhân vật.")
    if not f:
        return _err("Chưa chọn ảnh.")
    from PIL import Image
    try:
        img = Image.open(f.stream).convert("RGB")
    except Exception:  # noqa: BLE001
        return _err("Không đọc được ảnh (chị thử ảnh JPG hoặc PNG).")
    pdir = config.project_dir(pid)
    ref = pdir / "assets" / "ref" / f"{assets.config_slug(name) or 'nv'}.png"
    ref.parent.mkdir(parents=True, exist_ok=True)
    img.thumbnail((1600, 1600))
    img.save(ref)
    # bản nhỏ trong thư mục riêng của Claude cho đỡ tốn hạn mức khi xem ảnh
    look = Path(claude_cli._claude_dir()) / f"anh_{uuid.uuid4().hex[:8]}.png"
    small = img.copy()
    small.thumbnail((768, 768))
    small.save(look)
    warnings: list[str] = []
    try:
        spec = claude_cli.spec_from_photo(look, name)
    except Exception as e:  # noqa: BLE001
        warnings.append(f"Claude chưa xem được ảnh ({_short_err(e)}); "
                        "tool tự lấy màu áo, màu tóc từ ảnh.")
        spec = {}
    finally:
        look.unlink(missing_ok=True)
    if not spec:
        spec = character_kit.spec_from_colors(ref)
    note = spec.pop("note", "")
    s = parse_script(data.get("script", ""))
    chars = data["assets"].setdefault("characters", [])
    old = next((c for c in chars if c.get("name") == name), None)
    side = (old or {}).get("side") or s.sides.get(name) or \
        ["trai", "phai", "giua"][min(len(chars), 2)]
    rec = _build_kit_char(pdir, s, name, spec,
                          _char_style(data, _project_language(data, s)), side)
    rec["ref_image"] = str(ref)
    if note:
        rec["ref_note"] = note
    if old:
        chars[chars.index(old)] = rec
    else:
        chars.append(rec)
    _save_project(pid, data)
    return jsonify({"character": rec, "note": note, "warnings": warnings,
                    "assets": data["assets"]})


# ------------------------------------------------------------------- render

@app.post("/api/project/<pid>/render")
def api_project_render(pid):
    try:
        data = _load_project(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)

    st = _status(pid)
    if st.get("state") == "rendering":
        return jsonify({"ok": True, "already": True})

    s = parse_script(data.get("script", ""))
    if s.errors:
        return _err("Kịch bản còn lỗi: " + "; ".join(s.errors[:3]))
    chars_cfg = data["assets"].get("characters") or []
    if not chars_cfg:
        return _err("Chưa có nhân vật. Chị tải ảnh lên hoặc bấm để AI tạo.")

    with JOBS_LOCK:
        JOBS[pid] = {"state": "rendering", "progress": 0.0,
                     "message": "bắt đầu", "log": ["bắt đầu dựng"]}

    def work():
        try:
            pdir = config.project_dir(pid)
            settings = config.load_settings()
            if not settings.get("title_text"):
                settings["title_text"] = data.get("title", "")
            settings["video_format"] = _norm_format(data.get("format"))
            settings["target_duration"] = data.get("duration")
            settings["bg_spec"] = (data["assets"].get("background") or {}).get("spec")
            if _fit_scene_bgs(data, pdir):
                _save_project(pid, data)
            bg = (data["assets"].get("background") or {}).get("image")
            voices = dict(data["assets"].get("voices") or {})
            # nhân vật chưa có giọng -> dùng mô tả, mỗi vai một giọng khác nhau
            default_instructs = [
                "female, young adult, moderate pitch",
                "male, middle-aged, low pitch",
                "female, elderly, low pitch",
            ]
            names = s.cast or s.speakers_in_order()
            for i, name in enumerate(names):
                if name in voices:
                    continue
                lib = assets.voice_path(name, s.language)
                if lib:
                    voices[name] = {"ref": str(lib),
                                    "ref_text": assets.voice_text(name, s.language)}
                else:
                    voices[name] = {
                        "instruct": default_instructs[i % len(default_instructs)]
                    }

            def prog(frac, msg):
                _set_status(pid, progress=round(float(frac), 3), message=str(msg))

            result = pipeline.render_episode(
                pdir, s, chars_cfg, Path(bg) if bg else None,
                voices, settings, progress=prog,
                scene_bgs=_scene_bg_paths(data, s),
                scene_kinds=_scene_kinds(data, s),
            )
            data["result"] = result
            data["state"] = "done"
            _save_project(pid, data)

            # lưu lịch sử chống lặp khuôn
            hist = [h for h in _history() if h.get("id") != pid]   # dựng lại: thay bản cũ
            hist.append({
                "id": pid, "title": data.get("title", ""),
                "language": data.get("language", "ko"),
                "kind": data.get("kind", ""),
                "kind_name": (COMEDY_KINDS.get(data.get("language", "ko"), {})
                              .get(data.get("kind", ""), ("", ""))[0]),
                "opening": (s.lines()[0].text[:60] if s.lines() else ""),
                "ending": (s.lines()[-1].text[:60] if s.lines() else ""),
                "characters": list(s.cast) if s.cast else list(s.speakers_in_order()),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            })
            _save_history(hist[-200:])

            _set_status(pid, state="done", progress=1.0,
                        message=f"xong — {result['duration']:.1f} giây",
                        video_ready=True)
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc(limit=4)
            _set_status(pid, state="error", message=f"lỗi: {e}")
            with JOBS_LOCK:
                JOBS[pid]["traceback"] = tb

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True, "job": pid})


@app.get("/api/project/<pid>/status")
def api_project_status(pid):
    st = _status(pid)
    out = config.PROJECTS / pid / "out" / "video.mp4"      # chỉ đọc, không tạo lại thư mục đã xoá
    st["video_ready"] = out.exists()
    return jsonify(st)


@app.get("/api/project/<pid>/video")
def api_project_video(pid):
    p = config.project_dir(pid) / "out" / "video.mp4"
    if not p.exists():
        return _err("Chưa có video.", 404)
    return send_file(str(p), mimetype="video/mp4")


@app.get("/api/project/<pid>/pack")
def api_project_pack(pid):
    p = config.project_dir(pid) / "out" / "capcut_pack.zip"
    if not p.exists():
        return _err("Chưa có bộ file rời.", 404)
    return send_file(str(p), as_attachment=True,
                     download_name=f"{pid}_capcut.zip")


# ------------------------------------------------------- xuất dự án CapCut

@app.get("/api/capcut/drafts")
def api_capcut_drafts():
    """Danh sách dự án CapCut trên máy, để chọn làm dự án mẫu."""
    root = config.capcut_drafts_root()
    return jsonify({
        "root": str(root),
        "root_exists": root.is_dir(),
        "drafts": capcut_export.list_draft_names(root) if root.is_dir() else [],
        "template": config.load_settings().get("capcut_template_draft") or "",
    })


@app.post("/api/project/<pid>/capcut-export")
def api_project_capcut_export(pid):
    """Tạo dự án CapCut mới từ tập đã dựng xong."""
    body = request.get_json(silent=True) or {}
    draft_name = str(body.get("draft_name") or "").strip()

    try:
        root = config.capcut_drafts_root()
        template = config.capcut_template_draft()
        if template is None:
            name = str(config.load_settings().get("capcut_template_draft") or "").strip()
            if not name:
                msg = (
                    "Chưa chọn dự án CapCut mẫu. Vào trang Cài đặt, mục "
                    "“Chọn dự án CapCut mẫu” rồi bấm Lưu nhé."
                )
                _log_capcut_error(pid, msg)
                return _err(msg)
            msg = (
                f"Không tìm thấy dự án mẫu “{name}” trong thư mục CapCut. "
                "Chị kiểm tra lại đường dẫn ở trang Cài đặt nhé."
            )
            _log_capcut_error(pid, msg)
            return _err(msg)

        exporter = capcut_export.CapCutExporter(root, template)
        pdir = config.project_dir(pid)
        folder = exporter.export_project(pdir, draft_name)
    except capcut_export.CapCutEncryptedError as e:
        _log_capcut_error(pid, str(e))
        return _err(str(e))
    except FileNotFoundError as e:
        _log_capcut_error(pid, str(e))
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        msg = f"Xuất dự án CapCut lỗi: {e}"
        # ghi kèm vị trí lỗi vào log để dễ sửa
        _log_capcut_error(pid, msg + "\n" + traceback.format_exc(limit=6))
        traceback.print_exc()
        return _err(msg, 500)

    return jsonify({
        "ok": True,
        "name": folder.name,
        "path": str(folder),
        "message": (
            f"Đã tạo dự án CapCut “{folder.name}”. "
            "Chị nhớ đóng CapCut rồi mở lại để thấy dự án mới nhé."
        ),
    })


def _log_capcut_error(pid: str, msg: str) -> None:
    """Ghi lỗi xuất CapCut ra file log."""
    try:
        config.LOGS.mkdir(parents=True, exist_ok=True)
        p = config.LOGS / "capcut_export.log"
        with open(p, "a", encoding="utf-8") as f:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{stamp}] [{pid}] {msg}\n")
    except Exception:
        pass


# ------------------------------------------------------------------ history

@app.get("/api/history")
def api_history_get():
    return jsonify(_history())


@app.post("/api/history")
def api_history_post():
    body = request.get_json(silent=True) or {}
    hist = _history()
    # mỗi tập một bản ghi: server đã ghi khi dựng xong (kèm câu mở/chốt),
    # bản giao diện gửi lên chỉ bổ sung trường còn thiếu
    pid = body.get("id")
    same = [h for h in hist if pid and h.get("id") == pid]
    if same:
        for k, v in body.items():
            if v and not same[-1].get(k):
                same[-1][k] = v
    else:
        hist.append({**body,
                     "created_at": datetime.now().isoformat(timespec="seconds")})
    _save_history(hist[-200:])
    return jsonify({"ok": True})


# -------------------------------------------------------------------- chạy


# ------------------------------------------------ dựng xương (Bước C2)

@app.post("/api/rig/upload")
def api_rig_upload():
    """Tải ảnh nhân vật, tách nền và ước khớp."""
    f = request.files.get("file")
    if not f or not f.filename:
        return _err("Chưa chọn ảnh.", 400)
    pdir = config.DATA / "tmp" / "rig"
    pdir.mkdir(parents=True, exist_ok=True)
    dst = pdir / Path(f.filename).name
    f.save(str(dst))
    try:
        char = photo_rig.PhotoCharacter.load("tmp", dst)
    except Exception as e:  # noqa: BLE001
        return _err(f"Không xử lý được ảnh: {e}", 400)
    return jsonify({
        "ok": True,
        "path": str(dst),
        "url": "/api/rig/image/" + quote(dst.name),
        "size": list(char.rgba.size),
        "joints": char.joints.as_dict(),
        "source": char.source,
        "valid": char.valid,
    })


@app.get("/api/rig/image/<name>")
def api_rig_image(name):
    """Ảnh gốc đã tải lên ở màn Dựng xương (chỉ đọc trong thư mục tmp/rig)."""
    return send_from_directory(str(config.DATA / "tmp" / "rig"), name)


@app.post("/api/rig/save")
def api_rig_save():
    """Lưu rig.json (khớp đã sửa) vào thư mục tmp/rig."""
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "photo")
    joints = body.get("joints")
    source = body.get("source", "fallback")
    if not joints or not isinstance(joints, dict):
        return _err("Thiếu dữ liệu khớp.", 400)
    pdir = config.DATA / "tmp" / "rig"
    pdir.mkdir(parents=True, exist_ok=True)
    out = {
        "name": name,
        "root": "than",
        "source": source,
        "bones": [
            {"name": "than", "parent": None, "offset": list(joints.get("hip", [300, 620])),
             "part": "than.png", "pivot": list(joints.get("hip", [300, 620])), "layer": 2},
            {"name": "co", "parent": "than", "offset": list(joints.get("neck", [300, 400])),
             "part": "co.png", "pivot": list(joints.get("neck", [300, 400])), "layer": 2},
            {"name": "dau", "parent": "co", "offset": list(joints.get("head", [300, 130])),
             "part": "dau_dong.png", "pivot": list(joints.get("head", [300, 130])), "layer": 3},
            {"name": "vai_right", "parent": "than",
             "offset": list(joints.get("shoulder_r", [440, 260])),
             "part": "vai_right.png", "pivot": list(joints.get("shoulder_r", [440, 260])), "layer": 4},
            {"name": "khuyu_right", "parent": "vai_right",
             "offset": list(joints.get("elbow_r", [560, 380])),
             "part": "khuyu_right.png", "pivot": list(joints.get("elbow_r", [560, 380])), "layer": 4},
            {"name": "co_tay_right", "parent": "khuyu_right",
             "offset": list(joints.get("wrist_r", [700, 450])),
             "part": "co_tay_right.png", "pivot": list(joints.get("wrist_r", [700, 450])), "layer": 4},
            {"name": "vai_left", "parent": "than",
             "offset": list(joints.get("shoulder_l", [160, 260])),
             "part": "vai_left.png", "pivot": list(joints.get("shoulder_l", [160, 260])), "layer": 0},
            {"name": "khuyu_left", "parent": "vai_left",
             "offset": list(joints.get("elbow_l", [40, 380])),
             "part": "khuyu_left.png", "pivot": list(joints.get("elbow_l", [40, 380])), "layer": 0},
            {"name": "co_tay_left", "parent": "khuyu_left",
             "offset": list(joints.get("wrist_l", [30, 450])),
             "part": "co_tay_left.png", "pivot": list(joints.get("wrist_l", [30, 450])), "layer": 0},
            {"name": "dui_right", "parent": "than",
             "offset": list(joints.get("hip_r", [450, 560])),
             "part": "dui_right.png", "pivot": list(joints.get("hip_r", [450, 560])), "layer": 1},
            {"name": "goi_right", "parent": "dui_right",
             "offset": list(joints.get("knee_r", [520, 780])),
             "part": "goi_right.png", "pivot": list(joints.get("knee_r", [520, 780])), "layer": 1},
            {"name": "co_chan_right", "parent": "goi_right",
             "offset": list(joints.get("ankle_r", [560, 950])),
             "part": "co_chan_right.png", "pivot": list(joints.get("ankle_r", [560, 950])), "layer": 1},
            {"name": "dui_left", "parent": "than",
             "offset": list(joints.get("hip_l", [150, 560])),
             "part": "dui_left.png", "pivot": list(joints.get("hip_l", [150, 560])), "layer": 1},
            {"name": "goi_left", "parent": "dui_left",
             "offset": list(joints.get("knee_l", [80, 780])),
             "part": "goi_left.png", "pivot": list(joints.get("knee_l", [80, 780])), "layer": 1},
            {"name": "co_chan_left", "parent": "goi_left",
             "offset": list(joints.get("ankle_l", [40, 950])),
             "part": "co_chan_left.png", "pivot": list(joints.get("ankle_l", [40, 950])), "layer": 1},
        ],
    }
    p = pdir / f"{name}.json"
    p.write_text(__import__("json").dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "path": str(p)})


@app.route("/api/rig/preview", methods=["GET", "POST"])
def api_rig_preview():
    """Xem thử một cử chỉ trên ảnh đã load, dùng khung xương chị đã sửa.

    Trả về chuỗi khung JPEG (base64) đủ một vòng cử chỉ để phát lặp lại.
    """
    import base64, io
    from PIL import Image
    from core import gestures as gmod
    body = request.get_json(silent=True) or {}
    path = body.get("path") or request.args.get("path")
    mode = body.get("gesture") or body.get("mode") or request.args.get("mode", "wave")
    gesture_name = {"wave": "vaytay", "walk": "dibo"}.get(mode, mode)
    if not path:
        return _err("Thiếu path ảnh.", 400)
    _, lib = gmod.ensure_library()
    gesture = lib.get(gesture_name)
    if gesture is None and gesture_name != "tho":
        return _err(f"Không có cử chỉ '{gesture_name}'.", 400)
    try:
        char = photo_rig.PhotoCharacter.load("tmp", Path(path))
    except Exception as e:  # noqa: BLE001
        return _err(f"Không load ảnh: {e}", 400)
    joints = body.get("joints")
    if isinstance(joints, dict):
        cur = char.joints.as_dict()
        try:
            cur.update({k: (float(v[0]), float(v[1])) for k, v in joints.items() if k in cur})
        except (TypeError, ValueError, IndexError):
            return _err("Dữ liệu khớp không hợp lệ.", 400)
        char.joints = photo_rig.PhotoJoints(**cur)

    fps = 12
    duration = gesture.duration if gesture is not None else 2.0
    if gesture is not None and gesture.loop:
        duration *= 2   # cử chỉ lặp: cho chạy hai vòng
    duration = min(max(duration + gmod.RETURN_TIME + 0.4, 1.5), 4.0)
    n = int(duration * fps)
    w0, h0 = char.rgba.size
    m = int(max(w0, h0) * 0.25)        # lề quanh ảnh cho tay giơ ra ngoài
    w, h = w0 + 2 * m, h0 + 2 * m
    scale = min(1.0, 640 / h)
    out_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    frames = []
    for i in range(n):
        t = i / fps
        angles = gmod.breathe_angles(t, 0)
        pose = gmod.gesture_pose(gesture, t)
        if pose:
            angles = gmod.merge_angles(angles, pose)
        img, (ox, oy) = char.render_padded(angles, margin=0.25)
        bg = Image.new("RGB", (w, h), (30, 41, 59))
        # dịch cả người (vào/ra khung, nhảy lên) theo cỡ ảnh gốc
        off = (m - ox + int(angles.get("dich_x", 0.0) * w0),
               m - oy - int(angles.get("dich_y", 0.0) * h0))
        bg.paste(img, off, mask=img.getchannel("A"))
        if scale < 1.0:
            bg = bg.resize(out_size, Image.LANCZOS)
        buf = io.BytesIO()
        bg.save(buf, format="JPEG", quality=82)
        frames.append("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
    return jsonify({"ok": True, "gesture": gesture_name, "fps": fps, "frames": frames})


@app.get("/api/rig/gestures")
def api_rig_gestures():
    """Danh sách cử chỉ để chọn xem thử."""
    from core import gestures as gmod
    _, lib = gmod.ensure_library()
    items = [{"name": "tho", "label": "Đứng thở (không cử chỉ)"}]
    items += [{"name": g.name, "label": g.label or g.name} for g in lib.values()]
    return jsonify({"gestures": items})


# ====================================================================== TRUYỆN KỂ
# Video dài kể truyện (Lão Hạc...): một giọng người kể, tranh minh hoạ do chị tự
# vẽ từ bộ câu lệnh tool xuất ra (core/story.py, core/story_render.py).

def _load_story(pid: str) -> tuple[dict, dict]:
    from core import story as story_mod
    data = _load_project(pid)
    if data.get("mode") != "story":
        raise FileNotFoundError(f"'{pid}' không phải truyện kể")
    st = data.setdefault("story", story_mod.default_story())
    return data, st


def _story_view(pid: str, data: dict) -> dict:
    from core import story as story_mod
    pdir = config.project_dir(pid)
    st = data["story"]
    imgs = story_mod.scene_images(pdir)
    scenes = story_mod.all_scenes(st)
    out = dict(data)
    out["images"] = sorted(imgs)
    out["scene_count"] = len(scenes)
    out["missing"] = [sc["id"] for _ci, sc in scenes if sc["id"] not in imgs]
    from core import doodle, story_live
    for c in st.get("characters") or []:          # truyện làm từ trước: đoán bộ ghép từ mô tả
        if not c.get("kit"):
            c["kit"] = doodle.kit_from_look(c.get("name", ""), c.get("look", ""))
    for p in st.get("places") or []:
        if not scene_art.valid_kind(p.get("kind")):
            p["kind"] = story_live.place_kind(p)
        p.setdefault("time", "ngay")
    out["visual"] = st.get("visual", "tool")
    from core import doodle_parts, film as film_m, film_rig
    out["mode"] = st.get("mode", "story")
    out["char_styles"] = _char_style_options()
    smp = st.get("char_sample") or {}
    out["char_sample"] = {"note": smp.get("note", ""), "has": bool(smp.get("image")),
                          "lib": smp.get("lib") or ""}
    from core import sync as sync_m
    out["sync_styles"] = [[k, v[0]] for k, v in sync_m.STYLES.items()]
    out["sync"] = {k: v for k, v in (st.get("sync") or {}).items() if k != "bible"}
    out["film_acts"] = [[k, v[0] if isinstance(v, tuple) else v] for k, v in film_m.all_actions().items()]
    out["spots"] = [[k, v] for k, v in film_m.SPOT_VI.items()]
    from core import film_sfx
    out["furniture_items"] = [[k, v[0]] for k, v in film_m.FURNITURE.items()] + \
        [[k, v["name"] + " (AI vẽ)"] for k, v in doodle_parts.load().items() if v.get("kind") == "furniture"]
    out["sfx_names"] = [[k, v] for k, v in film_sfx.LABELS.items() if k not in film_sfx.AMBIENT]
    out["props"] = [[k, v] for k, v in film_rig.PROPS.items()] + \
        [[k, "★ " + v["name"]] for k, v in doodle_parts.load().items() if v.get("kind") == "prop"]
    from core import bg3d
    out["bg_mode"] = st.get("bg_mode", "draw")
    from core import story as story_m
    out["dialogues"] = [[k, v[0]] for k, v in story_m.DIALOGUE.items()]
    out["tones"] = [[k, v] for k, v in story_m.TONES.items()]
    for c in st.get("characters") or []:
        if not isinstance(c.get("voice"), dict):
            c["voice"] = {"voice": "", "instruct": story_m.default_voice(c.get("kit"))}
    out["bg3d_installed"] = bg3d.installed()
    d3 = pdir / bg3d.DIR
    out["bg3d"] = sorted(p.stem for p in d3.glob("*.png")) if d3.exists() else []
    out["kit_options"] = doodle.options()
    lib = doodle_parts.load()
    out["kinds"] = [[k, v["label"]] for k, v in scene_art.KINDS.items()] + \
        [[k, "★ " + v["name"]] for k, v in lib.items() if v.get("kind") == "scene"]
    out["part_names"] = {k: v["name"] for k, v in lib.items()}
    out["parts"] = [{"id": k, "kind": v["kind"], "name": v["name"], "desc": v.get("desc", "")}
                    for k, v in lib.items()]
    out["acts"] = [[k, v[0]] for k, v in story_live.ACTS.items()]
    out["styles"] = [[k, v[0]] for k, v in story_mod.STYLES.items()]   # giữ thứ tự
    out["style_ref"] = (story_mod.image_dir(pdir) / story_mod.STYLE_REF).exists()
    out["cameras"] = list(story_mod.CAMERAS)
    out["status"] = _status(pid)
    out["video_ready"] = (pdir / "out" / "video.mp4").exists()
    return out


@app.post("/api/story")
def api_story_new():
    from core import story as story_mod
    body = request.get_json(silent=True) or {}
    pid = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    data = {
        "id": pid, "mode": "story", "title": (body.get("title") or "").strip(),
        "language": body.get("language") or "vi",
        "format": _norm_format(body.get("format") or "16:9"),
        "story": story_mod.default_story((body.get("title") or "").strip(),
                                         (body.get("author") or "").strip()),
        "assets": {"characters": [], "background": None, "voices": {}},
        "state": "draft", "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    config.project_dir(pid)
    _save_project(pid, data)
    return jsonify(_story_view(pid, data))


@app.get("/api/story/list")
def api_story_list():
    out = []
    for p in sorted(config.PROJECTS.glob("*/project.json"), reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if d.get("mode") == "story":
            out.append({"id": d["id"], "title": d.get("title") or "(chưa đặt tên)",
                        "created_at": d.get("created_at")})
            try:                       # lưu kiểu nhân vật theo ảnh mẫu ra thư viện (xoá truyện không mất)
                if style_lib.backup(d.get("story") or {}, d.get("title") or ""):
                    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
    return jsonify({"stories": out[:50]})


TRASH = config.DATA / "thung_rac"
TRASH_DAYS = 30


@app.delete("/api/story/<pid>")
def api_story_delete(pid):
    """Xoá truyện / phim: chuyển thư mục projects/<id> vào thùng rác (data/thung_rac),
    khôi phục được trong 30 ngày. Kiểu nhân vật theo ảnh mẫu đã lưu sẵn ở thư viện."""
    import shutil
    import time as _time
    d = (config.PROJECTS / pid).resolve()
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", pid or "") or d.parent != config.PROJECTS.resolve() \
            or not (d / "project.json").exists():
        return _err("Không tìm thấy truyện này.", 404)
    if _status(pid).get("state") in ("writing", "rendering", "drawing"):
        return _err("Truyện đang chạy (viết / vẽ / dựng), đợi xong rồi hãy xoá.")
    try:
        data = json.loads((d / "project.json").read_text(encoding="utf-8"))
        if style_lib.backup(data.get("story") or {}, data.get("title") or ""):
            (d / "project.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    TRASH.mkdir(parents=True, exist_ok=True)
    dest = TRASH / pid
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    shutil.move(str(d), str(dest))
    (dest / ".deleted_at").write_text(str(int(_time.time())), encoding="utf-8")
    with JOBS_LOCK:
        JOBS.pop(pid, None)
    return jsonify({"ok": True})


def _char_style_options() -> list:
    """Kiểu nhân vật: kiểu vẽ sẵn + kiểu theo ảnh mẫu đã lưu trong thư viện."""
    from core import film_rig
    return [[k, v["label"]] for k, v in film_rig.CHAR_STYLES.items()] + \
        [["lib:" + it["id"], "Đã lưu: " + it["name"]] for it in style_lib.items()]


# ---------------------------------------------- kiểu nhân vật (tab riêng)

@app.get("/api/styles")
def api_styles():
    from core import style_preview
    return jsonify({"items": style_preview.items()})


@app.get("/api/styles/<sid>/<what>")
def api_style_file(sid, what):
    """Ảnh động hành động (anim.webp), dàn nhân vật (cast.png), ảnh mẫu gốc (sample.png)."""
    from core import style_preview
    try:
        if what == "anim.webp":
            p = style_preview.anim(sid)
        elif what == "cast.png":
            p = style_preview.cast(sid)
        elif what == "sample.png" and sid.startswith("lib:"):
            got = style_lib.get(sid[4:]) or {}
            p = Path(got["image"]) if got.get("image") else None
        else:
            p = None
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return _err(f"Không vẽ được xem trước: {e}", 500)
    if not p or not Path(p).exists():
        return _err("Không có ảnh này.", 404)
    return send_file(str(p), max_age=0)


@app.post("/api/styles")
def api_style_create():
    """Tải ảnh nhân vật mẫu: Claude xem nét vẽ + ngoại hình, tool tạo kiểu nhân vật mới
    (lưu ở thư viện, mọi truyện chọn được)."""
    from PIL import Image
    f = request.files.get("file")
    if not f:
        return _err("Chưa chọn ảnh.")
    try:
        img = Image.open(f.stream).convert("RGB")
    except Exception:  # noqa: BLE001
        return _err("Không đọc được ảnh (thử JPG, PNG, WEBP).")
    img.thumbnail((1400, 1400))
    tmp = config.DATA / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    src = tmp / f"kieu_{uuid.uuid4().hex[:8]}.png"
    img.save(src)
    look = Path(claude_cli._claude_dir()) / f"mau_{uuid.uuid4().hex[:8]}.png"
    small = img.copy()
    small.thumbnail((768, 768))
    small.save(look)
    try:
        res = claude_cli.style_from_photo(look)
    except Exception as e:  # noqa: BLE001
        src.unlink(missing_ok=True)
        return _err(f"Claude chưa xem được ảnh: {_short_err(e)}")
    finally:
        look.unlink(missing_ok=True)
    if not res:
        src.unlink(missing_ok=True)
        return _err("Claude không phân tích được ảnh.")
    name = str(request.form.get("name") or "").strip() or res.get("note") or "Kiểu nhân vật mới"
    sid = style_lib.save(res, src, name)
    src.unlink(missing_ok=True)
    if not sid:
        return _err("Không lưu được kiểu nhân vật.")
    return jsonify({"ok": True, "id": "lib:" + sid, "note": res.get("note", "")})


@app.post("/api/styles/<sid>/redo")
def api_style_redo(sid):
    """Thiết kế lại kiểu đã tạo theo ảnh mẫu của nó (Claude xem lại, so và chỉnh)."""
    from PIL import Image
    got = style_lib.get(sid[4:]) if sid.startswith("lib:") else None
    if not got or style_lib.is_builtin(sid[4:]) or not got.get("image") or not Path(got["image"]).exists():
        return _err("Chỉ thiết kế lại được kiểu chị tự tạo có ảnh mẫu.")
    look = Path(claude_cli._claude_dir()) / f"mau_{uuid.uuid4().hex[:8]}.png"
    small = Image.open(got["image"]).convert("RGB")
    small.thumbnail((768, 768))
    small.save(look)
    try:
        res = claude_cli.style_from_photo(look)
    except Exception as e:  # noqa: BLE001
        return _err(f"Claude chưa xem được ảnh: {_short_err(e)}")
    finally:
        look.unlink(missing_ok=True)
    if not res or not style_lib.update(sid[4:], res):
        return _err("Claude không phân tích được ảnh.")
    return jsonify({"ok": True, "note": res.get("note", "")})


@app.post("/api/styles/<sid>/rename")
def api_style_rename(sid):
    name = str((request.get_json(silent=True) or {}).get("name") or "")
    if not sid.startswith("lib:") or not style_lib.rename(sid[4:], name):
        return _err("Chỉ đổi tên được kiểu chị tự tạo.")
    return jsonify({"ok": True})


@app.delete("/api/styles/<sid>")
def api_style_delete(sid):
    if not sid.startswith("lib:") or not style_lib.remove(sid[4:]):
        return _err("Chỉ xoá được kiểu chị tự tạo (kiểu có sẵn của tool thì giữ).")
    return jsonify({"ok": True})


@app.get("/api/story/options")
def api_story_options():
    """Lựa chọn dùng khi chưa mở truyện nào (ô Kiểu nhân vật)."""
    return jsonify({"char_styles": _char_style_options()})


@app.get("/api/story/trash")
def api_story_trash():
    """Truyện trong thùng rác (quá 30 ngày thì xoá hẳn)."""
    import shutil
    import time as _time
    out = []
    for d in sorted(TRASH.glob("*"), reverse=True) if TRASH.is_dir() else []:
        try:
            at = int((d / ".deleted_at").read_text().strip())
        except Exception:  # noqa: BLE001
            at = int(d.stat().st_mtime)
        if _time.time() - at > TRASH_DAYS * 86400:
            shutil.rmtree(d, ignore_errors=True)
            continue
        try:
            data = json.loads((d / "project.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        out.append({"id": d.name, "title": data.get("title") or "(chưa đặt tên)",
                    "deleted_at": _time.strftime("%d/%m %H:%M", _time.localtime(at))})
    return jsonify({"items": out})


@app.post("/api/story/trash/<pid>/restore")
def api_story_restore(pid):
    import shutil
    src = TRASH / pid
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", pid or "") or not (src / "project.json").exists():
        return _err("Không thấy truyện này trong thùng rác.", 404)
    if (config.PROJECTS / pid / "project.json").exists():
        return _err("Đã có truyện cùng mã, không khôi phục đè được.")
    shutil.rmtree(config.PROJECTS / pid, ignore_errors=True)       # thư mục rỗng (nếu có)
    shutil.move(str(src), str(config.PROJECTS / pid))
    (config.PROJECTS / pid / ".deleted_at").unlink(missing_ok=True)
    return jsonify({"ok": True, "id": pid})


@app.get("/api/story/<pid>")
def api_story_get(pid):
    try:
        data, _st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    return jsonify(_story_view(pid, data))


@app.post("/api/story/<pid>/save")
def api_story_save(pid):
    """Lưu thông tin truyện và phần chị sửa (lời kể, câu lệnh vẽ, máy quay)."""
    from core import story as story_mod
    try:
        data, st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    body = request.get_json(silent=True) or {}
    for k in ("title", "author", "source_text", "style", "subtitles", "era", "brief"):
        if k in body:
            st[k] = body[k]
    if body.get("visual") in ("tool", "images"):
        st["visual"] = body["visual"]
    if body.get("bg_mode") in ("draw", "ai3d"):
        st["bg_mode"] = body["bg_mode"]
    if body.get("dialogue") in story_mod.DIALOGUE:
        st["dialogue"] = body["dialogue"]
    if body.get("tone") in story_mod.TONES:
        st["tone"] = body["tone"]
    if body.get("mode") in ("story", "film", "sync"):
        st["mode"] = body["mode"]
    from core import film_rig as fr_m
    if body.get("char_style") in list(fr_m.CHAR_STYLES) + ["sample"]:
        st["char_style"] = body["char_style"]
    elif str(body.get("char_style") or "").startswith("lib:"):          # kiểu nhân vật đã lưu
        got = style_lib.get(body["char_style"][4:])
        if got:
            st["char_sample"] = got
            st["char_style"] = "sample"
    if isinstance(body.get("sync_style"), str):
        from core import sync as sync_m
        if body["sync_style"] in sync_m.STYLES:
            st.setdefault("sync", {})["style"] = body["sync_style"]
    if "minutes" in body:
        try:
            st["minutes"] = max(3, min(40, int(float(body["minutes"]))))
        except (TypeError, ValueError):
            pass
    if isinstance(body.get("narrator"), dict):
        st["narrator"] = {"voice": str(body["narrator"].get("voice") or ""),
                          "instruct": str(body["narrator"].get("instruct") or "")}
    if isinstance(body.get("characters"), list):
        st["characters"] = [story_mod._clean_char(c) for c in body["characters"]
                            if isinstance(c, dict)]
    if isinstance(body.get("places"), list):
        st["places"] = [story_mod._clean_place(p) for p in body["places"] if isinstance(p, dict)]
    if isinstance(body.get("chapters"), list):
        st["chapters"] = body["chapters"]
    story_mod.renumber(st)
    if "format" in body:
        data["format"] = _norm_format(body["format"])
    if "title" in body:
        data["title"] = str(body["title"]).strip()
    _save_project(pid, data)
    return jsonify(_story_view(pid, data))


@app.post("/api/story/<pid>/write")
def api_story_write(pid):
    """AI chia chương, lập nhân vật/địa điểm, viết lời kể và chia cảnh (chạy nền)."""
    from core import story as story_mod
    try:
        data, st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    if not (st.get("title") or "").strip() and not (st.get("brief") or "").strip():
        return _err("Gõ yêu cầu (vd 'làm đoạn phim về chương 1 truyện Lão Hạc') hoặc tên truyện.")
    if _status(pid).get("state") in ("writing", "rendering", "drawing"):
        return jsonify({"ok": True, "already": True})
    with JOBS_LOCK:
        JOBS[pid] = {"state": "writing", "progress": 0.0, "message": "bắt đầu", "log": []}

    def work():
        try:
            story_mod.write_story(st, progress=lambda f, m: _set_status(
                pid, progress=round(float(f), 3), message=str(m)))
            d2, _ = _load_story(pid)
            d2["story"] = st
            _save_project(pid, d2)
            _set_status(pid, state="written", progress=1.0, message="đã viết xong lời kể")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            _set_status(pid, state="error", message=f"Viết lời kể lỗi: {_short_err(e, 400)}")

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.get("/api/story/<pid>/prompts")
def api_story_prompts(pid):
    """Tải bộ câu lệnh vẽ (.txt) để dán vào công cụ vẽ tranh."""
    from core import story as story_mod
    try:
        data, st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    if not story_mod.all_scenes(st):
        return _err("Chưa có cảnh nào — bấm 'AI viết lời kể' trước.")
    p = config.project_dir(pid) / "out" / "cau_lenh_ve.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    ref = (story_mod.image_dir(config.project_dir(pid)) / story_mod.STYLE_REF).exists()
    p.write_text(story_mod.prompts_text(st, data.get("format") or "16:9", ref),
                 encoding="utf-8")
    return send_file(str(p), mimetype="text/plain; charset=utf-8", as_attachment=True,
                     download_name=f"cau_lenh_ve_{pid}.txt")


@app.post("/api/story/<pid>/images")
def api_story_images(pid):
    """Nhận nhiều ảnh cùng lúc; tên file có số cảnh (scene_001.png, 001.jpg...)."""
    from core import story as story_mod
    try:
        data, _st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    d = story_mod.image_dir(config.project_dir(pid))
    saved, skipped = [], []
    for f in request.files.getlist("files"):
        name = Path(f.filename or "").name
        if Path(name).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            skipped.append(name)
            continue
        m = story_mod._NUM.search(Path(name).stem)
        if not m and not name.startswith("char_"):
            skipped.append(name)
            continue
        if m and not name.startswith("char_"):
            sid = f"{int(m.group(1)):03d}"
            for old in d.glob(f"scene_{sid}.*"):        # thay ảnh cũ của cảnh đó
                old.unlink(missing_ok=True)
            name = f"scene_{sid}{Path(name).suffix.lower()}"
        f.save(str(d / name))
        saved.append(name)
    out = _story_view(pid, data)
    out.update({"saved": saved, "skipped": skipped})
    return jsonify(out)


@app.post("/api/story/<pid>/style_ref")
def api_story_style_ref(pid):
    """Ảnh mẫu phong cách (vd một khung hình kênh chị thích): gửi kèm mọi lần vẽ."""
    from PIL import Image
    from core import story as story_mod
    try:
        data, _st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    f = request.files.get("file")
    dest = story_mod.image_dir(config.project_dir(pid)) / story_mod.STYLE_REF
    if request.form.get("remove"):
        dest.unlink(missing_ok=True)
        return jsonify(_story_view(pid, data))
    if not f:
        return _err("Chưa chọn ảnh.")
    try:
        Image.open(f.stream).convert("RGB").save(dest)
    except Exception:  # noqa: BLE001
        return _err("Không đọc được ảnh (chị thử ảnh JPG, PNG hoặc WEBP).")
    return jsonify(_story_view(pid, data))


@app.get("/api/story/<pid>/style_ref")
def api_story_style_ref_get(pid):
    from core import story as story_mod
    p = story_mod.image_dir(config.project_dir(pid)) / story_mod.STYLE_REF
    if not p.exists():
        return _err("Chưa có ảnh mẫu.", 404)
    return send_file(str(p), as_attachment=request.args.get("dl") == "1",
                     download_name="style_ref.png")


def _png(img):
    import io
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.get("/api/story/<pid>/char/<cid>.png")
def api_story_char_png(pid, cid):
    """Ảnh xem trước nhân vật tool vẽ."""
    from core import story_live
    try:
        _data, st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    c = next((c for c in st.get("characters") or [] if c.get("id") == cid), None)
    if not c:
        return _err("Không có nhân vật.", 404)
    from core import film_rig
    return _png(story_live.character_preview(c, 300, film_rig.style_of(st)))


@app.get("/api/story/<pid>/place/<plid>.png")
def api_story_place_png(pid, plid):
    from core import story_live
    try:
        _data, st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    p = next((p for p in st.get("places") or [] if p.get("id") == plid), None)
    if not p:
        return _err("Không có địa điểm.", 404)
    return _png(story_live.place_preview(p, p.get("time") or "ngay", (480, 270)))


@app.get("/api/story/<pid>/preview/<sid>.png")
def api_story_preview_png(pid, sid):
    """Khung xem trước một cảnh tool vẽ (nhân vật đang làm gì, ở đâu)."""
    from core import story as story_mod, story_live
    try:
        data, st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    sc = next((sc for _ci, sc in story_mod.all_scenes(st) if sc.get("id") == sid), None)
    if not sc:
        return _err("Không có cảnh.", 404)
    W, H = config.frame_size(data.get("format") or "16:9")
    k = 480 / max(W, H)
    if st.get("mode") == "film":
        from core import film as film_m
        img = film_m.preview(st, sc, (int(W * k), int(H * k)), pdir=config.project_dir(pid))
    else:
        img = story_live.preview(st, sc, (int(W * k), int(H * k)), 3.2,
                                 pdir=config.project_dir(pid))
    return _png(img)


# ----------------------------------------------- bộ phận AI vẽ thêm (Truyện kể)

def _part_view(p: dict) -> dict:
    return {"id": p["id"], "kind": p["kind"], "name": p.get("name", ""), "desc": p.get("desc", "")}


@app.get("/api/doodle/parts")
def api_doodle_parts():
    from core import doodle_parts
    return jsonify({"parts": [_part_view(p) for p in doodle_parts.load().values()],
                    "kinds": doodle_parts.KINDS})


@app.post("/api/doodle/parts")
def api_doodle_part_new():
    """AI vẽ một bộ phận mới (mũ, hoa văn áo, con vật, bối cảnh) và lưu vào thư viện."""
    from core import doodle_parts
    body = request.get_json(silent=True) or {}
    kind, name = body.get("kind"), str(body.get("name") or "").strip()
    if kind not in doodle_parts.KINDS or not name:
        return _err("Chọn loại và nhập tên thứ cần vẽ.")
    try:
        part = doodle_parts.design(kind, name, str(body.get("desc") or "").strip(),
                                   pid=body.get("id") or None)
    except Exception as e:  # noqa: BLE001
        return _err(f"AI chưa vẽ được: {_short_err(e)}")
    return jsonify({"part": _part_view(part)})


@app.post("/api/doodle/parts/<part_id>/redraw")
def api_doodle_part_redraw(part_id):
    from core import doodle_parts
    old = doodle_parts.get(part_id)
    if not old:
        return _err("Không có bộ phận này.", 404)
    body = request.get_json(silent=True) or {}
    desc = str(body.get("desc") or old.get("desc") or "")
    try:
        part = doodle_parts.design(old["kind"], old.get("name") or part_id, desc, pid=part_id)
    except Exception as e:  # noqa: BLE001
        return _err(f"AI chưa vẽ được: {_short_err(e)}")
    return jsonify({"part": _part_view(part)})


@app.delete("/api/doodle/parts/<part_id>")
def api_doodle_part_delete(part_id):
    from core import doodle_parts
    return jsonify({"ok": doodle_parts.delete_part(part_id)})


@app.get("/api/doodle/part/<part_id>.png")
def api_doodle_part_png(part_id):
    from core import doodle_parts
    p = doodle_parts.get(part_id)
    if not p:
        return _err("Không có bộ phận này.", 404)
    return _png(doodle_parts.preview(p))


@app.get("/api/story/<pid>/image/<sid>")
def api_story_image(pid, sid):
    from core import story as story_mod
    p = story_mod.scene_images(config.project_dir(pid)).get(str(sid))
    if not p:
        return _err("Chưa có ảnh.", 404)
    return send_file(str(p))


@app.post("/api/story/<pid>/char_sample")
def api_story_char_sample(pid):
    """Ảnh nhân vật mẫu: Claude xem ảnh, rút ra nét vẽ (tỉ lệ, mắt, nét viền) và
    ngoại hình; truyện dùng kiểu nhân vật 'Theo ảnh mẫu'."""
    from PIL import Image
    try:
        data, st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    f = request.files.get("file")
    if not f:
        return _err("Chưa chọn ảnh.")
    from core import story as story_mod
    try:
        img = Image.open(f.stream).convert("RGB")
    except Exception:  # noqa: BLE001
        return _err("Không đọc được ảnh (thử JPG, PNG, WEBP).")
    img.thumbnail((1400, 1400))
    dest = story_mod.image_dir(config.project_dir(pid)) / "char_sample.png"
    img.save(dest)
    look = Path(claude_cli._claude_dir()) / f"mau_{uuid.uuid4().hex[:8]}.png"
    small = img.copy()
    small.thumbnail((768, 768))
    small.save(look)
    try:
        res = claude_cli.style_from_photo(look)
    except Exception as e:  # noqa: BLE001
        return _err(f"Claude chưa xem được ảnh: {_short_err(e)}")
    finally:
        look.unlink(missing_ok=True)
    if not res:
        return _err("Claude không phân tích được ảnh.")
    st["char_sample"] = dict(res, image=str(dest))
    st["char_style"] = "sample"
    style_lib.backup(st, data.get("title") or "")       # lưu vào thư viện kiểu nhân vật
    _save_project(pid, data)
    return jsonify(_story_view(pid, data))


@app.get("/api/story/<pid>/char_sample.png")
def api_story_char_sample_png(pid):
    from core import story as story_mod
    try:
        _data, st = _load_story(pid)
        img = (st.get("char_sample") or {}).get("image")
    except FileNotFoundError:
        img = None
    p = Path(img) if img and Path(img).exists() else \
        story_mod.image_dir(config.project_dir(pid)) / "char_sample.png"
    if not p.exists():
        return _err("Chưa có ảnh mẫu.", 404)
    return send_file(str(p))


@app.post("/api/story/<pid>/sync_audio")
def api_story_sync_audio(pid):
    """Ảnh theo lời: nhận file giọng có sẵn (mp3, wav, m4a, mp4...)."""
    from core import sync as sync_m
    try:
        data, st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    f = request.files.get("file")
    if not f or not f.filename:
        return _err("Chưa chọn file giọng.")
    tmp = config.DATA / "tmp" / uuid.uuid4().hex[:8]
    tmp.mkdir(parents=True, exist_ok=True)
    p = tmp / Path(f.filename).name
    f.save(str(p))
    try:
        info = sync_m.save_audio(config.project_dir(pid), p)
    except Exception as e:  # noqa: BLE001
        return _err(_short_err(e))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    st["sync"] = dict(st.get("sync") or {}, **info)
    _save_project(pid, data)
    return jsonify(_story_view(pid, data))


@app.post("/api/story/<pid>/sync_split")
def api_story_sync_split(pid):
    """Nghe giọng, chia câu, AI viết câu lệnh vẽ (chạy nền)."""
    from core import sync as sync_m
    try:
        data, st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    if not (st.get("sync") or {}).get("audio"):
        return _err("Tải file giọng lên trước.")
    if _status(pid).get("state") in ("writing", "rendering", "drawing"):
        return jsonify({"ok": True, "already": True})
    with JOBS_LOCK:
        JOBS[pid] = {"state": "writing", "progress": 0.0, "message": "bắt đầu", "log": []}

    def work():
        try:
            sync_m.build(st, config.project_dir(pid), data.get("language") or "vi",
                         progress=lambda f, m: _set_status(pid, progress=round(float(f), 3),
                                                           message=str(m)))
            d2, _ = _load_story(pid)
            d2["story"] = st
            _save_project(pid, d2)
            _set_status(pid, state="written", progress=1.0,
                        message=f"đã chia {len(story_count(st))} câu")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            _set_status(pid, state="error", message=f"Chia câu lỗi: {_short_err(e, 400)}")

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


def story_count(st):
    from core import story as story_mod
    return story_mod.all_scenes(st)


@app.post("/api/story/<pid>/sync_draw")
def api_story_sync_draw(pid):
    """Stable Diffusion vẽ ảnh từng câu (chạy nền). body: ids (không có = câu
    chưa có ảnh), force (vẽ lại)."""
    from core import bg3d, sync as sync_m
    try:
        data, st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    if not bg3d.installed():
        return _err("Chưa cài phần vẽ ảnh AI. Chạy cai_3d.bat một lần (tải khoảng 7 GB).")
    if _status(pid).get("state") in ("writing", "rendering", "drawing"):
        return jsonify({"ok": True, "already": True})
    body = request.get_json(silent=True) or {}
    only = [str(x) for x in body.get("ids") or []] or None
    with JOBS_LOCK:
        JOBS[pid] = {"state": "drawing", "progress": 0.0,
                     "message": "nạp mô hình vẽ (lần đầu mất 1–2 phút)", "log": []}

    def work():
        try:
            made = sync_m.draw(st, config.project_dir(pid), config.frame_size(data.get("format") or "16:9"),
                               only, bool(body.get("force")),
                               progress=lambda f, m: _set_status(pid, progress=round(float(f), 3),
                                                                 message=str(m)))
            d2, _ = _load_story(pid)
            d2["story"] = st
            _save_project(pid, d2)
            _set_status(pid, state="drawn", progress=1.0, message=f"đã vẽ {len(made)} ảnh")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            _set_status(pid, state="error", message=f"Vẽ ảnh lỗi: {_short_err(e, 400)}")
        finally:
            bg3d.unload()

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/story/<pid>/bg3d")
def api_story_bg3d(pid):
    """Vẽ bối cảnh 3D cho các địa điểm (chạy nền). body: places (id, không có =
    mọi địa điểm còn thiếu), force (vẽ lại)."""
    from core import bg3d
    try:
        data, st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    if not bg3d.installed():
        return _err("Chưa cài phần vẽ 3D. Chạy cai_3d.bat một lần (tải khoảng 7 GB) rồi mở lại tool.")
    if _status(pid).get("state") in ("writing", "rendering", "drawing"):
        return jsonify({"ok": True, "already": True})
    body = request.get_json(silent=True) or {}
    only = [str(x) for x in body.get("places") or []] or None
    force = bool(body.get("force"))
    with JOBS_LOCK:
        JOBS[pid] = {"state": "drawing", "progress": 0.0,
                     "message": "nạp mô hình vẽ 3D (lần đầu mất 1–2 phút)", "log": []}

    def work():
        try:
            made = bg3d.draw_story(st, config.project_dir(pid),
                                   config.frame_size(data.get("format") or "16:9"), only, force,
                                   progress=lambda f, m: _set_status(
                                       pid, progress=round(float(f), 3), message=str(m)))
            d2, _ = _load_story(pid)
            d2["story"]["places"] = st["places"]
            _save_project(pid, d2)
            _set_status(pid, state="drawn", progress=1.0,
                        message=f"đã vẽ {len(made)} bối cảnh 3D" if made else "bối cảnh 3D đã đủ")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            _set_status(pid, state="error", message=f"Vẽ bối cảnh 3D lỗi: {_short_err(e, 400)}")
        finally:
            bg3d.unload()

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.get("/api/story/<pid>/bg3d/<name>.png")
def api_story_bg3d_png(pid, name):
    from core import bg3d
    p = config.project_dir(pid) / bg3d.DIR / f"{Path(name).name}.png"
    if not p.exists():
        return _err("Chưa vẽ.", 404)
    if request.args.get("w"):
        img = bg3d.load_cover(p, (480, 270))
        return _png(img)
    return send_file(str(p))


@app.post("/api/story/<pid>/render")
def api_story_render(pid):
    """Đọc lời kể (OmniVoice) rồi dựng video truyện kể (chạy nền)."""
    from core import story as story_mod
    from core import story_render
    try:
        data, st = _load_story(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    if not story_mod.all_scenes(st):
        return _err("Chưa có cảnh nào — bấm 'AI viết lời kể' trước.")
    if _status(pid).get("state") in ("writing", "rendering", "drawing"):
        return jsonify({"ok": True, "already": True})
    with JOBS_LOCK:
        JOBS[pid] = {"state": "rendering", "progress": 0.0, "message": "bắt đầu", "log": []}

    def work():
        try:
            pdir = config.project_dir(pid)
            settings = config.load_settings()
            lang = data.get("language") or "vi"
            if st.get("bg_mode") == "ai3d" and st.get("visual", "tool") == "tool":
                from core import bg3d
                try:
                    bg3d.draw_story(st, pdir, config.frame_size(data.get("format") or "16:9"),
                                    progress=lambda f, m: _set_status(pid, progress=0.0, message=str(m)))
                    d2, _ = _load_story(pid)
                    d2["story"]["places"] = st["places"]          # hạt giống đã dùng
                    _save_project(pid, d2)
                except Exception as e:  # noqa: BLE001
                    traceback.print_exc()
                    _set_status(pid, message=f"Không vẽ được bối cảnh 3D ({_short_err(e)}); "
                                             "dùng bối cảnh vẽ tay cho chỗ còn thiếu.")
                finally:
                    bg3d.unload()                    # trả bộ nhớ card cho OmniVoice
            if st.get("mode") == "sync":
                from core import bg3d, sync as sync_m
                if bg3d.installed():                     # ảnh còn thiếu: vẽ trước
                    try:
                        sync_m.draw(st, pdir, config.frame_size(data.get("format") or "16:9"),
                                    progress=lambda f, m: _set_status(pid, progress=0.0, message=str(m)))
                    except Exception as e:  # noqa: BLE001
                        traceback.print_exc()
                        _set_status(pid, message=f"Không vẽ được ảnh ({_short_err(e)}); ảnh thiếu "
                                                 "sẽ hiện khung chữ tạm.")
                    finally:
                        bg3d.unload()
                mp4 = sync_m.render(st, pdir, data.get("format") or "16:9", settings,
                                    progress=lambda f, m: _set_status(
                                        pid, progress=round(float(f), 3), message=str(m)))
                d2, _ = _load_story(pid)
                d2["result"] = {"video": str(mp4)}
                _save_project(pid, d2)
                _set_status(pid, state="done", progress=1.0, message="xong")
                return
            if st.get("mode") == "film":
                from core import film_render
                faud = film_render.voices(st, pdir, lang, progress=lambda f, m: _set_status(
                    pid, progress=round(0.4 * float(f), 3), message=str(m)))
                mp4 = film_render.render(st, pdir, data.get("format") or "16:9", settings, faud,
                                         progress=lambda f, m: _set_status(
                                             pid, progress=round(0.4 + 0.6 * float(f), 3),
                                             message=str(m)))
                d2, _ = _load_story(pid)
                d2["result"] = {"video": str(mp4)}
                _save_project(pid, d2)
                _set_status(pid, state="done", progress=1.0, message="xong")
                return
            audio = story_mod.narrate(st, pdir, lang, progress=lambda f, m: _set_status(
                pid, progress=round(0.4 * float(f), 3), message=str(m)))
            lines = story_mod.narrate_lines(st, pdir, lang, progress=lambda f, m: _set_status(
                pid, progress=round(0.4 + 0.05 * float(f), 3), message=str(m)))
            mp4 = story_render.render(st, pdir, data.get("format") or "16:9", settings, audio,
                                      progress=lambda f, m: _set_status(
                                          pid, progress=round(0.45 + 0.55 * float(f), 3), message=str(m)),
                                      lines=lines)
            d2, _ = _load_story(pid)
            d2["result"] = {"video": str(mp4)}
            _save_project(pid, d2)
            _set_status(pid, state="done", progress=1.0, message="xong")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            _set_status(pid, state="error", message=f"Dựng video lỗi: {_short_err(e, 400)}")

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


# ------------------------------------------------------------ truyện webtoon
# Tab riêng: truyện tranh động kiểu webtoon Hàn (nhân vật người thật, cận mặt,
# chèn màn hình điện thoại); AI viết truyện + phân cảnh, tool tự vẽ và diễn.

def _load_webtoon(pid: str) -> tuple[dict, dict]:
    from core import webtoon_film as wf
    data = _load_project(pid)
    if data.get("mode") != "webtoon":
        raise FileNotFoundError(f"'{pid}' không phải truyện webtoon")
    return data, data.setdefault("webtoon", wf.default_story())


def _webtoon_view(pid: str, data: dict) -> dict:
    from core import webtoon_art as wa, webtoon_film as wf, webtoon_pics as wpic
    out = dict(data)
    out["pics_needed"] = wpic.needed(data.get("webtoon") or {})
    out["status"] = _status(pid)
    out["video_ready"] = (config.PROJECTS / pid / "out" / "video.mp4").exists()
    out["options"] = {
        "genres": [[k, v] for k, v in wf.GENRES.items()], "langs": [[k, v] for k, v in wf.LANGS.items()],
        "types": list(wf.SHOT_TYPES), "cameras": list(wf.CAMERAS), "exprs": list(wa.EXPRS),
        "poses": list(wa.POSES), "hairs": list(wa.HAIRS), "hair_colors": list(wa.HAIR),
        "tops": list(wa.TOPS), "colors": list(wa.CLOTH), "skins": list(wa.SKIN),
        "kinds": [[k, v] for k, v in wf.PLACE_KINDS.items()],
        "screens": ["chat", "call", "wifi", "notice", "alert", "video", "noise", "lock", "loading", "app"],
    }
    return out


@app.post("/api/webtoon")
def api_webtoon_new():
    from core import webtoon_film as wf
    body = request.get_json(silent=True) or {}
    pid = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    wt = wf.default_story()
    for k in ("brief", "genre", "language"):
        if body.get(k):
            wt[k] = body[k]
    data = {"id": pid, "mode": "webtoon", "title": (body.get("title") or "").strip(),
            "language": wt["language"], "format": "16:9", "webtoon": wt,
            "assets": {"characters": [], "background": None, "voices": {}},
            "state": "draft", "created_at": datetime.now().isoformat(timespec="seconds")}
    config.project_dir(pid)
    _save_project(pid, data)
    return jsonify(_webtoon_view(pid, data))


@app.post("/api/webtoon/ideas")
def api_webtoon_ideas():
    """Gợi ý ý tưởng truyện (mỗi lần một loạt mới, không lặp các ý đã gợi ý)."""
    from core import webtoon_film as wf
    body = request.get_json(silent=True) or {}
    try:
        items = wf.ideas(str(body.get("genre") or ""), str(body.get("language") or "ko"),
                         body.get("avoid") if isinstance(body.get("avoid"), list) else [])
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return _err(f"AI gợi ý lỗi: {_short_err(e, 300)}")
    return jsonify({"ideas": items})


@app.get("/api/webtoon/list")
def api_webtoon_list():
    out = []
    for p in sorted(config.PROJECTS.glob("*/project.json"), reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if d.get("mode") == "webtoon":
            out.append({"id": d["id"], "title": d.get("title") or (d.get("webtoon") or {}).get("title")
                        or "(chưa đặt tên)", "created_at": d.get("created_at")})
    return jsonify({"items": out[:60]})


@app.get("/api/webtoon/<pid>")
def api_webtoon_get(pid):
    try:
        data, _ = _load_webtoon(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    return jsonify(_webtoon_view(pid, data))


@app.post("/api/webtoon/<pid>/save")
def api_webtoon_save(pid):
    from core import webtoon_art as wa, webtoon_film as wf
    try:
        data, wt = _load_webtoon(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    body = request.get_json(silent=True) or {}
    for k in ("title", "brief", "prev_summary", "hook"):
        if k in body:
            wt[k] = str(body[k] or "")
    if body.get("genre") in wf.GENRES:
        wt["genre"] = body["genre"]
    if body.get("language") in wf.LANGS:
        wt["language"] = data["language"] = body["language"]
    for k, lo, hi in (("minutes", 1, 20), ("part", 1, 99)):
        if k in body:
            try:
                wt[k] = max(lo, min(hi, float(body[k]) if k == "minutes" else int(body[k])))
            except (TypeError, ValueError):
                pass
    for k in ("subtitles", "cliffhanger"):
        if k in body:
            wt[k] = bool(body[k])
    if isinstance(body.get("narrator"), dict):
        wt["narrator"] = {"voice": str(body["narrator"].get("voice") or ""),
                          "instruct": str(body["narrator"].get("instruct") or "")}
    if isinstance(body.get("characters"), list):
        wt["characters"] = [{"id": wf.wa_slug(c.get("id") or c.get("name")), "name": str(c.get("name") or ""),
                             "look": wa.Look.from_dict(c.get("look")).to_dict(),
                             "voice": {"voice": str((c.get("voice") or {}).get("voice") or ""),
                                       "instruct": str((c.get("voice") or {}).get("instruct") or "")},
                             "home": str(c.get("home") or next((x.get("home") for x in wt.get("characters") or []
                                                                if x.get("id") == c.get("id")), "") or "")}
                            for c in body["characters"] if isinstance(c, dict)][:8]
    if isinstance(body.get("places"), list):
        wt["places"] = [{"id": wf.wa_slug(p.get("id") or p.get("name")), "name": str(p.get("name") or ""),
                         "kind": p.get("kind") if p.get("kind") in wf.PLACE_KINDS else "phong_khach",
                         "time": "dem" if p.get("time") == "dem" else "ngay"}
                        for p in body["places"] if isinstance(p, dict)][:10]
    if isinstance(body.get("shots"), list):
        ids = {c["id"] for c in wt.get("characters") or []}
        wt["shots"] = [wf.clean_shot(s, ids, k) for k, s in enumerate(body["shots"]) if isinstance(s, dict)]
    if wt.get("title"):
        data["title"] = wt["title"]
    _save_project(pid, data)
    return jsonify(_webtoon_view(pid, data))


@app.post("/api/webtoon/<pid>/write")
def api_webtoon_write(pid):
    from core import webtoon_film as wf
    try:
        data, wt = _load_webtoon(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    if _status(pid).get("state") in ("writing", "rendering"):
        return jsonify({"ok": True, "already": True})
    with JOBS_LOCK:
        JOBS[pid] = {"state": "writing", "progress": 0.0, "message": "bắt đầu", "log": []}

    def work():
        try:
            wf.write(wt, progress=lambda f, m: _set_status(pid, progress=round(float(f), 3), message=str(m)))
            d2, _ = _load_webtoon(pid)
            d2["webtoon"] = wt
            d2["title"] = wt.get("title") or d2.get("title")
            _save_project(pid, d2)
            _set_status(pid, state="written", progress=1.0, message="đã viết xong")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            _set_status(pid, state="error", message=f"AI viết lỗi: {_short_err(e, 400)}")

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.get("/api/webtoon/<pid>/preview/<int:i>.png")
def api_webtoon_preview(pid, i):
    import io
    from core import webtoon_film as wf
    try:
        _, wt = _load_webtoon(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    try:
        t = float(request.args.get("t") or 0.6)
    except ValueError:
        t = 0.6
    im = wf.preview(wt, i, (640, 360), t, config.PROJECTS / pid)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.get("/api/webtoon/<pid>/char/<cid>.png")
def api_webtoon_char(pid, cid):
    import io
    from PIL import Image
    from core import webtoon_art as wa
    try:
        _, wt = _load_webtoon(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    c = next((c for c in wt.get("characters") or [] if c["id"] == cid), None)
    if not c:
        return _err("Không thấy nhân vật.", 404)
    have = (wt.get("pics") or {}).get(cid) or {}
    if have:                                     # có ảnh AI: dùng ảnh gốc làm ảnh đại diện
        p = _pic_path(pid, cid, "down" if "down" in have else next(iter(have)))
        if p.exists():
            im = Image.open(p).convert("RGBA")
            im.thumbnail((240, 300))
            bg = Image.new("RGBA", (240, 300), (236, 234, 228, 255))
            bg.alpha_composite(im, ((240 - im.width) // 2, 300 - im.height))
            buf = io.BytesIO()
            bg.convert("RGB").save(buf, "PNG")
            buf.seek(0)
            return send_file(buf, mimetype="image/png")
    fig = wa.Figure(wa.Look.from_dict(c.get("look")))
    W, H = 240, 300
    s = H * 0.9 / fig.b["H"]
    im = wa.render(fig, wa.State(expr="neutral"), (W, H), (W / 2, H * 0.96), s, 1.6,
                   Image.new("RGB", (W, H), (236, 234, 228)))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


def _pic_path(pid: str, cid: str, key: str) -> Path:
    from core import webtoon_pics as wpic
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,60}", cid or "") or not re.fullmatch(r"[A-Za-z0-9_\-]{1,60}", key or ""):
        raise ValueError("Tên ảnh không hợp lệ.")
    return config.PROJECTS / pid / wpic.PICS_DIR / cid / f"{key}.png"


@app.post("/api/webtoon/<pid>/pic/<cid>/<key>")
def api_webtoon_pic_upload(pid, cid, key):
    """Tải ảnh AI của nhân vật cho một tư thế (+ nét mặt): tách nền, tự tìm mắt / miệng."""
    from core import webtoon_pics as wpic
    try:
        data, wt = _load_webtoon(pid)
        dst = _pic_path(pid, cid, key)
    except (FileNotFoundError, ValueError) as e:
        return _err(str(e), 404)
    f = request.files.get("file")
    if not f or not f.filename:
        return _err("Chưa chọn ảnh.")
    tmp = dst.with_suffix(".upload")
    dst.parent.mkdir(parents=True, exist_ok=True)
    f.save(str(tmp))
    try:
        meta = wpic.process(tmp, dst)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return _err(f"Không đọc được ảnh: {_short_err(e, 200)}")
    finally:
        tmp.unlink(missing_ok=True)
    wt.setdefault("pics", {}).setdefault(cid, {})[key] = meta
    _save_project(pid, data)
    return jsonify(_webtoon_view(pid, data))


@app.get("/api/webtoon/<pid>/pics_prompts.txt")
def api_webtoon_pics_prompts(pid):
    """Tải file câu lệnh vẽ: mỗi dòng một câu lệnh (?cid= một nhân vật, ?all=1 lấy cả ảnh đã có)."""
    import io
    from core import webtoon_pics as wpic
    try:
        _, wt = _load_webtoon(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    cid = request.args.get("cid") or None
    text = wpic.prompts_text(wt, cid, missing=request.args.get("all") != "1")
    if not text:
        return _err("Không còn ảnh nào cần vẽ.", 404)
    buf = io.BytesIO(text.encode("utf-8"))
    name = f"cau_lenh_ve_{cid or 'tat_ca'}.txt"
    return send_file(buf, mimetype="text/plain; charset=utf-8", as_attachment=True, download_name=name)


@app.get("/api/webtoon/<pid>/pic/<cid>/<key>.png")
def api_webtoon_pic_get(pid, cid, key):
    try:
        p = _pic_path(pid, cid, key)
    except ValueError as e:
        return _err(str(e), 404)
    if not p.exists():
        return _err("Chưa có ảnh.", 404)
    return send_file(str(p), mimetype="image/png", max_age=0)


@app.post("/api/webtoon/<pid>/pic/<cid>/<key>/marks")
def api_webtoon_pic_marks(pid, cid, key):
    """Chị chỉnh lại điểm mắt / miệng (toạ độ px trong ảnh đã xử lý)."""
    from core import webtoon_pics as wpic
    try:
        data, wt = _load_webtoon(pid)
        p = _pic_path(pid, cid, key)
    except (FileNotFoundError, ValueError) as e:
        return _err(str(e), 404)
    meta = ((wt.get("pics") or {}).get(cid) or {}).get(key)
    if not meta or not p.exists():
        return _err("Chưa có ảnh.", 404)
    body = request.get_json(silent=True) or {}
    try:
        eyes = [[float(x), float(y)] for x, y in body["eyes"]] if body.get("eyes") else None
        mouth = [float(body["mouth"][0]), float(body["mouth"][1])] if body.get("mouth") else None
    except (TypeError, ValueError, KeyError, IndexError):
        return _err("Điểm đánh dấu không hợp lệ.")
    wt["pics"][cid][key] = wpic.remark(p, meta, eyes, mouth)
    _save_project(pid, data)
    return jsonify(_webtoon_view(pid, data))


@app.post("/api/webtoon/<pid>/pic/<cid>/<key>/delete")
def api_webtoon_pic_delete(pid, cid, key):
    try:
        data, wt = _load_webtoon(pid)
        p = _pic_path(pid, cid, key)
    except (FileNotFoundError, ValueError) as e:
        return _err(str(e), 404)
    p.unlink(missing_ok=True)
    ((wt.get("pics") or {}).get(cid) or {}).pop(key, None)
    _save_project(pid, data)
    return jsonify(_webtoon_view(pid, data))


@app.post("/api/webtoon/<pid>/render")
def api_webtoon_render(pid):
    from core import webtoon_film as wf
    try:
        data, wt = _load_webtoon(pid)
    except FileNotFoundError as e:
        return _err(str(e), 404)
    if not wt.get("shots"):
        return _err("Chưa có cảnh quay nào — bấm 'AI viết truyện & phân cảnh' trước.")
    if _status(pid).get("state") in ("writing", "rendering"):
        return jsonify({"ok": True, "already": True})
    with JOBS_LOCK:
        JOBS[pid] = {"state": "rendering", "progress": 0.0, "message": "bắt đầu", "log": []}

    def work():
        try:
            pdir = config.project_dir(pid)
            audio = wf.narrate(wt, pdir, progress=lambda f, m: _set_status(
                pid, progress=round(0.35 * float(f), 3), message=str(m)))
            mp4 = wf.render(wt, pdir, (1920, 1080), audio, out_name="video.mp4",
                            progress=lambda f, m: _set_status(pid, progress=round(0.35 + 0.65 * float(f), 3),
                                                              message=str(m)))
            d2, _ = _load_webtoon(pid)
            d2["result"] = {"video": str(mp4)}
            _save_project(pid, d2)
            _set_status(pid, state="done", progress=1.0, message="xong")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            _set_status(pid, state="error", message=f"Dựng video lỗi: {_short_err(e, 400)}")

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


def main() -> None:
    host = "127.0.0.1"
    port = 8766
    print(f"\n  Tool hoat hinh hai thoai")
    print(f"  Mo trinh duyet: http://{host}:{port}\n")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
