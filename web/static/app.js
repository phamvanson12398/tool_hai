/* ============================================================
   Tool hoạt hình hài thoại — app.js
   Vanilla JS, không framework, không CDN.
   ============================================================ */

(function () {
  "use strict";

  /* ----------------------------- State ----------------------------- */

  var state = {
    meta: null,
    settings: null,
    library: null,
    project: null,     // {id, title, language, kind, ...}
    scriptDirty: false,
    parseTimer: null,
    parseSeq: 0,
    review: [],        // suggestions from last review
    pollTimer: null,
    bgmObjectUrl: null,
    bgmPristine: true, // true nếu user chưa đổi file (vẫn là file server)
    projectTouched: false
  };

  var LS_TAB = "tanh_tab";
  var LS_TITLE = "tanh_title";

  /* ----------------------------- Utils ----------------------------- */

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function debounce(fn, ms) {
    var t = null;
    return function () {
      var args = arguments, self = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(self, args); }, ms);
    };
  }

  function ext(name) {
    var m = /\.([A-Za-z0-9]+)$/.exec(name || "");
    return m ? m[1].toLowerCase() : "";
  }

  function baseName(name) {
    return (name || "").replace(/\.[A-Za-z0-9]+$/, "");
  }

  function humanSize(bytes) {
    if (!bytes && bytes !== 0) return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
  }

  /* ----------------------------- Toast ----------------------------- */

  function toast(type, title, body, ms) {
    var wrap = $("toasts");
    if (!wrap) return;
    var t = el("div", "toast " + (type || ""));
    var ttl = el("div", "toast-title", title || "");
    t.appendChild(ttl);
    if (body) t.appendChild(el("div", "toast-body", body));
    wrap.appendChild(t);
    var life = ms || (type === "error" ? 6500 : 3400);
    setTimeout(function () {
      t.style.transition = "opacity .3s, transform .3s";
      t.style.opacity = "0";
      t.style.transform = "translateY(8px)";
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 320);
    }, life);
  }

  function errToast(prefix, err) {
    var msg = err && err.message ? err.message : String(err);
    toast("error", prefix || "Lỗi", msg);
  }

  /* ----------------------------- API ------------------------------- */

  function apiError(res, data) {
    var msg = "HTTP " + res.status;
    if (data && (data.error || data.message || data.detail)) {
      msg = data.error || data.message || data.detail;
      if (typeof msg !== "string") msg = JSON.stringify(msg);
    } else if (res.status === 404) {
      msg = "Không tìm thấy tài nguyên (404)";
    }
    var e = new Error(msg);
    e.status = res.status;
    e.data = data;
    return e;
  }

  function api(path, opts) {
    opts = opts || {};
    var headers = opts.headers || {};
    var body = opts.body;
    if (body && !(body instanceof FormData) && typeof body !== "string") {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    return fetch(path, {
      method: opts.method || (body ? "POST" : "GET"),
      headers: headers,
      body: body
    }).then(function (res) {
      if (res.status === 204) return { ok: true };
      var ct = res.headers.get("content-type") || "";
      var p;
      if (ct.indexOf("json") >= 0) p = res.json().catch(function () { return null; });
      else p = res.text().catch(function () { return ""; });

      return p.then(function (data) {
        if (!res.ok) throw apiError(res, data);
        return data;
      });
    }, function (netErr) {
      throw new Error("Không kết nối được tới server (" + (netErr && netErr.message || "network") + "). Server đã chạy chưa?");
    });
  }

  function qs(params) {
    if (!params) return "";
    var parts = [];
    Object.keys(params).forEach(function (k) {
      if (params[k] === undefined || params[k] === null) return;
      parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(params[k]));
    });
    return parts.length ? ("?" + parts.join("&")) : "";
  }

  /* --------------------- Buttons busy/spinner ---------------------- */

  function withBusy(btn, fn) {
    if (!btn || btn.dataset.busy === "1") return;
    btn.dataset.busy = "1";
    btn.disabled = true;
    var sp = btn.querySelector(".spinner");
    if (sp) sp.hidden = false;
    var done = function () {
      btn.dataset.busy = "";
      btn.disabled = false;
      if (sp) sp.hidden = true;
    };
    var r;
    try { r = fn(); } catch (e) { done(); throw e; }
    if (r && typeof r.then === "function") {
      return r.then(function (v) { done(); return v; }, function (e) { done(); throw e; });
    }
    done();
    return r;
  }

  function emptyState(container, icon, text) {
    // el() chỉ nhận chữ (textContent): ghép phần tử con bằng appendChild,
    // không truyền phần tử vào el() (sẽ hiện "[object HTMLDivElement]")
    var box = el("div", "empty");
    var wrap = document.createElement("div");
    wrap.appendChild(el("span", "empty-icon", icon || ""));
    wrap.appendChild(document.createTextNode(text || "Chưa có gì"));
    box.appendChild(wrap);
    container.appendChild(box);
  }

  /* ---------------------------- Meta ------------------------------- */

  function labelForLang(code) {
    if (state.meta && state.meta.languages) {
      for (var i = 0; i < state.meta.languages.length; i++) {
        if (state.meta.languages[i].code === code) return state.meta.languages[i].label;
      }
    }
    return code;
  }

  function kindName(lang, kindId) {
    if (!state.meta || !state.meta.comedy_kinds || !state.meta.comedy_kinds[lang]) return kindId;
    var arr = state.meta.comedy_kinds[lang];
    for (var i = 0; i < arr.length; i++) if (arr[i].id === kindId) return arr[i].name;
    return kindId;
  }

  function populateLanguages() {
    var sel = $("p-language");
    var vd = $("vd-language");
    [sel, vd].forEach(function (s) {
      if (!s) return;
      s.innerHTML = "";
      (state.meta.languages || []).forEach(function (l) {
        var o = document.createElement("option");
        o.value = l.code;
        o.textContent = l.label;
        s.appendChild(o);
      });
      if (!s.options.length) {
        ["ko", "en", "vi"].forEach(function (c) {
          var o = document.createElement("option");
          o.value = c; o.textContent = c; s.appendChild(o);
        });
      }
    });
    // mảng index
    if (state.meta.languages && state.meta.languages.length > 1) {
      sel.value = state.meta.languages[1].code; // Tiếng Anh là mặc định
    }
    populateKinds();
    updateVoiceDesignLang();
  }

  function updateVoiceDesignLang() {
    var vd = $("vd-language");
    var sel = $("p-language");
    if (!vd || !sel) return;
    var code = sel.value;
    var has = false;
    for (var i = 0; i < vd.options.length; i++) {
      if (vd.options[i].value === code) { has = true; break; }
    }
    if (!has) return;
    vd.value = code;
  }

  function populateKinds() {
    var sel = $("p-kind");
    var lang = $("p-language") ? $("p-language").value : "en";
    var kinds = (state.meta.comedy_kinds && state.meta.comedy_kinds[lang]) || [];
    sel.innerHTML = "";
    kinds.forEach(function (k) {
      var o = document.createElement("option");
      o.value = k.id;
      o.textContent = k.name;
      sel.appendChild(o);
    });
    var custom = document.createElement("option");
    custom.value = "__custom__";
    custom.textContent = "Tự chọn";
    sel.appendChild(custom);
    sel.selectedIndex = 0;
    updateKindHow();
  }

  function updateKindHow() {
    var sel = $("p-kind");
    var wrap = $("kind-how-wrap");
    var how = $("kind-how");
    if (sel.value === "__custom__") { wrap.hidden = true; return; }
    var lang = $("p-language").value;
    var kinds = (state.meta.comedy_kinds && state.meta.comedy_kinds[lang]) || [];
    for (var i = 0; i < kinds.length; i++) {
      if (kinds[i].id === sel.value && kinds[i].how) {
        how.textContent = kinds[i].how;
        wrap.hidden = false;
        return;
      }
    }
    wrap.hidden = true;
  }

  var SUBTITLE_LABELS = {yellow: "Vàng", white: "Trắng", green: "Xanh lá", pink: "Hồng"};

  function populateSubtitleStyles() {
    var sel = $("s-subtitle");
    if (!sel) return;
    sel.innerHTML = "";
    (state.meta.subtitle_styles || []).forEach(function (s) {
      var o = document.createElement("option");
      o.value = s;
      o.textContent = SUBTITLE_LABELS[s] || s;
      sel.appendChild(o);
    });
    showTarget();
    updateSubtitleSwatch();
  }

  function updateSubtitleSwatch() {
    var sw = $("subtitle-swatch");
    if (!sw) return;
    var v = $("s-subtitle").value || "yellow";
    sw.className = "subtitle-swatch style-" + v;
    sw.textContent = "Xin chào! 안녕하세요";
  }

  /* -------------------------- Project ------------------------------ */

  function projectLabel() {
    if (!state.project || !state.project.id) return "Chưa có tập nào";
    var title = $("p-title").value.trim() || state.project.title || "(không tên)";
    var lang = $("p-language") ? $("p-language").value : "";
    return state.project.id + " · " + title + " · " + labelForLang(lang);
  }

  /* ---------------------- Khung + thời lượng ----------------------- */

  function formatValue() { return ($("p-format") && $("p-format").value) || "9:16"; }

  function durationValue() {
    var v = parseInt(($("p-duration") && $("p-duration").value) || "", 10);
    if (!v || v <= 0) return null;
    return Math.max(15, Math.min(600, v));
  }

  var FORMAT_SIZES = { "9:16": "1080×1920", "16:9": "1920×1080", "1:1": "1080×1080" };

  /** Giống config.stage_layout: chân đứng, chiều cao người, vị trí ngang. */
  function stageLayout(fmt) {
    if (fmt === "16:9") return { ratio: 16 / 9, floor: 0.90, height: [0.68, 0.60],
      slots: { 1: [0.5], 2: [0.33, 0.67], 3: [0.24, 0.5, 0.76] } };
    if (fmt === "1:1") return { ratio: 1, floor: 0.88, height: [0.62, 0.54],
      slots: { 1: [0.5], 2: [0.29, 0.71], 3: [0.2, 0.5, 0.8] } };
    return { ratio: 9 / 16, floor: 0.80, height: [0.50, 0.42],
      slots: { 1: [0.5], 2: [0.27, 0.73], 3: [0.18, 0.5, 0.82] } };
  }

  function targetRange() {
    var d = (state.project && state.project.duration) || durationValue();
    if (d) return [Math.round(d * 0.85), Math.round(d * 1.15)];
    return state.meta && state.meta.target_duration ? state.meta.target_duration : [30, 90];
  }

  function showTarget() {
    var td = targetRange();
    var pill = $("est-target");
    if (pill) pill.textContent = "Mục tiêu " + td[0] + "–" + td[1] + "s";
  }

  /** Đưa khung + thời lượng của tập lên form. */
  function fillMetaFields(p) {
    if (!p) return;
    if ($("p-format")) $("p-format").value = p.format || "9:16";
    if ($("p-duration")) $("p-duration").value = p.duration ? String(p.duration) : "";
    showTarget();
  }

  function saveMeta() {
    showTarget();
    updateDurationPill();
    updateStageFromProject();
    var p = state.project || {};
    if (!p.id) return Promise.resolve();
    return api("/api/project/" + encodeURIComponent(p.id) + "/meta", {
      method: "POST", body: { format: formatValue(), duration: durationValue() }
    }).then(function (r) {
      if (r && r.redrawn) toast("ok", "Đã vẽ lại bối cảnh", "Cho vừa khung " + r.format);
      return refreshProject();
    }).catch(function (e) { errToast("Lưu khung / thời lượng thất bại", e); });
  }

  function ensureProject(force) {
    if (state.project && state.project.id && !force) return Promise.resolve(state.project);
    var title = $("p-title").value.trim();
    var language = $("p-language").value;
    if (!title) title = "Tập chưa đặt tên";
    var kind = $("p-kind").value;
    if (kind === "__custom__") kind = "";
    return api("/api/project", {
      method: "POST",
      body: { title: title, language: language, kind: kind,
              format: formatValue(), duration: durationValue() }
    }).then(function (p) {
      state.project = p;
      state.projectTouched = false;
      $("project-badge").textContent = projectLabel();
      renderProjectKv();
      saveTitleLocal();
      return p;
    });
  }

  function touchProject() {
    if (state.project && state.project.id) {
      state.projectTouched = true;
    }
    saveTitleLocal();
  }

  function saveTitleLocal() {
    try {
      var t = $("p-title").value;
      if (t) localStorage.setItem(LS_TITLE, t);
    } catch (e) {}
  }

  function renderProjectKv() {
    var p = state.project || {};
    $("kv-id").textContent = p.id || "—";
    $("kv-title").textContent = p.title || ($("p-title").value || "—");
    $("kv-lang").textContent = labelForLang(p.language || $("p-language").value);
    $("kv-kind").textContent = p.kind ? kindName(p.language, p.kind) : "—";
    $("kv-state").textContent = p.state || "draft";
    var est = p.estimate_duration;
    $("kv-duration").textContent = (typeof est === "number") ? (est.toFixed(1) + "s") : "—";
    $("project-badge").textContent = projectLabel();
  }

  /* --------------------- Script validation ------------------------- */

  function estimateSeconds(text) {
    if (!text) return 0;
    var secs = 0;
    text.split("\n").forEach(function (raw) {
      var line = raw.trim();
      if (!line) return;
      if (line.charAt(0) === "#") return;
      if (line.charAt(0) === ">") {
        var m = /([0-9]+(?:\.[0-9]+)?)\s*$/.exec(line);
        var d = m ? parseFloat(m[1]) : 0.8;
        if (isFinite(d)) secs += d;
        return;
      }
      var body = line.replace(/^[^:]*[:]\s*/, ""); // bỏ "tên (cảm): "
      var chars = body.replace(/\s+/g, " ").trim().length;
      secs += Math.max(1.6, chars / 4.6);
    });
    return secs;
  }

  function renderIssues(container, list, isError) {
    container.innerHTML = "";
    (list || []).forEach(function (it) {
      var d = typeof it === "string" ? { message: it } : (it || {});
      var cls = isError ? "error" : "warn";
      var row = el("div", "issue " + cls);
      var body = el("div", "issue-body", d.message || d.text || d.error || String(it));
      if (d.line != null) {
        row.appendChild(body);
        row.appendChild(el("span", "issue-loc", "dòng " + d.line));
      } else {
        row.appendChild(body);
      }
      container.appendChild(row);
    });
  }

  function updateDurationPill() {
    var text = $("p-script").value;
    var secs = estimateSeconds(text);
    var pill = $("est-duration");
    pill.textContent = "≈ " + secs.toFixed(0) + "s";
    var td = targetRange();
    pill.className = "pill " + (secs >= td[0] && secs <= td[1] ? "ok" : (secs === 0 ? "" : "warn"));
    if (secs === 0) pill.textContent = "≈ 0s";
    var kv = $("kv-duration");
    if (kv) kv.textContent = secs.toFixed(1) + "s";
  }

  var runParse = function () {
    var text = $("p-script").value;
    if (!text.trim()) {
      renderIssues($("script-errors"), []);
      renderIssues($("script-warnings"), []);
      updateDurationPill();
      return;
    }
    var seq = ++state.parseSeq;
    api("/api/parse-script", { method: "POST", body: { script: text } })
      .then(function (data) {
        if (seq !== state.parseSeq) return; // bỏ kết quả cũ
        renderIssues($("script-errors"), data && data.errors, true);
        renderIssues($("script-warnings"), data && data.warnings, false);
        if (state.project && state.project.id && data && data.scenes) {
          state.project.parse = state.project.parse || {};
          state.project.parse.scenes = data.scenes;
          state.project.parse.scene_cast = data.scene_cast || [];
          renderScenes();
          updateStageFromProject();
        }
        if (data && typeof data.estimate_duration === "number" &&
            !$("p-script").dataset.localEst) {
          // Ước lượng server nếu có — hiển thị cho khớp backend
        }
      })
      .catch(function () {
        // parse-script lỗi thì vẫn giữ ước lượng local
      });
    updateDurationPill();
  };

  var scheduleParse = debounce(runParse, 600);

  function onScriptInput() {
    updateDurationPill();
    scheduleParse();
    touchProject();
    if (state.review.length) {
      state.review = [];
      $("review-list").innerHTML = "";
      $("review-apply-wrap").hidden = true;
    }
  }

  function saveScriptToServer() {
    if (!state.project || !state.project.id) {
      toast("warn", "Chưa có tập", "Bấm “Tạo tập” trước khi lưu kịch bản.");
      return;
    }
    var btn = $("btn-save-script");
    withBusy(btn, function () {
      return api("/api/project/" + encodeURIComponent(state.project.id) + "/script", {
        method: "POST",
        body: { script: $("p-script").value }
      }).then(function (data) {
        if (data && typeof data === "object") {
          if (data.parse) {
            renderIssues($("script-errors"), data.parse.errors, true);
            renderIssues($("script-warnings"), data.parse.warnings, false);
          }
          if (typeof data.estimate_duration === "number") {
            state.project.estimate_duration = data.estimate_duration;
          }
          if (data.state) state.project.state = data.state;
          renderProjectKv();
        }
        toast("ok", "Đã lưu kịch bản");
        saveTitleLocal();
      }).catch(function (e) { errToast("Lưu thất bại", e); });
    });
  }

  /* --------------------------- Write ------------------------------- */

  function collectWriteBody() {
    var kind = $("p-kind").value;
    return {
      title: $("p-title").value.trim(),
      language: $("p-language").value,
      kind: kind === "__custom__" ? "" : kind,
      hints: $("p-hints").value.trim(),
      duration: durationValue()
    };
  }

  function applyScript(script) {
    $("p-script").value = script || "";
    onScriptInput();
    runParse();
    $("p-script").scrollTop = 0;
  }

  function doWrite(extraHints) {
    var body = collectWriteBody();
    if (extraHints) body.hints = (body.hints ? body.hints + " | " : "") + extraHints;
    return ensureProject().then(function (p) {
      return api("/api/project/" + encodeURIComponent(p.id) + "/write", {
        method: "POST",
        body: body
      });
    }).then(function (data) {
      applyScript(data && data.script);
      toast("ok", "Đã viết kịch bản");
      return data;
    });
  }

  /* --------------------------- Ideas ------------------------------- */

  function renderIdeas(list) {
    var box = $("ideas-list");
    box.innerHTML = "";
    if (!list || !list.length) {
      emptyState(box, "💡", "Chưa có hướng nào — bấm “3 hướng khác”");
      return;
    }
    list.forEach(function (idea) {
      var item = el("div", "item is-clickable");
      var head = el("div", "item-head");
      if (idea.kind) head.appendChild(el("span", "pill", idea.kind));
      head.appendChild(el("span", "item-title", idea.kind_id || ""));
      item.appendChild(head);
      item.appendChild(el("div", "item-body", idea.pitch || ""));
      item.appendChild(el("div", "item-meta", "Bấm để viết kịch bản theo hướng này"));
      item.addEventListener("click", function () {
        withBusy($("btn-write"), function () {
          return doWrite("hướng hài: " + (idea.kind || idea.kind_id || "") + " — " + (idea.pitch || ""));
        }).catch(function (e) { errToast("Viết thất bại", e); });
      });
      box.appendChild(item);
    });
  }

  /* -------------------------- Trends ------------------------------- */

  function renderTrends(list) {
    var box = $("trends-list");
    box.innerHTML = "";
    if (!list || !list.length) {
      emptyState(box, "📈", "Chưa lấy được trend nào");
      return;
    }
    list.forEach(function (t) {
      var item = el("div", "item is-clickable");
      var head = el("div", "item-head");
      head.appendChild(el("span", "item-title", t.title || "(không tên)"));
      item.appendChild(head);
      // format là cả một đoạn mô tả: hiện như đoạn văn (xuống dòng được),
      // không nhét vào nhãn nhỏ một dòng làm tràn khung
      if (t.format) {
        var fm = el("div", "item-body item-format");
        fm.appendChild(el("b", "", "Cách làm: "));
        fm.appendChild(document.createTextNode(t.format));
        item.appendChild(fm);
      }
      if (t.why) {
        var why = el("div", "item-body");
        why.appendChild(el("b", "", "Vì sao đang lên: "));
        why.appendChild(document.createTextNode(t.why));
        item.appendChild(why);
      }
      var meta = el("div", "item-meta", (t.found_at ? "Tìm thấy: " + t.found_at + " · " : "") +
                    "Bấm để viết kịch bản theo trend này");
      item.appendChild(meta);
      if (t.sources && t.sources.length) {
        var src = el("div", "item-sources");
        src.appendChild(document.createTextNode("Nguồn: "));
        t.sources.forEach(function (u, i) {
          if (i) src.appendChild(document.createTextNode(" · "));
          var a = document.createElement("a");
          a.href = u;
          var host = "";
          try { host = new URL(u).hostname.replace(/^www\./, ""); } catch (e) { host = ""; }
          a.textContent = host || ("nguồn " + (i + 1));
          a.title = u;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.addEventListener("click", function (e) { e.stopPropagation(); });
          src.appendChild(a);
        });
        item.appendChild(src);
      }
      item.addEventListener("click", function () {
        withBusy($("btn-write"), function () {
          return doWrite("bám trend: " + (t.title || "") + (t.format ? " (" + t.format + ")" : "") +
            (t.why ? " — " + t.why : ""));
        }).catch(function (e) { errToast("Viết thất bại", e); });
      });
      box.appendChild(item);
    });
  }

  /* -------------------------- Review ------------------------------- */

  var CATEGORY_VI = {
    punchline: "điểm hài",
    naturalness: "tự nhiên",
    length: "độ dài",
    character: "nhân vật",
    policy: "chính sách",
    repeat: "trùng lặp"
  };
  var SEVERITY_VI = { low: "nhẹ", medium: "vừa", high: "nặng" };

  function renderReview(list) {
    var box = $("review-list");
    box.innerHTML = "";
    state.review = list || [];
    $("review-apply-wrap").hidden = !state.review.length;
    if (!state.review.length) {
      emptyState(box, "🧐", "Chưa có góp ý nào — bấm “Rà soát bằng AI”");
      return;
    }
    state.review.forEach(function (s) {
      var item = el("div", "item");
      var line = el("label", "checkline");

      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = true;
      cb.dataset.sugId = String(s.id);

      var right = el("div");
      var head = el("div", "item-head");
      head.appendChild(el("span", "pill",
        (CATEGORY_VI[s.category] || s.category || "") +
        (s.severity ? " · " + (SEVERITY_VI[s.severity] || s.severity) : "")));
      head.appendChild(el("span", "item-title", "#" + s.id));
      right.appendChild(head);

      if (s.quote) right.appendChild(el("div", "item-quote", s.quote));
      if (s.suggestion) right.appendChild(el("div", "item-body", s.suggestion));

      line.appendChild(cb);
      line.appendChild(right);
      item.appendChild(line);
      box.appendChild(item);
    });
  }

  function applyReview() {
    var boxes = $("review-list").querySelectorAll("input[data-sug-id]");
    var ids = [], items = [];
    Array.prototype.forEach.call(boxes, function (b) {
      if (!b.checked) return;
      ids.push(b.dataset.sugId);
      state.review.forEach(function (s) {
        if (String(s.id) === b.dataset.sugId) items.push(s);
      });
    });
    if (!ids.length) {
      toast("warn", "Chưa chọn góp ý", "Hãy chọn ít nhất một góp ý để áp dụng.");
      return;
    }
    withBusy($("btn-apply"), function () {
      return api("/api/project/" + encodeURIComponent(state.project.id) + "/apply", {
        method: "POST",
        body: { ids: ids, items: items, script: $("p-script").value }
      }).then(function (data) {
        applyScript(data && data.script);
        renderReview([]);
        toast("ok", "Đã áp dụng " + ids.length + " góp ý");
      }).catch(function (e) { errToast("Áp dụng thất bại", e); });
    });
  }

  /* -------------------------- Uploads ------------------------------ */

  var pending = { characters: [], background: [], voices: [] };

  function zoneState(kind) {
    return kind === "background" ? pending.background : pending[kind];
  }

  function setFiles(kind, fileList) {
    var arr = Array.prototype.slice.call(fileList || []);
    if (kind === "background") pending.background = arr.slice(0, 1);
    else pending[kind] = pending[kind].concat(arr);
    renderThumbs();
  }

  function renderThumbs() {
    var box = $("upload-thumbs");
    box.innerHTML = "";
    var all = pending.characters.concat(pending.background, pending.voices);
    all.forEach(function (f, idx) {
      var t = el("div", "thumb");
      var kind = idx < pending.characters.length ? "characters"
        : (idx < pending.characters.length + pending.background.length ? "background" : "voices");
      var localIdx = idx;
      if (kind === "background") localIdx = idx - pending.characters.length;
      else if (kind === "voices") localIdx = idx - pending.characters.length - pending.background.length;

      if (f.type && f.type.indexOf("image") === 0) {
        var img = document.createElement("img");
        img.src = URL.createObjectURL(f);
        img.alt = f.name;
        img.addEventListener("load", function () { URL.revokeObjectURL(img.src); });
        t.appendChild(img);
      } else {
        t.appendChild(el("div", "thumb-audio", "🎵"));
      }
      var lbl = el("div", "thumb-label", baseName(f.name) + " · " + humanSize(f.size));
      t.appendChild(lbl);

      var rm = el("button", "thumb-rm", "×");
      rm.type = "button";
      rm.title = "Bỏ file này";
      rm.textContent = "✕";
      rm.addEventListener("click", function () {
        pending[kind].splice(localIdx, 1);
        renderThumbs();
      });
      t.appendChild(rm);
      box.appendChild(t);
    });
  }

  function filenameToCharacter(fileName) {
    var base = baseName(fileName);
    var mo = /^(.+)_([A-Za-z0-9가-힣]+)_mo$/.exec(base);
    if (mo) return { name: mo[1], expression: mo[2], full: true };
    return { name: base, expression: null, full: false };
  }

  function renderParsedCharacters(charList) {
    var box = $("parsed-characters");
    box.innerHTML = "";
    if (!charList || !charList.length) {
      emptyState(box, "👤", "Chưa có nhân vật nào ở tập này");
      return;
    }
    charList.forEach(function (c) {
      var item = el("div", "item");
      var head = el("div", "item-head");
      head.appendChild(el("span", "item-title", c.name || "?"));
      if (c.side) head.appendChild(el("span", "pill", c.side));
      head.appendChild(el("span", "pill", c.mode === "set" ? "bộ ảnh" : "đơn ảnh"));
      item.appendChild(head);

      if (c.expressions && c.expressions.length) {
        item.appendChild(el("div", "item-meta",
          c.expressions.length + " biểu cảm: " + c.expressions.join(", ")));
      }
      if (c.warnings && c.warnings.length) {
        var w = el("div", "item-meta", "⚠ " + c.warnings.join(" · "));
        w.style.color = "var(--warn)";
        item.appendChild(w);
      }

      var saveBtn = el("button", "btn btn-sm", "Lưu vào thư viện");
      saveBtn.type = "button";
      saveBtn.addEventListener("click", function () {
        withBusy(saveBtn, function () {
          return api("/api/library/character/" + encodeURIComponent(c.name) + "/save", {
            method: "POST",
            body: {}
          }).then(function () {
            toast("ok", "Đã lưu " + c.name + " vào thư viện");
            loadLibrary();
          }).catch(function (e) { errToast("Lưu thất bại", e); });
        });
      });
      item.appendChild(saveBtn);
      box.appendChild(item);
    });
  }

  function uploadAssets() {
    if (!pending.characters.length && !pending.background.length && !pending.voices.length) {
      toast("warn", "Chưa có file", "Hãy chọn ảnh nhân vật / bối cảnh / giọng mẫu trước.");
      return;
    }
    var fd = new FormData();
    pending.characters.forEach(function (f) { fd.append("characters", f); });
    if (pending.background[0]) fd.append("background", pending.background[0]);
    pending.voices.forEach(function (f) { fd.append("voices", f); });

    // Tên hiển thị (nếu backend không suy ra được từ filename)
    var names = [];
    pending.characters.forEach(function (f) {
      var p = filenameToCharacter(f.name);
      if (names.indexOf(p.name) < 0) names.push(p.name);
    });
    pending.voices.forEach(function (f) {
      var n = baseName(f.name);
      if (names.indexOf(n) < 0) names.push(n);
    });
    if (names.length) fd.append("names", JSON.stringify(names));

    withBusy($("btn-upload"), function () {
      return ensureProject().then(function (p) {
        return api("/api/project/" + encodeURIComponent(p.id) + "/assets", {
          method: "POST",
          body: fd
        });
      }).then(function (data) {
        toast("ok", "Đã tải lên", "Đang lấy dữ liệu tập…");
        pending = { characters: [], background: [], voices: [] };
        renderThumbs();
        return refreshProject();
      }).catch(function (e) { errToast("Tải lên thất bại", e); });
    });
  }

  /* ------------------------- Generate ------------------------------ */

  function renderGeneratePreview(data) {
    var box = $("generate-preview");
    box.innerHTML = "";

    if (data.characters && data.characters.length) {
      var cast = el("div", "asset-cast");
      data.characters.forEach(function (c) {
        var card = el("div", "asset-card");
        var img = document.createElement("img");
        img.alt = c.name || "";
        img.src = c.image ? assetUrl(c.image) : "";
        if (!c.image) { img.removeAttribute("src"); }
        card.appendChild(img);
        card.appendChild(el("div", "ac-name", c.name || "?"));
        var redraw = el("button", "btn", "Vẽ lại");
        redraw.type = "button";
        redraw.addEventListener("click", function () { doGenerate([c.name]); });
        card.appendChild(redraw);
        cast.appendChild(card);
      });
      box.appendChild(cast);
    }

    if (data.background) {
      var bg = el("div", "asset-bg");
      if (data.background.image) {
        var bimg = document.createElement("img");
        bimg.alt = data.background.name || "bối cảnh";
        bimg.src = assetUrl(data.background.image);
        bg.appendChild(bimg);
      }
      var brow = el("div", "row-actions");
      brow.style.marginTop = "0";
      var bredraw = el("button", "btn btn-sm", "Vẽ lại bối cảnh");
      bredraw.type = "button";
      bredraw.addEventListener("click", function () {
        doGenerate(null, data.background.name || data.background.description || "");
      });
      brow.appendChild(bredraw);
      bg.appendChild(brow);
      box.appendChild(bg);
    }

    if (data.voices && typeof data.voices === "object") {
      var vp = el("div", "item-meta");
      var vnames = Object.keys(data.voices);
      vp.textContent = vnames.length
        ? ("Giọng: " + vnames.join(", "))
        : "";
      if (vnames.length) box.appendChild(vp);
    }

    updateStageFromProject();
  }

  function doGenerate(characters, background) {
    if (!state.project || !state.project.id) {
      toast("warn", "Chưa có tập", "Bấm “Tạo tập” ở mục 1 trước.");
      return;
    }
    withBusy($("btn-generate"), function () {
      return api("/api/project/" + encodeURIComponent(state.project.id) + "/generate", {
        method: "POST",
        body: background
          ? { characters: characters || [], scenes: [""], background: background, voices: true }
          : { characters: characters || scriptCharacterNames(),
              background: $("p-title").value + " / " + $("p-hints").value, voices: true }
      }).then(function (data) {
        (data && data.warnings || []).forEach(function (w) { toast("warn", "Lưu ý", w); });
        renderGeneratePreview(data || {});
        toast("ok", "AI đã tạo phần còn thiếu");
        return refreshProject();
      }).catch(function (e) { errToast("Tạo phần còn thiếu thất bại", e); });
    });
  }

  function scriptCharacterNames() {
    var text = $("p-script").value;
    var names = [];
    var m = /#\s*nhan_vat:\s*(.+)/i.exec(text);
    if (m) {
      m[1].split(",").forEach(function (pair) {
        var n = pair.split("=")[0].trim();
        if (n && names.indexOf(n) < 0) names.push(n);
      });
    }
    if (!names.length) {
      text.split("\n").forEach(function (line) {
        var d = /^\s*([^\s(:>#][^:()]{0,20})\s*\(/.exec(line);
        if (d) {
          var n = d[1].trim();
          if (n && names.indexOf(n) < 0) names.push(n);
        }
      });
    }
    if (!names.length) names = ["nhân vật chính"];
    return names;
  }

  /* --------------------- Bối cảnh từng cảnh ------------------------ */

  function sceneKey(desc) { return (desc || "").trim().toLowerCase(); }

  function sceneBg(assets, desc) {
    assets = assets || {};
    if (!sceneKey(desc)) return assets.background || null;
    return (assets.backgrounds || {})[sceneKey(desc)] || null;
  }

  function currentScenes() {
    // mỗi nơi một dòng (cùng nơi nhưng khác người có mặt vẫn chung ảnh nền)
    var p = state.project || {};
    var sc = (p.parse && p.parse.scenes) || [];
    var out = [], seen = {};
    sc.forEach(function (d) {
      var k = String(d || "").trim().toLowerCase();
      if (!seen[k]) { seen[k] = 1; out.push(d); }
    });
    return out.length ? out : [""];
  }

  /** Ai có mặt ở nơi này (null = mọi nhân vật). */
  function sceneCast(desc) {
    var p = state.project || {};
    var sc = (p.parse && p.parse.scenes) || [];
    var casts = (p.parse && p.parse.scene_cast) || [];
    var k = String(desc || "").trim().toLowerCase();
    var names = {}, any = false;
    for (var i = 0; i < sc.length; i++) {
      if (String(sc[i] || "").trim().toLowerCase() !== k) continue;
      if (!casts[i]) return null;
      casts[i].forEach(function (n) { names[n] = 1; });
      any = true;
    }
    return any ? Object.keys(names) : null;
  }

  function renderScenes() {
    var box = $("scene-list");
    if (!box) return;
    box.innerHTML = "";
    var p = state.project || {};
    if (!p.id) {
      emptyState(box, "🏞️", "Tạo tập và viết kịch bản trước");
      return;
    }
    var assets = p.assets || {};
    var scenes = currentScenes();
    if (state.sceneIdx == null || state.sceneIdx >= scenes.length) state.sceneIdx = 0;
    scenes.forEach(function (desc, i) {
      var rec = sceneBg(assets, desc);
      // cảnh chưa có ảnh riêng dùng bối cảnh chung (nếu có)
      var shown = rec || (sceneKey(desc) ? assets.background : null);
      var row = el("div", "scene-row" + (i === state.sceneIdx ? " active" : ""));
      var th = el("div", "scene-thumb", shown ? "" : "Chưa có ảnh");
      if (shown && shown.image) th.style.backgroundImage = "url('" + assetUrl(shown.image) + "')";
      th.title = "Xem trước cảnh này";
      th.addEventListener("click", function () {
        state.sceneIdx = i;
        renderScenes();
        updateStageFromProject();
      });
      row.appendChild(th);

      var body = el("div", "scene-body");
      body.appendChild(el("div", "scene-title",
        (scenes.length > 1 ? "Cảnh " + (i + 1) + ": " : "") + (desc || "Bối cảnh chung của tập")));
      var who = sceneCast(desc);
      if (who) body.appendChild(el("div", "scene-meta", "Có mặt: " + who.join(", ")));
      body.appendChild(el("div", "scene-meta", rec
        ? ("Ảnh: " + (rec.name || "") + (rec.kind ? " · mẫu " + rec.kind : "") + (rec.time === "dem" ? " · đêm" : ""))
        : (shown ? "Đang dùng bối cảnh chung" : "Chưa có ảnh — bấm AI vẽ hoặc tải ảnh lên")));

      var act = el("div", "scene-actions");
      var up = el("button", "btn btn-sm", "Tải ảnh lên");
      up.type = "button";
      up.addEventListener("click", function () {
        state.sceneUpload = desc;
        $("in-scene-bg").value = "";
        $("in-scene-bg").click();
      });
      var ai = el("button", "btn btn-sm", rec ? "AI vẽ lại" : "AI vẽ");
      ai.type = "button";
      ai.appendChild(el("span", "spinner"));
      ai.lastChild.hidden = true;
      ai.addEventListener("click", function () {
        withBusy(ai, function () {
          return api("/api/project/" + encodeURIComponent(p.id) + "/generate", {
            method: "POST",
            body: { characters: [], scenes: [desc], background: $("p-hints").value }
          }).then(function (data) {
            (data.warnings || []).forEach(function (w) { toast("warn", "Lưu ý", w); });
            toast("ok", "Đã vẽ bối cảnh", desc || "bối cảnh chung");
            state.sceneIdx = i;
            return refreshProject();
          }).catch(function (e) { errToast("Vẽ bối cảnh thất bại", e); });
        });
      });
      act.appendChild(up);
      act.appendChild(ai);
      body.appendChild(act);
      row.appendChild(body);
      box.appendChild(row);
    });
  }

  function uploadSceneBg(file) {
    var p = state.project || {};
    if (!file || !p.id) return;
    var fd = new FormData();
    fd.append("scene", state.sceneUpload || "");
    fd.append("file", file);
    api("/api/project/" + encodeURIComponent(p.id) + "/scene-bg", { method: "POST", body: fd })
      .then(function () {
        toast("ok", "Đã đổi ảnh nền", state.sceneUpload || "bối cảnh chung");
        return refreshProject();
      })
      .catch(function (e) { errToast("Tải ảnh nền thất bại", e); });
  }

  /** Tải lại dữ liệu tập từ server rồi vẽ lại các phần liên quan. */
  function refreshProject() {
    var p = state.project || {};
    if (!p.id) return Promise.resolve(null);
    // lưu kịch bản đang soạn (lặng lẽ) để server tính đúng danh sách cảnh
    var text = $("p-script").value;
    var save = (state.projectTouched && text.trim())
      ? api("/api/project/" + encodeURIComponent(p.id) + "/script",
            { method: "POST", body: { script: text } }).catch(function () {})
      : Promise.resolve();
    return save.then(function () {
      return api("/api/project/" + encodeURIComponent(p.id));
    }).then(function (data) {
      state.project = data;
      fillMetaFields(data);
      renderProjectKv();
      renderParsedCharacters((data.assets || {}).characters || []);
      renderScenes();
      updateStageFromProject();
      return data;
    });
  }

  /* ------------------------- Preview stage ------------------------- */

  function assetUrl(value) {
    if (!value) return "";
    if (/^(https?:|data:|blob:)/.test(value)) return value;
    if (/^\/(api|static)\//.test(value)) return value;
    // đường dẫn file trên máy (C:\... hoặc /home/...) -> server trả ảnh
    return "/api/library/image/" + encodeURIComponent(value);
  }

  function updateStageFromProject() {
    var p = state.project || {};
    var assets = p.assets || {};
    var stage = $("stage");
    var bg = $("stage-bg");
    var cast = $("stage-cast");
    var stageTitle = $("stage-title");
    var empty = $("stage-empty");

    // bối cảnh: cảnh đang chọn ở mục 8b (không có ảnh riêng thì dùng nền chung)
    var scenes = currentScenes();
    var sdesc = scenes[Math.min(state.sceneIdx || 0, scenes.length - 1)];
    var brec = sceneBg(assets, sdesc) || assets.background;
    if (brec && (brec.image || brec.id)) {
      bg.style.backgroundImage = "url('" + assetUrl(brec.image || brec.id) + "')";
    } else {
      bg.style.backgroundImage = "";
    }

    // tiêu đề cố định
    var fixed = (state.settings && state.settings.title_text) || $("stage-title.dataset.fixed") || "";
    stageTitle.textContent = state.settings && state.settings.title_text
      ? state.settings.title_text : "";

    // nhân vật
    cast.innerHTML = "";
    var chars = (assets.characters || []).slice();
    // chỉ người có mặt ở cảnh đang chọn (vd gọi điện: mỗi người một nơi)
    var here = sceneCast(sdesc);
    if (here) {
      var only = chars.filter(function (c) { return here.indexOf(c.name) >= 0; });
      if (only.length) chars = only;
    }
    var n = chars.length;
    // giống video: xếp trái -> giữa -> phải theo vị trí trong kịch bản
    var sides = (p.parse && p.parse.sides) || {};
    var order = { trai: 0, left: 0, giua: 1, center: 1, phai: 2, right: 2 };
    chars.sort(function (a, b) {
      var sa = order[String(sides[a.name] || a.side || "giua").toLowerCase()];
      var sb = order[String(sides[b.name] || b.side || "giua").toLowerCase()];
      return (sa == null ? 1 : sa) - (sb == null ? 1 : sb);
    });
    // khung + bố cục giống video (9:16, 16:9, 1:1)
    var fmtNow = (p && p.format) || formatValue();
    var lay = stageLayout(fmtNow);
    stage.style.aspectRatio = String(lay.ratio);
    stage.style.maxWidth = lay.ratio > 1 ? "100%" : (lay.ratio === 1 ? "380px" : "270px");
    var slots = lay.slots[n];
    var hpct = (n >= 3 ? lay.height[1] : lay.height[0]) * 100;
    chars.forEach(function (c, i) {
      var spr = el("div", "sprite");
      var x = slots ? slots[i] : (i + 1) / (n + 1);
      spr.style.left = (x * 100).toFixed(1) + "%";
      spr.style.bottom = ((1 - lay.floor) * 100).toFixed(1) + "%";
      spr.style.height = (hpct * Number(c.scale || 1)).toFixed(1) + "%";
      var img = document.createElement("img");
      img.alt = c.name || "";
      img.src = assetUrl(c.image);
      if (!c.image) img.removeAttribute("src");
      spr.appendChild(img);
      if (c.name) spr.appendChild(el("span", "sprite-name", c.name));
      cast.appendChild(spr);
    });

    var has = n > 0 || bg.style.backgroundImage;
    empty.style.display = has ? "none" : "";
    if (has) {
      var info = [];
      if (bg.style.backgroundImage) info.push("bối cảnh ✓");
      if (n) info.push(n + " nhân vật");
      $("stage-info").textContent = fmtNow + " · " + info.join(" · ");
    } else {
      $("stage-info").textContent = fmtNow + " · " + FORMAT_SIZES[fmtNow];
    }
  }

  /* -------------------------- Render job --------------------------- */

  function shortId(id) {
    var s = String(id || "");
    if (s.length > 8) return s.slice(0, 8);
    if (/^[0-9a-f-]{20,}/i.test(s)) return s.slice(0, 8);
    return s;
  }

  function setProgressVisible(v) {
    $("render-progress-wrap").hidden = !v;
  }

  function updateRenderStatus(st) {
    var pct = Math.round((st.progress || 0) * 100);
    $("render-progress-bar").style.width = pct + "%";
    $("render-pct").textContent = pct + "%";
    $("render-state").textContent = st.message || st.state || "";
    var logEl = $("render-log");
    if (st.log && st.log.length) {
      logEl.textContent = st.log.slice(-60).join("\n");
      logEl.scrollTop = logEl.scrollHeight;
    }
    if (state.project) {
      state.project.state = st.state;
      renderProjectKv();
    }
    // Chỉ coi là xong khi job báo "done" — lúc đang dựng lại, file video cũ
    // vẫn còn nên video_ready có thể đúng dù video mới chưa xong.
    if (st.state === "done") {
      stopPolling();
      showVideoOutput();
      toast("ok", "Video đã xong!", "Bấm “Tải mp4” hoặc xem ngay ở bên dưới.");
      loadHistoryOnDone();
    } else if (st.state === "error") {
      stopPolling();
      toast("error", "Dựng video lỗi", st.message || "Xem log để biết chi tiết.", 9000);
      setBusyRender(false);
    }
  }

  function startRender() {
    if (!state.project || !state.project.id) {
      toast("warn", "Chưa có tập", "Bấm “Tạo tập” ở mục 1 trước.");
      return;
    }
    if (state.projectTouched || !state.scriptDirtySafe()) {
      // lưu kịch bản trước
    }
    withBusy($("btn-render"), function () {
      return api("/api/project/" + encodeURIComponent(state.project.id) + "/script", {
        method: "POST",
        body: { script: $("p-script").value }
      }).then(function () {
        return api("/api/project/" + encodeURIComponent(state.project.id) + "/render", {
          method: "POST",
          body: {}
        });
      }).then(function () {
        $("render-output").hidden = true;
        $("render-progress-bar").style.width = "0%";
        $("render-pct").textContent = "0%";
        $("render-state").textContent = "bắt đầu dựng…";
        $("render-log").textContent = "";
        setProgressVisible(true);
        setBusyRender(true);
        toast("ok", "Bắt đầu dựng video", "Quá trình có thể mất vài phút.");
        state.pollDraftTries = 0;
        schedulePoll(0);
      }).catch(function (e) { errToast("Không dựng được video", e); });
    });
  }

  function setBusyRender(on) {
    var b = $("btn-render");
    b.disabled = !!on;
    b.dataset.busy = on ? "1" : "";
    var sp = b.querySelector(".spinner");
    if (sp) sp.hidden = !on;
    var lbl = b.querySelector(".btn-label");
    if (lbl) lbl.textContent = on ? "Đang dựng…" : "Xác nhận và dựng video";
  }

  function schedulePoll(delay) {
    clearTimeout(state.pollTimer);
    state.pollTimer = setTimeout(pollOnce, delay || 2000);
  }

  function pollOnce() {
    if (!state.project || !state.project.id) return;
    api("/api/project/" + encodeURIComponent(state.project.id) + "/status")
      .then(function (st) {
        st = st || {};
        updateRenderStatus(st);
        // dừng hẳn khi xong hoặc lỗi (trước đây vẫn hẹn lần sau nên video
        // bị gán lại nguồn và tải lại mỗi 2 giây)
        if (st.state === "rendering") {
          schedulePoll(2000);
        } else if (st.state === "draft" && (state.pollDraftTries = (state.pollDraftTries || 0) + 1) < 5) {
          // job vừa gửi mà server chưa kịp ghi trạng thái — thử thêm vài lần
          schedulePoll(2000);
        } else if (st.state !== "done" && st.state !== "error") {
          stopPolling();
        }
      })
      .catch(function (e) {
        schedulePoll(4000); // server có thể đang bận — thử lại
      });
  }

  function stopPolling() {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
    setBusyRender(false);
  }

  function showVideoOutput() {
    var out = $("render-output");
    var v = $("render-video");
    var sid = state.project.id;
    var bust = Date.now();
    v.src = "/api/project/" + encodeURIComponent(sid) + "/video?t=" + bust;
    $("dl-mp4").href = "/api/project/" + encodeURIComponent(sid) + "/video";
    $("dl-pack").href = "/api/project/" + encodeURIComponent(sid) + "/pack";
    out.hidden = false;
    resetCapcutExportResult();
    setProgressVisible(false);
  }

  /* ------------------ Xuất dự án CapCut (thử nghiệm) ------------------ */

  function resetCapcutExportResult() {
    var box = $("capcut-export-result");
    if (box) box.hidden = true;
    var msg = $("capcut-export-msg");
    if (msg) msg.textContent = "";
  }

  function exportCapcut() {
    var sid = state.project.id;
    if (!sid) return;
    var btn = $("btn-capcut-export");
    var box = $("capcut-export-result");
    var msg = $("capcut-export-msg");
    box.hidden = false;
    msg.textContent = "Đang tạo dự án CapCut...";
    withBusy(btn, function () {
      return api("/api/project/" + encodeURIComponent(sid) + "/capcut-export", {
        method: "POST", body: {}
      }).then(function (r) {
        msg.textContent = (r && r.message)
          || ("Đã tạo dự án CapCut “" + (r && r.name) + "”.");
        toast("ok", "Xuất dự án CapCut thành công", r && r.name, 6000);
        return r;
      }).catch(function (e) {
        // Bắt mọi lỗi: hiện rõ tiếng Việt, không để treo ứng dụng
        msg.textContent = e && e.message ? e.message : String(e);
        toast("error", "Không xuất được dự án CapCut",
          (e && e.message) || String(e), 8000);
        throw e;
      });
    });
  }

  function loadHistoryOnDone() {
    // Sau khi xong, lưu thông tin tập vào lịch sử để backend tổng hợp
    api("/api/history", {
      method: "POST",
      body: {
        id: state.project.id,
        title: $("p-title").value || state.project.title,
        language: state.project.language,
        kind: state.project.kind
      }
    }).catch(function () { /* không chặn luồng chính */ });
  }

  // helper để startRender đọc được cờ bẩn script (đặt prototype-ish)
  state.scriptDirtySafe = function () { return true; };

  /* -------------------------- Library ------------------------------ */

  function loadLibrary() {
    return api("/api/library").then(function (lib) {
      state.library = lib || {};
      renderLibrary();
      return state.library;
    }).catch(function (e) { errToast("Không tải được thư viện", e); });
  }

  function renderLibrary() {
    var lib = state.library || {};

    // Tab switching
    document.querySelectorAll('[data-tab]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var tab = this.getAttribute('data-tab');
        document.querySelectorAll('[data-tab]').forEach(function(b) {
          b.classList.remove('active');
        });
        this.classList.add('active');
        document.querySelectorAll('[data-tab-content]').forEach(function(el) {
          el.hidden = el.getAttribute('data-tab-content') !== tab;
        });
      });
    });

    // Characters
    var cb = $("lib-characters");
    cb.innerHTML = "";
    if (!lib.characters || !lib.characters.length) {
      emptyState(cb, "👤", "Chưa có nhân vật nào — bấm “Tải nhân vật lên”");
    } else {
      lib.characters.forEach(function (c) {
        var item = el("div", "grid-item");
        var img = document.createElement("img");
        img.className = "gi-img";
        img.alt = c.name || "";
        img.src = assetUrl(c.image);
        if (!c.image) { img.removeAttribute("src"); img.alt = "không có ảnh"; }
        item.appendChild(img);
        var body = el("div", "gi-body");
        var nm = el("div", "gi-name");
        nm.appendChild(document.createTextNode(c.name || "?"));
        if (c.side) nm.appendChild(el("span", "pill", c.side));
        body.appendChild(nm);
        body.appendChild(el("div", "gi-sub",
          (c.mode === "set" ? "bộ ảnh" : "đơn ảnh") +
          (c.expressions && c.expressions.length ? " · " + c.expressions.length + " biểu cảm" : "")));

        var act = el("div", "li-actions");

        // Nhân vật 1 ảnh: hiển thị nút chấm miệng nếu chưa có mouth_pos
        if (c.mode === "single" && c.image) {
          if (c.mouth_pos) {
            act.appendChild(el("span", "pill", "miệng: " + c.mouth_pos[0] + "," + c.mouth_pos[1]));
          } else {
            var mouthBtn = el("button", "btn btn-sm", "🎯 Chấm miệng");
            mouthBtn.type = "button";
            mouthBtn.addEventListener("click", function () {
              openMouthPicker(c.name, c.image);
            });
            act.appendChild(mouthBtn);
          }
        }

        // Đổi tên
        var renameBtn = el("button", "btn btn-sm", "✏️ Đổi tên");
        renameBtn.type = "button";
        renameBtn.addEventListener("click", function () {
          var nn = prompt("Tên mới cho nhân vật:", c.name);
          if (nn && nn.trim() && nn.trim() !== c.name) {
            withBusy(renameBtn, function () {
              return api("/api/library/character/" + encodeURIComponent(c.name) + "/rename", {
                method: "POST",
                body: { name: nn.trim() }
              }).then(function () {
                toast("ok", "Đã đổi tên");
                return loadLibrary();
              }).catch(function (e) { errToast("Đổi tên thất bại", e); });
            });
          }
        });
        act.appendChild(renameBtn);

        // Xoá
        var delBtn = el("button", "btn btn-sm btn-danger", "🗑️ Xoá");
        delBtn.type = "button";
        delBtn.addEventListener("click", function () {
          if (confirm("Xoá nhân vật '" + c.name + "'?")) {
            withBusy(delBtn, function () {
              return api("/api/library/character/" + encodeURIComponent(c.name), {
                method: "DELETE"
              }).then(function () {
                toast("ok", "Đã xoá");
                return loadLibrary();
              }).catch(function (e) { errToast("Xoá thất bại", e); });
            });
          }
        });
        act.appendChild(delBtn);

        body.appendChild(act);
        item.appendChild(body);
        cb.appendChild(item);
      });
    }

    // Backgrounds
    var bb = $("lib-backgrounds");
    bb.innerHTML = "";
    if (!lib.backgrounds || !lib.backgrounds.length) {
      emptyState(bb, "🏞️", "Chưa có bối cảnh nào");
    } else {
      lib.backgrounds.forEach(function (b) {
        var item = el("div", "grid-item");
        var img = document.createElement("img");
        img.className = "gi-img";
        img.alt = b.name || "";
        img.src = assetUrl(b.image || b.id);
        item.appendChild(img);
        var body = el("div", "gi-body");
        body.appendChild(el("div", "gi-name", b.name || b.id || "?"));

        var act = el("div", "li-actions");
        var renameBtn = el("button", "btn btn-sm", "✏️ Đổi tên");
        renameBtn.type = "button";
        renameBtn.addEventListener("click", function () {
          var nn = prompt("Tên mới cho bối cảnh:", b.name);
          if (nn && nn.trim() && nn.trim() !== b.name) {
            withBusy(renameBtn, function () {
              return api("/api/library/background/" + encodeURIComponent(b.id) + "/rename", {
                method: "POST",
                body: { name: nn.trim() }
              }).then(function () {
                toast("ok", "Đã đổi tên");
                return loadLibrary();
              }).catch(function (e) { errToast("Đổi tên thất bại", e); });
            });
          }
        });
        act.appendChild(renameBtn);

        var delBtn = el("button", "btn btn-sm btn-danger", "🗑️ Xoá");
        delBtn.type = "button";
        delBtn.addEventListener("click", function () {
          if (confirm("Xoá bối cảnh '" + (b.name || b.id) + "'?")) {
            withBusy(delBtn, function () {
              return api("/api/library/background/" + encodeURIComponent(b.id), {
                method: "DELETE"
              }).then(function () {
                toast("ok", "Đã xoá");
                return loadLibrary();
              }).catch(function (e) { errToast("Xoá thất bại", e); });
            });
          }
        });
        act.appendChild(delBtn);

        body.appendChild(act);
        item.appendChild(body);
        bb.appendChild(item);
      });
    }

    // Voices
    var vb = $("lib-voices");
    vb.innerHTML = "";
    var hasVoice = false;
    if (lib.voices && lib.voices.length) {
      lib.voices.forEach(function (v) {
        var langs = v.languages || {};
        var keys = Object.keys(langs);
        if (keys.length) hasVoice = true;
        var item = el("div", "list-item");
        var head = el("div", "li-head");
        head.appendChild(el("span", "li-name", v.name || "?"));
        keys.forEach(function (k) {
          head.appendChild(el("span", "pill", k));
        });
        item.appendChild(head);

        keys.forEach(function (k) {
          var info = langs[k] || {};
          if (info.text) item.appendChild(el("div", "li-text", "“" + info.text + "”"));
          var act = el("div", "li-actions");
          var play = el("button", "btn btn-sm", "▶ Nghe (" + k + ")");
          play.type = "button";
          play.addEventListener("click", function () {
            var a = new Audio("/api/library/voice/" + encodeURIComponent(v.name) + "/audio" + qs({ lang: k }));
            a.play().catch(function () { toast("error", "Không phát được", v.name + " · " + k); });
          });
          act.appendChild(play);
          if (typeof info.duration === "number") {
            act.appendChild(el("span", "muted", info.duration.toFixed(1) + "s"));
          }
          item.appendChild(act);
        });

        // Đổi tên & Xoá
        var act2 = el("div", "li-actions");
        var renameBtn = el("button", "btn btn-sm", "✏️ Đổi tên");
        renameBtn.type = "button";
        renameBtn.addEventListener("click", function () {
          var nn = prompt("Tên mới cho giọng mẫu:", v.name);
          if (nn && nn.trim() && nn.trim() !== v.name) {
            withBusy(renameBtn, function () {
              return api("/api/library/voice/" + encodeURIComponent(v.name) + "/rename", {
                method: "POST",
                body: { name: nn.trim() }
              }).then(function () {
                toast("ok", "Đã đổi tên");
                return loadLibrary();
              }).catch(function (e) { errToast("Đổi tên thất bại", e); });
            });
          }
        });
        act2.appendChild(renameBtn);

        var delBtn = el("button", "btn btn-sm btn-danger", "🗑️ Xoá");
        delBtn.type = "button";
        delBtn.addEventListener("click", function () {
          if (confirm("Xoá giọng mẫu '" + v.name + "'?")) {
            withBusy(delBtn, function () {
              return api("/api/library/voice/" + encodeURIComponent(v.name), {
                method: "DELETE"
              }).then(function () {
                toast("ok", "Đã xoá");
                return loadLibrary();
              }).catch(function (e) { errToast("Xoá thất bại", e); });
            });
          }
        });
        act2.appendChild(delBtn);
        item.appendChild(act2);

        vb.appendChild(item);
      });
    }
    if (!hasVoice) {
      emptyState(vb, "🎙️", "Chưa có giọng mẫu nào — tải lên hoặc tạo bằng AI");
    }

    // SFX
    renderSfx(lib.sfx);

    // Kinds (tùy chọn lang)
    renderKinds();
  }

  function renderSfx(list) {
    var box = $("lib-sfx");
    if (!box) return;
    box.innerHTML = "";
    if (!list || !list.length) {
      emptyState(box, "🔊", "Chưa có tiếng động nào");
      return;
    }
    list.forEach(function (s) {
      var item = el("div", "list-item");
      var head = el("div", "li-head");
      head.appendChild(el("span", "li-name", s.name));
      head.appendChild(el("span", "pill", "wav"));
      item.appendChild(head);

      var act = el("div", "li-actions");
      var play = el("button", "btn btn-sm", "▶ Nghe");
      play.type = "button";
      play.addEventListener("click", function () {
        var a = new Audio("/api/library/sfx/" + encodeURIComponent(s.name) + "/audio");
        a.play().catch(function () { toast("error", "Không phát được", s.name); });
      });
      act.appendChild(play);

      var renameBtn = el("button", "btn btn-sm", "✏️ Đổi tên");
      renameBtn.type = "button";
      renameBtn.addEventListener("click", function () {
        var nn = prompt("Tên mới cho tiếng động:", s.name);
        if (nn && nn.trim() && nn.trim() !== s.name) {
          withBusy(renameBtn, function () {
            return api("/api/library/sfx/" + encodeURIComponent(s.name) + "/rename", {
              method: "POST",
              body: { name: nn.trim() }
            }).then(function () {
              toast("ok", "Đã đổi tên");
              return loadLibrary();
            }).catch(function (e) { errToast("Đổi tên thất bại", e); });
          });
        }
      });
      act.appendChild(renameBtn);

      var delBtn = el("button", "btn btn-sm btn-danger", "🗑️ Xoá");
      delBtn.type = "button";
      delBtn.addEventListener("click", function () {
        if (confirm("Xoá tiếng động '" + s.name + "'?")) {
          withBusy(delBtn, function () {
            return api("/api/library/sfx/" + encodeURIComponent(s.name), {
              method: "DELETE"
            }).then(function () {
              toast("ok", "Đã xoá");
              return loadLibrary();
            }).catch(function (e) { errToast("Xoá thất bại", e); });
          });
        }
      });
      act.appendChild(delBtn);

      item.appendChild(act);
      box.appendChild(item);
    });
  }

  function renderKinds() {
    var box = $("lib-kinds");
    if (!box) return;
    var lang = $("kind-lang-select") ? $("kind-lang-select").value : "en";
    box.innerHTML = "";
    api("/api/comedy-kinds?lang=" + encodeURIComponent(lang))
      .then(function (data) {
        var kinds = (data && data.kinds) || [];
        if (!kinds.length) {
          emptyState(box, "😂", "Chưa có kiểu hài nào");
          return;
        }
        kinds.forEach(function (k) {
          var item = el("div", "list-item");
          var head = el("div", "li-head");
          head.appendChild(el("span", "li-name", k.name));
          head.appendChild(el("span", "pill", k.id));
          if (k.custom) head.appendChild(el("span", "pill", "tùy chỉnh"));
          item.appendChild(head);
          if (k.how) item.appendChild(el("div", "li-text", k.how));

          if (k.custom) {
            var act = el("div", "li-actions");
            var renameBtn = el("button", "btn btn-sm", "✏️ Sửa");
            renameBtn.type = "button";
            renameBtn.addEventListener("click", function () {
              var nName = prompt("Tên kiểu hài:", k.name);
              if (!nName) return;
              var nHow = prompt("Cách gây cười:", k.how);
              withBusy(renameBtn, function () {
                return api("/api/comedy-kinds", {
                  method: "POST",
                  body: { lang: lang, id: k.id, name: nName.trim(), how: nHow || "" }
                }).then(function () {
                  toast("ok", "Đã sửa");
                  renderKinds();
                }).catch(function (e) { errToast("Sửa thất bại", e); });
              });
            });
            act.appendChild(renameBtn);

            var delBtn = el("button", "btn btn-sm btn-danger", "🗑️ Xoá");
            delBtn.type = "button";
            delBtn.addEventListener("click", function () {
              if (confirm("Xoá kiểu hài '" + k.name + "'?")) {
                withBusy(delBtn, function () {
                  return api("/api/comedy-kinds/" + encodeURIComponent(k.id) + "?lang=" + encodeURIComponent(lang), {
                    method: "DELETE"
                  }).then(function () {
                    toast("ok", "Đã xoá");
                    renderKinds();
                  }).catch(function (e) { errToast("Xoá thất bại", e); });
                });
              }
            });
            act.appendChild(delBtn);
            item.appendChild(act);
          }

          box.appendChild(item);
        });
      })
      .catch(function (e) {
        errToast("Không tải được kiểu hài", e);
      });
  }

  function uploadLibraryCharacter(files) {
    var fd = new FormData();
    Array.prototype.forEach.call(files, function (f) { fd.append("files", f); });
    var first = files[0];
    var parsed = filenameToCharacter(first.name);
    withBusy($("btn-lib-char-upload"), function () {
      return api("/api/library/character", { method: "POST", body: fd })
        .then(function (r) {
          toast("ok", "Đã thêm nhân vật", (r && r.name) || parsed.name);
          return loadLibrary();
        })
        .catch(function (e) { errToast("Thêm nhân vật thất bại", e); });
    });
  }

  function uploadLibraryBackground(files) {
    var fd = new FormData();
    Array.prototype.forEach.call(files, function (f) { fd.append("files", f); });
    withBusy($("btn-lib-bg-upload"), function () {
      return api("/api/library/background", { method: "POST", body: fd })
        .then(function (r) {
          toast("ok", "Đã thêm bối cảnh", (r && r.name) || "");
          return loadLibrary();
        })
        .catch(function (e) { errToast("Thêm bối cảnh thất bại", e); });
    });
  }

  function uploadLibraryVoice(file, name, language, text) {
    var fd = new FormData();
    fd.append("file", file);
    if (name) fd.append("name", name);
    if (language) fd.append("language", language);
    if (text) fd.append("text", text);
    return api("/api/library/voice", { method: "POST", body: fd });
  }

  function openMouthPicker(charName, imagePath) {
    // Mở modal hiển thị ảnh, người dùng click vào vị trí miệng
    var modal = $("mouth-picker-modal");
    if (!modal) {
      modal = el("div", "modal");
      modal.id = "mouth-picker-modal";
      modal.style.cssText = "position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:9999;";

      var box = el("div", "modal-box");
      box.style.cssText = "background:#fff;padding:24px;border-radius:16px;max-width:900px;max-height:90vh;overflow:auto;";
      modal.appendChild(box);

      var title = el("h2", "", "Chấm vị trí miệng cho " + charName);
      box.appendChild(title);

      var hint = el("p", "hint", "Click vào vị trí giữa miệng (phía dưới mũi) rồi bấm Lưu.");
      box.appendChild(hint);

      var canvas = document.createElement("canvas");
      canvas.id = "mouth-canvas";
      canvas.style.cursor = "crosshair";
      canvas.style.border = "2px solid #0B0E14";
      canvas.style.borderRadius = "8px";
      canvas.style.display = "block";
      canvas.style.margin = "16px auto";
      box.appendChild(canvas);

      var btnRow = el("div", "");
      btnRow.style.cssText = "display:flex;gap:12px;justify-content:flex-end;";
      var saveBtn = el("button", "btn btn-primary", "Lưu");
      saveBtn.id = "mouth-save-btn";
      saveBtn.disabled = true;
      var cancelBtn = el("button", "btn", "Huỷ");
      cancelBtn.addEventListener("click", function() { document.body.removeChild(modal); });
      btnRow.appendChild(cancelBtn);
      btnRow.appendChild(saveBtn);
      box.appendChild(btnRow);

      document.body.appendChild(modal);
    } else {
      modal.querySelector("h2").textContent = "Chấm vị trí miệng cho " + charName;
    }

    var canvas = $("mouth-canvas");
    var ctx = canvas.getContext("2d");
    var img = new Image();
    var markedPos = null;

    img.onload = function() {
      // Scale ảnh cho vừa khung (max 800x600)
      var maxW = 800, maxH = 600;
      var scale = Math.min(1, maxW / img.width, maxH / img.height);
      canvas.width = img.width * scale;
      canvas.height = img.height * scale;

      function redraw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        if (markedPos) {
          ctx.fillStyle = "#F97316";
          ctx.strokeStyle = "#FFF";
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.arc(markedPos.x, markedPos.y, 8, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        }
      }

      redraw();

      canvas.onclick = function(e) {
        var rect = canvas.getBoundingClientRect();
        var x = e.clientX - rect.left;
        var y = e.clientY - rect.top;
        markedPos = { x: Math.round(x / scale), y: Math.round(y / scale) };
        redraw();
        $("mouth-save-btn").disabled = false;
      };

      $("mouth-save-btn").onclick = function() {
        if (!markedPos) return;
        withBusy($("mouth-save-btn"), function() {
          return api("/api/library/character/" + encodeURIComponent(charName) + "/mouth", {
            method: "POST",
            body: { x: markedPos.x, y: markedPos.y }
          }).then(function() {
            toast("ok", "Đã lưu", "Vị trí miệng: " + markedPos.x + ", " + markedPos.y);
            document.body.removeChild(modal);
            return loadLibrary();
          }).catch(function(e) {
            errToast("Lưu thất bại", e);
          });
        });
      };
    };

    img.src = assetUrl(imagePath);
  }

  /* --------------------------- Settings ---------------------------- */

  function renderSettings() {
    var s = state.settings || {};
    if (s.gap_between_lines != null) $("s-gap").value = s.gap_between_lines;
    if (s.subtitle_style) $("s-subtitle").value = s.subtitle_style;
    if (s.subtitle_mode) $("s-subtitle-mode").value = s.subtitle_mode;
    if (s.bgm_volume != null) {
      $("s-bgm-volume").value = s.bgm_volume;
      $("s-bgm-volume-val").textContent = Number(s.bgm_volume).toFixed(2);
    }
    if (s.sfx_volume != null) {
      $("s-sfx-volume").value = s.sfx_volume;
      $("s-sfx-volume-val").textContent = Number(s.sfx_volume).toFixed(2);
    }
    $("s-title-text").value = s.title_text || "";
    $("s-claude-bin").value = s.claude_bin || "";
    $("s-agy-bin").value = s.agy_bin || "";
    $("s-agy-model").value = s.agy_model || "";
    $("s-ai-fallback").value = s.ai_fallback === false ? "0" : "1";
    renderAiEngines(s.ai_engines || {});
    $("s-ffmpeg-bin").value = s.ffmpeg_bin || "";
    $("s-enable-rig").value = s.enable_rig === false ? "0" : "1";
    $("s-auto-camera").value = s.auto_camera === false ? "0" : "1";
    $("s-auto-seat").value = s.auto_seat === false ? "0" : "1";
    $("s-three-quarter").value = s.three_quarter === false ? "0" : "1";
    $("s-wide-stage").value = s.wide_stage === false ? "0" : "1";
    $("s-subtitle-pos").value = s.subtitle_position === "duoi" ? "duoi" : "tren";
    var cs = s.char_style || "auto";
    $("s-char-style").value = ["auto", "gray", "khand", "kchibi", "box", "stick", "flat"].indexOf(cs) >= 0 ? cs : "auto";
    $("bgm-current").textContent = s.bgm_file ? (s.bgm_file) : "Chưa chọn file";
    $("s-capcut-root").value = s.capcut_drafts_root || "";
    $("capcut-root-hint").textContent =
      s.capcut_drafts_root || "(để trống = dùng mặc định của CapCut)";
    updateSubtitleSwatch();
    updateStageFromProject();
  }

  /* --------------------- Trợ lý AI cho từng việc ---------------------- */

  function renderAiEngines(chosen) {
    var box = $("ai-engine-list");
    if (!box) return;
    box.innerHTML = "";
    var engines = (state.meta && state.meta.ai_engines) || [];
    ((state.meta && state.meta.ai_tasks) || []).forEach(function (t) {
      var f = el("div", "field");
      var lb = el("label", "", t.label);
      lb.setAttribute("for", "ai-task-" + t.id);
      var sel = document.createElement("select");
      sel.id = "ai-task-" + t.id;
      sel.setAttribute("data-task", t.id);
      var allowed = t.engines || null;
      engines.forEach(function (e) {
        if (!allowed || allowed.indexOf(e.id) >= 0) sel.appendChild(new Option(e.label, e.id));
      });
      var v = chosen[t.id] === "gemini" ? "agy" : chosen[t.id];   // cài đặt cũ
      sel.value = v || t["default"];
      if (!sel.value) sel.value = t["default"];
      f.appendChild(lb);
      f.appendChild(sel);
      box.appendChild(f);
    });
  }

  function collectAiEngines() {
    var out = {};
    var box = $("ai-engine-list");
    var sels = box ? box.querySelectorAll("select[data-task]") : [];
    // danh sách chưa hiện (meta chưa tải xong): giữ nguyên lựa chọn cũ
    if (!sels.length) return (state.settings && state.settings.ai_engines) || {};
    box.querySelectorAll("select[data-task]").forEach(function (s) {
      out[s.getAttribute("data-task")] = s.value;
    });
    return out;
  }

  function showAiCalls(counts) {
    var cc = $("claude-calls");
    if (!cc || !counts) return;
    cc.textContent = "Claude " + (counts.claude || 0) + " · Antigravity " + (counts.agy || 0);
  }

  /* --------------------- Xuất dự án CapCut ---------------------- */

  function fillCapcutTemplateSelect(drafts, current) {
    var sel = $("s-capcut-template");
    if (!sel) return;
    sel.innerHTML = "";
    sel.appendChild(new Option("— Chưa chọn —", ""));
    (drafts || []).forEach(function (name) {
      sel.appendChild(new Option(name, name));
    });
    if (current) sel.value = current;
  }

  function loadCapcutDrafts() {
    return api("/api/capcut/drafts").then(function (d) {
      d = d || {};
      fillCapcutTemplateSelect(d.drafts, d.template);
      var hint = $("capcut-root-hint");
      if (hint && !($("s-capcut-root").value || "").trim()) {
        hint.textContent = d.root || "";
      }
      if (!d.root_exists) {
        toast("error", "Không thấy thư mục CapCut",
          "Kiểm tra lại đường dẫn CapCut trong Cài đặt nhé.");
      }
      return d;
    }).catch(function (e) { errToast("Không tải được danh sách dự án CapCut", e); });
  }

  function loadSettings() {
    return api("/api/settings").then(function (s) {
      state.settings = s || {};
      renderSettings();
      loadCapcutDrafts();
      return state.settings;
    }).catch(function (e) { errToast("Không tải được cài đặt", e); });
  }

  function saveSettings() {
    var body = {
      gap_between_lines: parseFloat($("s-gap").value) || 0,
      subtitle_style: $("s-subtitle").value,
      subtitle_mode: $("s-subtitle-mode") ? $("s-subtitle-mode").value : "chunks",
      bgm_volume: parseFloat($("s-bgm-volume").value) || 0,
      sfx_volume: parseFloat($("s-sfx-volume").value) || 0,
      title_text: $("s-title-text").value,
      claude_bin: $("s-claude-bin").value.trim(),
      agy_bin: $("s-agy-bin").value.trim(),
      agy_model: $("s-agy-model").value.trim(),
      ai_engines: collectAiEngines(),
      ai_fallback: $("s-ai-fallback").value === "1",
      ffmpeg_bin: $("s-ffmpeg-bin").value.trim(),
      enable_rig: $("s-enable-rig").value === "1",
      auto_camera: $("s-auto-camera").value === "1",
      auto_seat: $("s-auto-seat").value === "1",
      three_quarter: $("s-three-quarter").value === "1",
      wide_stage: $("s-wide-stage").value === "1",
      subtitle_position: $("s-subtitle-pos").value,
      char_style: $("s-char-style").value,
      capcut_drafts_root: $("s-capcut-root").value.trim(),
      capcut_template_draft: $("s-capcut-template")
        ? $("s-capcut-template").value : ""
    };
    // Chỉ gửi bgm_file khi user vừa chọn file mới (server tự lưu binary)
    if (state.settings && state.settings.bgm_file && state.bgmPristine) {
      body.bgm_file = state.settings.bgm_file;
    }
    var btn = $("btn-save-settings");
    withBusy(btn, function () {
      var p1 = api("/api/settings", { method: "POST", body: body });
      var fileToPost = state.bgmPristine ? null : (pending.bgmFile || null);
      return p1.then(function (saved) {
        if (fileToPost) {
          var fd = new FormData();
          fd.append("file", fileToPost);
          // Gửi kèm tên file để server lưu lại
          return api("/api/settings", { method: "POST", body: fd })
            .then(function (s2) { state.settings = s2; })
            .catch(function () { /* vẫn coi như lưu được phần còn lại */ });
        }
        state.settings = saved;
        return saved;
      }).then(function () {
        state.bgmPristine = true;
        renderSettings();
        toast("ok", "Đã lưu", "Cài đặt đã được lưu.");
      }).catch(function (e) { errToast("Lưu cài đặt thất bại", e); });
    });
  }

  function checkSystem() {
    withBusy($("btn-check-system"), function () {
      return api("/api/check-system", { method: "GET" })
        .then(function (data) {
          var checks = (data && data.checks) || [];
          var box = $("check-result");
          box.innerHTML = "";
          checks.forEach(function (c) {
            var item = el("div", "item");
            var head = el("div", "item-head");
            var statusMap = {ok: "ok", warn: "warn", error: "err"};
            var statusLabel = {ok: "✓", warn: "⚠", error: "✗"};
            head.appendChild(el("span", "pill " + statusMap[c.status], statusLabel[c.status] + " " + c.item));
            item.appendChild(head);
            item.appendChild(el("div", "item-body", c.message));
            box.appendChild(item);
          });
        })
        .catch(function (e) {
          errToast("Kiểm tra thất bại", e);
        });
    });
  }

  /* ---------------------------- Tabs ------------------------------- */

  function switchTab(name, push) {
    document.querySelectorAll(".tab").forEach(function (t) {
      t.classList.toggle("is-active", t.dataset.screen === name);
    });
    document.querySelectorAll(".screen").forEach(function (s) {
      s.classList.toggle("is-active", s.id === "screen-" + name);
    });
    try { localStorage.setItem(LS_TAB, name); } catch (e) {}

    if (name === "library" && !state.library) loadLibrary();
    if (name === "library") { renderLibrary(); }
    if (name === "settings" && !state.settings) loadSettings();
    if (name === "rig") { /* rig screen handles itself */ }
  }

  /* --------------------------- Wiring ------------------------------ */

  function wireTabs() {
    $("tabs").addEventListener("click", function (e) {
      var b = e.target.closest(".tab");
      if (b) switchTab(b.dataset.screen);
    });

    // Cho phép màn hình con (ví dụ rig.js) yêu cầu chuyển tab
    document.addEventListener("switchTab", function (e) {
      if (!e || !e.detail || !e.detail.name) return;
      var tab = document.querySelector('.tab[data-screen="' + e.detail.name + '"]');
      if (tab) switchTab(e.detail.name);
    });
  }

  function wireMeta() {
    $("p-language").addEventListener("change", function () {
      populateKinds();
      touchProject();
    });
    $("p-kind").addEventListener("change", function () { updateKindHow(); touchProject(); });
    $("p-title").addEventListener("input", debounce(function () {
      $("project-badge").textContent = projectLabel();
      if ($("project-badge").textContent === "Chưa có tập nào" && state.project && state.project.title) {
        $("project-badge").textContent = state.project.id + " · " + $("p-title").value;
      }
      saveTitleLocal();
      if (state.project && state.project.id) {
        // đồng bộ tiêu đề — tạo project mới nếu đổi tiêu đề sau khi tạo?
        // Giữ nguyên id, chỉ cập nhật label.
        renderProjectKv();
      }
    }, 350));
    $("p-hints").addEventListener("input", touchProject);
    $("p-format").addEventListener("change", saveMeta);
    $("p-duration").addEventListener("change", saveMeta);

    $("btn-create").addEventListener("click", function () {
      withBusy($("btn-create"), function () {
        var title = $("p-title").value.trim();
        if (!title) {
          toast("warn", "Thiếu tiêu đề", "Hãy nhập tiêu đề tập trước.");
          return;
        }
        var kind = $("p-kind").value;
        if (kind === "__custom__") kind = "";
        return api("/api/project", {
          method: "POST",
          body: { title: title, language: $("p-language").value, kind: kind,
                  format: formatValue(), duration: durationValue() }
        }).then(function (p) {
          state.project = p;
          state.projectTouched = false;
          renderProjectKv();
          renderScenes();
          saveTitleLocal();
          toast("ok", "Đã tạo tập", "Mã: " + p.id);
        }).catch(function (e) { errToast("Tạo tập thất bại", e); });
      });
    });
  }

  function wireScript() {
    var ta = $("p-script");
    ta.addEventListener("input", onScriptInput);
    $("btn-save-script").addEventListener("click", saveScriptToServer);
  }

  function wireWrite() {
    $("btn-write").addEventListener("click", function () {
      withBusy($("btn-write"), function () {
        return doWrite().catch(function (e) { errToast("Viết thất bại", e); });
      });
    });

    $("btn-ideas").addEventListener("click", function () {
      var t = $("p-title").value.trim();
      if (!t) { toast("warn", "Thiếu tiêu đề", "Nhập tiêu đề trước khi lấy ý tưởng."); return; }
      withBusy($("btn-ideas"), function () {
        return ensureProject().then(function (p) {
          return api("/api/project/" + encodeURIComponent(p.id) + "/ideas", {
            method: "POST",
            body: { title: t, language: $("p-language").value }
          });
        }).then(function (data) {
          renderIdeas(data && data.ideas);
          if (!data || !data.ideas || !data.ideas.length) toast("warn", "Không có ý tưởng", "Thử lại sau.");
        }).catch(function (e) { errToast("Lấy ý tưởng thất bại", e); });
      });
    });

    $("btn-trends").addEventListener("click", function () {
      withBusy($("btn-trends"), function () {
        return ensureProject().then(function (p) {
          return api("/api/project/" + encodeURIComponent(p.id) + "/trends", {
            method: "POST",
            body: { language: $("p-language").value }
          });
        }).then(function (data) {
          renderTrends(data && data.ideas);
          if (!data || !data.ideas || !data.ideas.length) toast("warn", "Không có trend", "Thử lại sau.");
        }).catch(function (e) { errToast("Lấy trend thất bại", e); });
      });
    });

    $("btn-review").addEventListener("click", function () {
      if (!state.project || !state.project.id) {
        toast("warn", "Chưa có tập", "Tạo tập và viết kịch bản trước.");
        return;
      }
      withBusy($("btn-review"), function () {
        return api("/api/project/" + encodeURIComponent(state.project.id) + "/script", {
          method: "POST",
          body: { script: $("p-script").value }
        }).then(function () {
          return api("/api/project/" + encodeURIComponent(state.project.id) + "/review", {
            method: "POST",
            body: {}
          });
        }).then(function (data) {
          renderReview((data && data.suggestions) || []);
          var n = (data && data.suggestions || []).length;
          toast(n ? "ok" : "warn", n ? (n + " góp ý") : "Không có góp ý");
        }).catch(function (e) { errToast("Rà soát thất bại", e); });
      });
    });

    $("btn-apply").addEventListener("click", applyReview);
    $("btn-generate").addEventListener("click", function () { doGenerate(); });
    $("in-scene-bg").addEventListener("change", function () {
      uploadSceneBg(this.files && this.files[0]);
    });
  }

  function wireUploads() {
    var pairs = [
      ["dz-characters", "in-characters", "characters"],
      ["dz-background", "in-background", "background"],
      ["dz-voices", "in-voices", "voices"]
    ];
    pairs.forEach(function (pr) {
      var dz = $(pr[0]), input = $(pr[1]), kind = pr[2];
      dz.addEventListener("click", function () { input.click(); });
      input.addEventListener("change", function () {
        setFiles(kind, input.files);
        input.value = "";
      });
      dz.addEventListener("dragover", function (e) {
        e.preventDefault(); dz.classList.add("is-over");
      });
      dz.addEventListener("dragleave", function () { dz.classList.remove("is-over"); });
      dz.addEventListener("drop", function (e) {
        e.preventDefault();
        dz.classList.remove("is-over");
        setFiles(kind, e.dataTransfer.files);
      });
    });

    $("btn-upload").addEventListener("click", uploadAssets);

    // nút copy text gợi ý
    var hint = document.querySelector("#sec-upload .hint-upload");
    if (hint) {
      var copyBtn = document.createElement("button");
      copyBtn.className = "btn btn-ghost btn-sm";
      copyBtn.type = "button";
      copyBtn.textContent = "Copy gợi ý hướng";
      copyBtn.addEventListener("click", function () {
        var text = "Áp dụng cùng font, cùng cỡ chữ, cùng màu, cùng hiệu ứng, cùng viền và cùng tỉ lệ cho mọi nhân vật.";
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () {
            toast("ok", "Đã copy hướng dạo phim");
          }, function () { toast("warn", "Không copy được"); });
        } else {
          toast("warn", "Trình duyệt không hỗ trợ copy");
        }
      });
      hint.appendChild(copyBtn);
    }
  }

  function wireLibrary() {
    $("btn-lib-reload").addEventListener("click", function () {
      withBusy($("btn-lib-reload"), function () { return loadLibrary(); });
    });

    $("btn-lib-char-upload").addEventListener("click", function () { $("lib-char-input").click(); });
    $("lib-char-input").addEventListener("change", function () {
      if (this.files.length) uploadLibraryCharacter(this.files);
      this.value = "";
    });

    $("btn-lib-bg-upload").addEventListener("click", function () { $("lib-bg-input").click(); });
    $("lib-bg-input").addEventListener("change", function () {
      if (this.files.length) uploadLibraryBackground(this.files);
      this.value = "";
    });

    $("btn-lib-voice-upload").addEventListener("click", function () { $("lib-voice-input").click(); });
    $("lib-voice-input").addEventListener("change", function () {
      var files = this.files;
      this.value = "";
      if (!files.length) return;
      var f = files[0];
      var name = baseName(f.name);
      var lang = ($("vd-language").value) || "ko";
      withBusy($("btn-lib-voice-upload"), function () {
        return uploadLibraryVoice(f, name, lang).then(function () {
          toast("ok", "Đã thêm giọng", name);
          return loadLibrary();
        }).catch(function (e) { errToast("Thêm giọng thất bại", e); });
      });
    });

    $("btn-voice-design").addEventListener("click", function () {
      var name = $("vd-name").value.trim();
      var instruct = $("vd-instruct").value.trim();
      if (!name || !instruct) {
        toast("warn", "Thiếu thông tin", "Nhập tên nhân vật và mô tả giọng.");
        return;
      }
      withBusy($("btn-voice-design"), function () {
        return api("/api/library/voice/design", {
          method: "POST",
          body: {
            name: name,
            language: $("vd-language").value,
            instruct: instruct
          }
        }).then(function (r) {
          toast("ok", "Đã tạo giọng", (r.name || name) + " · " + (r.duration ? r.duration.toFixed(1) + "s" : ""));
          var lang = r.language || $("vd-language").value;
          var a = new Audio("/api/library/voice/" + encodeURIComponent(r.name) + "/audio" + qs({ lang: lang }));
          a.play().catch(function () {});
          return loadLibrary();
        }).catch(function (e) { errToast("Tạo giọng thất bại", e); });
      });
    });

    // Kinds section
    var kindLangSelect = $("kind-lang-select");
    if (kindLangSelect) {
      kindLangSelect.addEventListener("change", function () { renderKinds(); });
    }
    var btnAddKind = $("btn-add-kind");
    if (btnAddKind) {
      btnAddKind.addEventListener("click", function () {
        var lang = kindLangSelect ? kindLangSelect.value : "en";
        var id = prompt("ID cho kiểu hài (không dấu, không khoảng trắng, VD: my_kind):");
        if (!id) return;
        var name = prompt("Tên hiển thị:");
        if (!name) return;
        var how = prompt("Cách gây cười:");
        withBusy(btnAddKind, function () {
          return api("/api/comedy-kinds", {
            method: "POST",
            body: { lang: lang, id: id.trim(), name: name.trim(), how: how || "" }
          }).then(function () {
            toast("ok", "Đã thêm kiểu hài");
            renderKinds();
          }).catch(function (e) { errToast("Thêm thất bại", e); });
        });
      });
    }
  }

  function wireSettings() {
    $("s-gap").addEventListener("input", function () {});
    $("s-subtitle").addEventListener("change", updateSubtitleSwatch);
    $("s-bgm-volume").addEventListener("input", function () {
      $("s-bgm-volume-val").textContent = Number(this.value).toFixed(2);
      if ($("bgm-audio")) $("bgm-audio").volume = Number(this.value);
    });
    $("s-sfx-volume").addEventListener("input", function () {
      $("s-sfx-volume-val").textContent = Number(this.value).toFixed(2);
    });

    $("s-bgm-file").addEventListener("change", function () {
      var f = this.files && this.files[0];
      if (f) {
        state.bgmPristine = false;
        pending.bgmFile = f;
        $("bgm-current").textContent = f.name + " · " + humanSize(f.size);
        if (state.bgmObjectUrl) URL.revokeObjectURL(state.bgmObjectUrl);
        state.bgmObjectUrl = URL.createObjectURL(f);
        $("bgm-audio").src = state.bgmObjectUrl;
      }
    });

    $("btn-bgm-play").addEventListener("click", function () {
      var a = $("bgm-audio");
      var btn = this;
      if (!a.src) {
        // chưa chọn file local — dùng file server nếu có
        if (state.settings && state.settings.bgm_file) {
          a.src = state.settings.bgm_file;
        } else {
          toast("warn", "Chưa có nhạc", "Hãy chọn file nhạc nền trước.");
          return;
        }
      }
      if (a.paused) {
        a.play().then(function () { btn.textContent = "⏸ Tạm dừng"; })
          .catch(function () { toast("error", "Không phát được nhạc"); });
      } else {
        a.pause();
        btn.textContent = "▶ Nghe thử";
      }
    });

    $("btn-save-settings").addEventListener("click", saveSettings);
    $("btn-check-system").addEventListener("click", checkSystem);
    if ($("btn-capcut-reload")) {
      $("btn-capcut-reload").addEventListener("click", function () {
        var b = this;
        withBusy(b, loadCapcutDrafts);
      });
    }
    if ($("btn-capcut-export")) {
      $("btn-capcut-export").addEventListener("click", exportCapcut);
    }
  }

  function wireRender() {
    $("btn-render").addEventListener("click", startRender);
  }

  /* --------------------------- Bootstrap --------------------------- */

  function updateClaudeCalls() {
    api("/api/claude-calls").then(function (d) {
      if (d && d.counts) { showAiCalls(d.counts); return; }
      var el = $("claude-calls");
      if (el && d) el.textContent = d.count || 0;
    }).catch(function () {});
  }

  function loadMeta() {
    return api("/api/meta").then(function (m) {
      state.meta = m || {};
      if (!state.meta.languages) state.meta.languages = [{ code: "ko", label: "Tiếng Hàn" }, { code: "en", label: "Tiếng Anh" }, { code: "vi", label: "Tiếng Việt" }];
      populateLanguages();
      populateSubtitleStyles();
      var cc = $("claude-calls");
      if (cc && typeof state.meta.claude_calls === "number") cc.textContent = state.meta.claude_calls;
      if (state.meta.ai_calls) showAiCalls(state.meta.ai_calls);
      if (state.settings) renderAiEngines(state.settings.ai_engines || {});
      return state.meta;
    });
  }

  function init() {
    wireTabs();
    wireMeta();
    wireScript();
    wireWrite();
    wireUploads();
    wireLibrary();
    wireSettings();
    wireRender();

    // khôi phục tab & tiêu đề
    var savedTitle = "";
    try { savedTitle = localStorage.getItem(LS_TITLE) || ""; } catch (e) {}
    if (savedTitle) $("p-title").value = savedTitle;

    var savedTab = "new";
    try { savedTab = localStorage.getItem(LS_TAB) || "new"; } catch (e) {}

    renderIdeas([]);
    renderTrends([]);
    renderReview([]);
    renderParsedCharacters([]);
    renderThumbs();
    updateDurationPill();

    // meta là bắt buộc
    loadMeta().catch(function (e) {
      errToast("Không tải được meta", e);
      // vẫn render UI với defaults
      if (!state.meta) {
        state.meta = {
          languages: [{ code: "ko", label: "Tiếng Hàn" }, { code: "en", label: "Tiếng Anh" }, { code: "vi", label: "Tiếng Việt" }],
          comedy_kinds: {}, subtitle_styles: ["yellow", "white", "green", "pink"],
          target_duration: [30, 90]
        };
        populateLanguages();
        populateSubtitleStyles();
      }
    });

    loadSettings();
    switchTab(savedTab);

    // nếu tab library được chọn, switchTab đã gọi loadLibrary
    updateStageFromProject();
    renderScenes();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
