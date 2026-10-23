/* ============================================================
   Màn hình Truyện kể: video dài kể chuyện, một giọng người kể,
   tranh minh hoạ chị tự vẽ từ bộ câu lệnh tool xuất ra.
   ============================================================ */

(function () {
  "use strict";

  var LS_STORY = "tool_hai_story_id";
  var CAM_VI = { zoom_in: "Phóng vào", zoom_out: "Lùi ra", pan_left: "Lia sang trái",
                 pan_right: "Lia sang phải", pan_up: "Lia lên", pan_down: "Lia xuống",
                 still: "Đứng yên" };
  var st = { id: null, data: null, voices: [], polling: null };

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function toast(type, title, body) {
    var wrap = $("toasts");
    if (!wrap) return;
    var t = el("div", "toast " + (type || ""));
    t.appendChild(el("div", "toast-title", title || ""));
    if (body) t.appendChild(el("div", "toast-body", body));
    wrap.appendChild(t);
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, type === "error" ? 6500 : 3400);
  }
  function api(path, opts) {
    opts = opts || {};
    var headers = {}, body = opts.body;
    if (body && !(body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    return fetch(path, { method: opts.method || (body ? "POST" : "GET"), headers: headers, body: body })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (d) {
          if (!res.ok) throw new Error((d && d.error) || ("Lỗi " + res.status));
          return d;
        });
      });
  }
  function fail(prefix) {
    return function (e) { toast("error", prefix, e && e.message ? e.message : String(e)); };
  }

  /* ----------------------------------------------------------- tải / lưu */

  function loadList(selectId) {
    return api("/api/story/list").then(function (d) {
      var sel = $("st-pick");
      sel.innerHTML = "";
      sel.appendChild(new Option("— Mở truyện đã làm —", ""));
      (d.stories || []).forEach(function (s) {
        sel.appendChild(new Option(s.title + " · " + (s.created_at || "").slice(0, 10), s.id));
      });
      if (selectId) sel.value = selectId;
    });
  }

  function loadVoices() {
    return api("/api/library").then(function (d) {
      var sel = $("st-voice");
      sel.innerHTML = "";
      sel.appendChild(new Option("— Dùng mô tả giọng bên cạnh —", ""));
      (d.voices || []).forEach(function (v) {
        if (v && v.name) sel.appendChild(new Option(v.name, v.name));
      });
    }).catch(function () {});
  }

  function open(id) {
    if (!id) return Promise.resolve();
    return api("/api/story/" + encodeURIComponent(id)).then(function (d) {
      st.id = id;
      try { localStorage.setItem(LS_STORY, id); } catch (e) {}
      render(d);
      watch();
    }).catch(fail("Không mở được truyện"));
  }

  function collect() {
    var s = (st.data && st.data.story) || {};
    var body = {
      title: $("st-title").value.trim(),
      author: $("st-author").value.trim(),
      minutes: parseInt($("st-minutes").value, 10) || 25,
      format: $("st-format").value,
      style: $("st-style").value,
      subtitles: $("st-subs").value === "1",
      source_text: $("st-source").value,
      narrator: { voice: $("st-voice").value, instruct: $("st-instruct").value.trim() }
    };
    // nhân vật / địa điểm đã sửa
    var bible = { characters: [], places: [] };
    document.querySelectorAll("#st-bible [data-kind]").forEach(function (row) {
      bible[row.getAttribute("data-kind")].push({
        id: row.getAttribute("data-id"),
        name: row.querySelector("input").value,
        look: row.querySelector("textarea").value
      });
    });
    if (s.characters) { body.characters = bible.characters; body.places = bible.places; }
    // chương / cảnh đã sửa
    if (s.chapters && s.chapters.length) {
      body.chapters = s.chapters.map(function (ch, ci) {
        var t = document.querySelector('[data-chapter="' + ci + '"]');
        return {
          title: t ? t.value : ch.title,
          scenes: (ch.scenes || []).map(function (sc) {
            var box = document.querySelector('[data-scene="' + sc.id + '"]');
            if (!box) return sc;
            var out = Object.assign({}, sc);
            out.text = box.querySelector(".st-text").value;
            out.prompt = box.querySelector(".st-prompt").value;
            out.camera = box.querySelector("select").value;
            return out;
          })
        };
      });
    }
    return body;
  }

  function save(quiet) {
    if (!st.id) return Promise.resolve();
    return api("/api/story/" + encodeURIComponent(st.id) + "/save", { body: collect() })
      .then(function (d) { render(d); if (!quiet) toast("ok", "Đã lưu"); return d; })
      .catch(fail("Lưu thất bại"));
  }

  /* ----------------------------------------------------------- hiển thị */

  function render(d) {
    st.data = d;
    var s = d.story || {};
    $("st-title").value = s.title || "";
    $("st-author").value = s.author || "";
    $("st-minutes").value = s.minutes || 25;
    $("st-format").value = d.format || "16:9";
    var sty = $("st-style");
    sty.innerHTML = "";
    Object.keys(d.styles || {}).forEach(function (k) { sty.appendChild(new Option(d.styles[k], k)); });
    sty.value = s.style || "anim2d";
    $("st-subs").value = s.subtitles ? "1" : "0";
    $("st-source").value = s.source_text || "";
    var nar = s.narrator || {};
    $("st-voice").value = nar.voice || "";
    $("st-instruct").value = nar.instruct || "";
    renderBible(s);
    renderScenes(d);
    var n = d.scene_count || 0;
    $("st-img-count").textContent = n
      ? ("Đã có " + (n - (d.missing || []).length) + "/" + n + " tranh" +
         ((d.missing || []).length ? " · thiếu: " + d.missing.slice(0, 12).join(", ") +
          (d.missing.length > 12 ? "…" : "") : ""))
      : "Chưa có cảnh — bấm “AI viết lời kể & chia cảnh”.";
    $("st-prompts").href = n ? "/api/story/" + encodeURIComponent(st.id) + "/prompts" : "#";
    showVideo(d.video_ready);
  }

  function renderBible(s) {
    var box = $("st-bible");
    box.innerHTML = "";
    var rows = (s.characters || []).map(function (c) { return ["characters", c]; })
      .concat((s.places || []).map(function (p) { return ["places", p]; }));
    if (!rows.length) {
      box.appendChild(el("p", "hint", "AI sẽ lập danh sách khi viết lời kể."));
      return;
    }
    rows.forEach(function (r) {
      var row = el("div", "st-bible-item");
      row.setAttribute("data-kind", r[0]);
      row.setAttribute("data-id", r[1].id);
      var name = document.createElement("input");
      name.type = "text";
      name.value = r[1].name || "";
      name.title = r[0] === "characters" ? "Nhân vật" : "Địa điểm";
      var look = document.createElement("textarea");
      look.rows = 2;
      look.value = r[1].look || "";
      row.appendChild(name);
      row.appendChild(look);
      box.appendChild(row);
    });
  }

  function renderScenes(d) {
    var box = $("st-scenes");
    box.innerHTML = "";
    var s = d.story || {};
    var have = {};
    (d.images || []).forEach(function (i) { have[i] = true; });
    if (!(s.chapters || []).length) {
      box.appendChild(el("p", "hint", "Chưa có cảnh."));
      return;
    }
    s.chapters.forEach(function (ch, ci) {
      var t = document.createElement("input");
      t.type = "text";
      t.className = "st-chapter";
      t.value = ch.title || "";
      t.setAttribute("data-chapter", ci);
      var head = el("div", "st-meta", "Chương " + (ci + 1));
      box.appendChild(head);
      box.appendChild(t);
      (ch.scenes || []).forEach(function (sc) {
        var row = el("div", "st-scene");
        row.setAttribute("data-scene", sc.id);
        var thumb;
        if (have[sc.id]) {
          thumb = document.createElement("img");
          thumb.className = "st-thumb";
          thumb.loading = "lazy";
          thumb.src = "/api/story/" + encodeURIComponent(st.id) + "/image/" + sc.id + "?t=" + Date.now();
        } else {
          thumb = el("div", "st-thumb", "scene_" + sc.id + "\nchưa có tranh");
        }
        var right = el("div", "");
        var meta = el("div", "st-meta", "Cảnh " + sc.id + " · máy quay");
        var cam = document.createElement("select");
        (d.cameras || []).forEach(function (c) { cam.appendChild(new Option(CAM_VI[c] || c, c)); });
        cam.value = sc.camera || "zoom_in";
        meta.appendChild(cam);
        var text = document.createElement("textarea");
        text.className = "st-text";
        text.rows = 3;
        text.value = sc.text || "";
        var prompt = document.createElement("textarea");
        prompt.className = "st-prompt";
        prompt.rows = 2;
        prompt.placeholder = "Mô tả tranh (tiếng Anh)";
        prompt.value = sc.prompt || "";
        right.appendChild(meta);
        right.appendChild(text);
        right.appendChild(prompt);
        row.appendChild(thumb);
        row.appendChild(right);
        box.appendChild(row);
      });
    });
  }

  function showVideo(ready) {
    var v = $("st-video"), a = $("st-download");
    if (ready && st.id) {
      var url = "/api/project/" + encodeURIComponent(st.id) + "/video?t=" + Date.now();
      v.src = url;
      v.hidden = false;
      a.href = url;
      a.hidden = false;
    } else {
      v.hidden = true;
      a.hidden = true;
    }
  }

  /* ----------------------------------------------------------- việc nền */

  function watch() {
    if (st.polling) clearInterval(st.polling);
    var last = null;
    st.polling = setInterval(function () {
      if (!st.id) return;
      api("/api/project/" + encodeURIComponent(st.id) + "/status").then(function (s) {
        var writing = s.state === "writing", rendering = s.state === "rendering";
        var pct = Math.round((s.progress || 0) * 100) + "%";
        $("st-progress-wrap").hidden = !writing;
        $("st-render-wrap").hidden = !rendering;
        if (writing) {
          $("st-progress-bar").style.width = pct;
          $("st-progress-label").textContent = pct + " · " + (s.message || "");
        }
        if (rendering) {
          $("st-render-bar").style.width = pct;
          $("st-render-label").textContent = pct + " · " + (s.message || "");
        }
        // việc nền xong mà màn hình chưa có kết quả (xong nhanh hơn lần hỏi đầu): tải lại
        if (s.state === "written" && !(st.data && st.data.scene_count)) open(st.id);
        if (s.state === "done" && !(st.data && st.data.video_ready)) open(st.id);
        if (last && last !== s.state) {
          if (s.state === "written") { toast("ok", "AI đã viết xong lời kể"); open(st.id); }
          if (s.state === "done") { toast("ok", "Đã dựng xong video"); open(st.id); }
          if (s.state === "error") toast("error", "Có lỗi", s.message || "");
        }
        last = s.state;
      }).catch(function () {});
    }, 1500);
  }

  /* ----------------------------------------------------------- nút */

  function wire() {
    $("st-new").addEventListener("click", function () {
      api("/api/story", { body: { title: $("st-title").value.trim(), author: $("st-author").value.trim(),
                                   format: $("st-format").value || "16:9" } })
        .then(function (d) { st.id = d.id; render(d); watch(); return loadList(d.id); })
        .then(function () { toast("ok", "Đã tạo truyện mới"); })
        .catch(fail("Không tạo được truyện"));
    });
    $("st-pick").addEventListener("change", function () { open(this.value); });
    $("st-save").addEventListener("click", function () { save(); });
    $("st-save2").addEventListener("click", function () { save(); });
    $("st-write").addEventListener("click", function () {
      var go = function () {
        save(true).then(function () {
          if ((st.data && st.data.scene_count) &&
              !confirm("Viết lại sẽ thay toàn bộ lời kể và cảnh hiện có. Tiếp tục?")) return;
          return api("/api/story/" + encodeURIComponent(st.id) + "/write", { method: "POST" })
            .then(function () { toast("ok", "AI đang viết lời kể", "Truyện dài cần vài phút."); });
        }).catch(fail("Không viết được"));
      };
      if (!st.id) {
        api("/api/story", { body: { title: $("st-title").value.trim(), author: $("st-author").value.trim(),
                                     format: $("st-format").value || "16:9" } })
          .then(function (d) { st.id = d.id; watch(); return loadList(d.id); }).then(go)
          .catch(fail("Không tạo được truyện"));
      } else {
        go();
      }
    });
    $("st-files").addEventListener("change", function () {
      if (!st.id || !this.files.length) return;
      var fd = new FormData();
      Array.prototype.forEach.call(this.files, function (f) { fd.append("files", f); });
      var input = this;
      api("/api/story/" + encodeURIComponent(st.id) + "/images", { body: fd })
        .then(function (d) {
          render(d);
          toast("ok", "Đã nhận " + (d.saved || []).length + " ảnh",
                (d.skipped || []).length ? "Bỏ qua (tên không có số cảnh): " + d.skipped.join(", ") : "");
          input.value = "";
        }).catch(fail("Tải ảnh thất bại"));
    });
    $("st-render").addEventListener("click", function () {
      if (!st.id) return;
      save(true).then(function () {
        return api("/api/story/" + encodeURIComponent(st.id) + "/render", { method: "POST" });
      }).then(function () { toast("ok", "Đang dựng video", "Theo dõi tiến độ ngay bên dưới."); })
        .catch(fail("Không dựng được"));
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!$("screen-story")) return;
    wire();
    var sty = $("st-style");               // có sẵn lựa chọn khi chưa mở truyện nào
    [["anim2d", "Hoạt hình 2D"], ["watercolor", "Tranh màu nước"], ["oil", "Tranh sơn dầu"],
     ["book", "Tranh minh hoạ sách"]].forEach(function (o) { sty.appendChild(new Option(o[1], o[0])); });
    var last = null;
    try { last = localStorage.getItem(LS_STORY); } catch (e) {}
    loadVoices().then(function () { return loadList(last); }).then(function () {
      if (last) open(last);
    });
  });
})();
