# -*- coding: utf-8 -*-
"""Web server chạy trên máy chị: http://127.0.0.1:8766

Ba màn hình: Tập mới / Thư viện / Cài đặt. Mọi việc nặng (tạo giọng, dựng
video, gọi Claude) chạy ở luồng nền để giao diện không bị treo.
"""
from __future__ import annotations

import json
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
from core import capcut_export, photo_rig, rig as core_rig  # noqa: E402
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


def _draw_scene_bg(data: dict, pdir: Path, desc: str, hint: str = "") -> tuple[dict, str | None]:
    """Claude chọn mẫu + màu cho cảnh, tool vẽ và lưu. Trả về (bản ghi, cảnh báo)."""
    from core import scene_art
    warn = None
    try:
        bg = claude_cli.design_background(data.get("script", ""),
                                          data.get("language", "ko"),
                                          desc or hint)
    except Exception as e:  # noqa: BLE001
        warn = f"Claude chọn bối cảnh '{desc or 'chung'}' lỗi ({e}); dùng mẫu mặc định."
        bg = {}
    if not bg:
        bg = {"name": desc or "boi_canh", "kind": "phong_khach", "time": "ngay"}
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


def _fit_scene_bgs(data: dict, pdir: Path) -> bool:
    """Đổi khung (9:16 <-> 16:9...) thì vẽ lại các nền do tool vẽ cho đúng
    khung mới (ảnh tải lên thì để nguyên, lúc dựng sẽ cắt cho vừa).
    Trả về True nếu có nền được vẽ lại."""
    from core import scene_art
    size = list(config.frame_size(data.get("format")))
    recs = [data["assets"].get("background")]
    recs += list((data["assets"].get("backgrounds") or {}).values())
    changed = False
    for rec in recs:
        if not rec or not rec.get("kind"):
            continue
        if rec.get("size") == size and Path(rec.get("image") or "").exists():
            continue
        spec = rec.get("spec") or {"kind": rec.get("kind"), "time": rec.get("time"),
                                   "name": rec.get("name", "")}
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
        "tts_engines": tts_plugin.list_engines(),
    })


@app.get("/api/claude-calls")
def api_claude_calls():
    """Số lần đã gọi Claude trong phiên làm việc của server."""
    return jsonify({"count": claude_cli.call_count()})


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
    return jsonify(cur)


@app.get("/api/check-system")
def api_check_system():
    """Kiểm tra: GPU NVIDIA, ffmpeg, claude CLI."""
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
    redrawn = _fit_scene_bgs(data, config.project_dir(pid))
    _save_project(pid, data)
    return jsonify({"ok": True, "format": data.get("format"),
                    "duration": data.get("duration"), "redrawn": redrawn})


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
    # kịch bản có '# ngon_ngu:' thì theo kịch bản (chọn kiểu nhân vật Hàn/Mỹ)
    has_lang = "ngon_ngu" in (data.get("script") or "")
    language = s.language if has_lang else data.get("language", "ko")
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
            warnings.append(f"Claude chọn bộ ghép lỗi ({e}); dùng mặc định.")
            specs = {}
        style = config.load_settings().get("char_style") or "auto"
        if style not in character_kit.STYLES:      # "auto": theo ngôn ngữ của tập
            style = "khand" if language == "ko" else "gray"   # Anh, Việt -> người xám TikTok
        for i, name in enumerate(want_chars):
            spec_d = specs.get(name) or {}
            spec_d["name"] = name
            spec_d["style"] = style
            spec = character_kit.CharSpec.from_dict(spec_d)
            exprs = sorted({b.expression for b in s.beats
                            if b.speaker == name} | {"neutral"})
            sheet = character_kit.build_sheet(
                spec, pdir / "assets" / "kit" / assets.config_slug(name), exprs
            )
            first = sheet.get("neutral") or next(iter(sheet.values()))
            made.append({
                "name": name,
                "side": s.sides.get(name, ["trai", "phai", "giua"][min(i, 2)]),
                "mode": "kit",
                "spec": spec.to_dict(),
                "images": sheet,
                "expressions": list(sheet),
                "image": first.get("dong"),
                "mouth_open": first.get("mo"),
                "mouth_closed": first.get("dong"),
            })
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
                warnings.append(f"Claude mô tả giọng lỗi ({e}).")
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
    out = config.project_dir(pid) / "out" / "video.mp4"
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


def main() -> None:
    host = "127.0.0.1"
    port = 8766
    print(f"\n  Tool hoat hinh hai thoai")
    print(f"  Mo trinh duyet: http://{host}:{port}\n")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
