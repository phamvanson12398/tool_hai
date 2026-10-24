/* ============================================================
   Tab Truyện webtoon: truyện tranh động kiểu webtoon Hàn.
   AI viết truyện + phân cảnh, tool tự vẽ nhân vật kiểu người thật,
   nhép miệng, chèn màn hình điện thoại, dựng video 16:9.
   ============================================================ */

(function () {
  "use strict";

  var LS = "tool_hai_webtoon_id";
  var W = { id: null, data: null, polling: null };
  var EXPR_VI = { neutral: "Bình thường", worried: "Lo lắng", shocked: "Sốc", scared: "Sợ hãi", sad: "Buồn",
    crying: "Khóc", angry: "Giận", happy: "Vui", laughing: "Cười to", smirk: "Nhếch mép", tired: "Mệt mỏi",
    thinking: "Suy nghĩ", relieved: "Nhẹ nhõm", desperate: "Tuyệt vọng" };
  var POSE_VI = { down: "Tay buông", phone_ear: "Áp điện thoại", phone_look: "Xem điện thoại",
    hand_head: "Ôm đầu", hands_head: "Hai tay ôm đầu", cross: "Khoanh tay", point: "Chỉ tay", wave: "Vẫy tay",
    hands_face: "Hai tay che mặt", hands_hips: "Chống nạnh", shrug: "Nhún vai", fist: "Nắm tay", hold_out: "Chìa tay" };
  var TYPE_VI = { close: "Cận mặt", medium: "Nửa người", wide: "Toàn cảnh", two: "Hai người", phone: "Màn hình ĐT",
    black: "Màn đen" };
  var CAM_VI = { push_in: "Đẩy vào", pull_out: "Lùi ra", pan_left: "Lia trái", pan_right: "Lia phải",
    shake: "Rung", still: "Đứng yên" };
  var SCREEN_VI = { chat: "Tin nhắn", call: "Cuộc gọi", wifi: "Danh sách wifi", notice: "Thông báo",
    alert: "Cảnh báo chữ đỏ", video: "Gọi video", noise: "Nhiễu sóng", lock: "Màn hình khoá",
    loading: "Đang tải", app: "Ứng dụng" };

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
          if (!res.ok) throw new Error((d && (d.error || d.message)) || ("Lỗi " + res.status));
          return d;
        });
      });
  }
  function sel(options, value, labels) {
    var s = document.createElement("select");
    options.forEach(function (o) {
      var v = Array.isArray(o) ? o[0] : o;
      var lb = Array.isArray(o) ? o[1] : ((labels && labels[o]) || o);
      s.appendChild(new Option(lb, v));
    });
    if (value != null) s.value = value;
    return s;
  }
  function wt() { return (W.data && W.data.webtoon) || {}; }
  function opts() { return (W.data && W.data.options) || {}; }

  /* ---------------------------- tải / lưu ---------------------------- */

  function loadList(selectId) {
    return api("/api/webtoon/list").then(function (d) {
      var s = $("wt-open");
      s.innerHTML = "";
      s.appendChild(new Option("— Chọn tập —", ""));
      (d.items || []).forEach(function (it) { s.appendChild(new Option(it.title + " · " + it.id, it.id)); });
      if (selectId) s.value = selectId;
    });
  }

  function open(id) {
    if (!id) return Promise.resolve();
    return api("/api/webtoon/" + encodeURIComponent(id)).then(function (d) {
      W.id = id;
      W.data = d;
      try { localStorage.setItem(LS, id); } catch (e) {}
      render();
      var s = d.status || {};
      if (s.state === "writing" || s.state === "rendering") poll();
    }).catch(function (e) { toast("error", "Không mở được tập", e.message); });
  }

  function createNew() {
    return api("/api/webtoon", { method: "POST", body: { brief: $("wt-brief").value.trim(),
      genre: $("wt-genre").value || "thriller", language: $("wt-lang").value || "vi" } })
      .then(function (d) {
        W.id = d.id; W.data = d;
        try { localStorage.setItem(LS, d.id); } catch (e) {}
        render();
        return loadList(d.id).then(function () { return d; });
      });
  }

  function collect() {
    var b = {
      title: $("wt-title").value.trim(), brief: $("wt-brief").value.trim(), genre: $("wt-genre").value,
      language: $("wt-lang").value, minutes: parseFloat($("wt-minutes").value) || 4,
      part: parseInt($("wt-part").value, 10) || 1, cliffhanger: $("wt-cliff").value === "1",
      subtitles: $("wt-subs").value === "1", prev_summary: $("wt-prev").value
    };
    var cur = wt();
    if ((cur.characters || []).length) {
      b.characters = [];
      document.querySelectorAll("#wt-chars .wt-char").forEach(function (row) {
        var look = {};
        row.querySelectorAll("[data-look]").forEach(function (f) {
          look[f.getAttribute("data-look")] = f.type === "checkbox" ? f.checked : f.value;
        });
        b.characters.push({ id: row.getAttribute("data-id"), name: row.querySelector(".name").value,
          look: look, voice: { instruct: row.querySelector(".voice").value } });
      });
    }
    if ((cur.places || []).length) {
      b.places = [];
      document.querySelectorAll("#wt-places .wt-place").forEach(function (row) {
        b.places.push({ id: row.getAttribute("data-id"), name: row.querySelector(".name").value,
          kind: row.querySelector(".kind").value, time: row.querySelector(".time").value });
      });
    }
    b.shots = [];
    document.querySelectorAll("#wt-shots .wt-shot").forEach(function (row) {
      var s = JSON.parse(row.getAttribute("data-raw") || "{}");
      row.querySelectorAll("[data-k]").forEach(function (f) { s[f.getAttribute("data-k")] = f.value; });
      var who = row.querySelector(".lwho"), text = row.querySelector(".text");
      s.line = text && text.value.trim() ? { who: who.value, text: text.value.trim() } : {};
      var ph = row.querySelector(".phone");
      if (ph) {
        try { s.phone = JSON.parse(ph.value || "{}"); }
        catch (e) { toast("warn", "Màn hình ĐT chưa đúng dạng", "Cảnh " + row.getAttribute("data-i")); }
      }
      if (s.dur === "") delete s.dur;
      b.shots.push(s);
    });
    return b;
  }

  function save(quiet) {
    var go = W.id ? Promise.resolve() : createNew();
    return go.then(function () {
      return api("/api/webtoon/" + encodeURIComponent(W.id) + "/save", { method: "POST", body: collect() });
    }).then(function (d) {
      W.data = d;
      render();
      if (!quiet) toast("ok", "Đã lưu");
      return d;
    }).catch(function (e) { toast("error", "Lưu thất bại", e.message); });
  }

  /* ---------------------------- vẽ giao diện ---------------------------- */

  function fillSelect(id, list, value) {
    var s = $(id);
    s.innerHTML = "";
    (list || []).forEach(function (kv) { s.appendChild(new Option(kv[1], kv[0])); });
    if (value) s.value = value;
  }

  function render() {
    var d = W.data || {}, w = wt(), o = opts();
    fillSelect("wt-genre", o.genres, w.genre || "thriller");
    fillSelect("wt-lang", o.langs, w.language || "vi");
    $("wt-brief").value = w.brief || "";
    $("wt-title").value = w.title || "";
    $("wt-minutes").value = w.minutes || 4;
    $("wt-part").value = w.part || 1;
    $("wt-cliff").value = w.cliffhanger === false ? "0" : "1";
    $("wt-subs").value = w.subtitles === false ? "0" : "1";
    $("wt-prev").value = w.prev_summary || "";
    if ($("wt-open").value !== W.id && W.id) $("wt-open").value = W.id;
    renderChars();
    renderShots();
    var s = d.status || {};
    showStatus(s, d.video_ready);
  }

  function renderChars() {
    var w = wt(), o = opts(), box = $("wt-chars");
    box.innerHTML = "";
    (w.characters || []).forEach(function (c) {
      var lk = c.look || {};
      var row = el("div", "wt-char");
      row.setAttribute("data-id", c.id);
      var img = document.createElement("img");
      img.src = "/api/webtoon/" + encodeURIComponent(W.id) + "/char/" + encodeURIComponent(c.id) + ".png?v=" +
        encodeURIComponent(JSON.stringify(lk)).length + "_" + Date.now() % 100000;
      row.appendChild(img);
      var f = el("div");
      var nm = document.createElement("input");
      nm.className = "name"; nm.value = c.name || ""; nm.placeholder = "Tên";
      f.appendChild(nm);
      [["sex", [["male", "Nam"], ["female", "Nữ"]]],
       ["age", [["child", "Trẻ con"], ["teen", "Thiếu niên"], ["young", "Thanh niên"], ["adult", "Người lớn"],
                ["middle", "Trung niên"], ["old", "Người già"]]],
       ["hair", o.hairs || []], ["hair_color", o.hair_colors || []], ["top", o.tops || []],
       ["top_color", o.colors || []], ["bottom_color", o.colors || []], ["skin", o.skins || []]
      ].forEach(function (kv) {
        var s = sel(kv[1], lk[kv[0]]);
        s.setAttribute("data-look", kv[0]);
        s.title = kv[0];
        s.addEventListener("change", function () { save(true); });
        f.appendChild(s);
      });
      var g = document.createElement("label");
      var cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = !!lk.glasses; cb.setAttribute("data-look", "glasses");
      cb.addEventListener("change", function () { save(true); });
      g.appendChild(cb); g.appendChild(document.createTextNode(" kính"));
      f.appendChild(g);
      var v = document.createElement("input");
      v.className = "voice"; v.value = (c.voice || {}).instruct || ""; v.placeholder = "Giọng: vd male, middle-aged, low pitch";
      f.appendChild(v);
      row.appendChild(f);
      box.appendChild(row);
    });
    var pb = $("wt-places");
    pb.innerHTML = "";
    (w.places || []).forEach(function (p) {
      var row = el("div", "wt-place");
      row.setAttribute("data-id", p.id);
      var nm = document.createElement("input");
      nm.className = "name"; nm.value = p.name || "";
      row.appendChild(nm);
      var k = sel(o.kinds || [], p.kind); k.className = "kind";
      var tm = sel([["ngay", "Ngày"], ["dem", "Đêm"]], p.time); tm.className = "time";
      row.appendChild(k); row.appendChild(tm);
      pb.appendChild(row);
    });
  }

  function shotThumb(i) {
    return "/api/webtoon/" + encodeURIComponent(W.id) + "/preview/" + i + ".png?v=" + Date.now() % 1000000;
  }

  function renderShots() {
    var w = wt(), o = opts(), box = $("wt-shots");
    box.innerHTML = "";
    var chars = (w.characters || []).map(function (c) { return [c.id, c.name || c.id]; });
    var places = (w.places || []).map(function (p) { return [p.id, p.name || p.id]; });
    (w.shots || []).forEach(function (s, i) {
      var row = el("div", "wt-shot");
      row.setAttribute("data-i", i + 1);
      var raw = JSON.parse(JSON.stringify(s));
      row.setAttribute("data-raw", JSON.stringify(raw));
      row.appendChild(el("div", "num", String(i + 1)));
      var img = document.createElement("img");
      img.loading = "lazy";
      img.src = shotThumb(i);
      img.title = "Xem lớn";
      img.addEventListener("click", function () { $("wt-big").src = shotThumb(i).replace("preview/" + i, "preview/" + i); });
      row.appendChild(img);
      var ctl = el("div", "ctl");
      function add(k, list, labels) {
        var x = sel(list, s[k], labels);
        x.setAttribute("data-k", k);
        ctl.appendChild(x);
        return x;
      }
      add("type", o.types || [], TYPE_VI);
      add("place", places);
      if (s.type !== "phone" && s.type !== "black") {
        add("who", chars);
        add("expr", o.exprs || [], EXPR_VI);
        add("pose", o.poses || [], POSE_VI);
        add("look", [["", "Nhìn thẳng"], ["left", "Nhìn trái"], ["right", "Nhìn phải"], ["down", "Nhìn xuống"], ["up", "Nhìn lên"]]);
      }
      add("camera", o.cameras || [], CAM_VI);
      var ln = s.line || {};
      var lw = sel([["narr", "Người kể"]].concat(chars), ln.who || s.who || "narr");
      lw.className = "lwho";
      ctl.appendChild(lw);
      var tx = document.createElement("input");
      tx.className = "text"; tx.value = ln.text || ""; tx.placeholder = "Câu nói (để trống nếu không có)";
      ctl.appendChild(tx);
      if (s.type === "phone") {
        var ph = document.createElement("textarea");
        ph.className = "phone"; ph.rows = 3;
        ph.value = JSON.stringify(s.phone || { screen: "chat", data: {} });
        ph.title = "Màn hình: " + Object.keys(SCREEN_VI).map(function (k) { return k + " (" + SCREEN_VI[k] + ")"; }).join(", ");
        ctl.appendChild(ph);
      }
      row.appendChild(ctl);
      var acts = el("div", "acts");
      var up = el("button", "btn btn-sm", "↑"); up.type = "button"; up.title = "Đưa lên trước";
      up.addEventListener("click", function () {
        if (row.previousSibling) { box.insertBefore(row, row.previousSibling); }
      });
      var rm = el("button", "btn btn-sm", "✕"); rm.type = "button"; rm.title = "Bỏ cảnh này";
      rm.addEventListener("click", function () { row.parentNode.removeChild(row); });
      acts.appendChild(up); acts.appendChild(rm);
      row.appendChild(acts);
      box.appendChild(row);
    });
    if ((w.shots || []).length && !$("wt-big").getAttribute("src")) $("wt-big").src = shotThumb(0);
  }

  /* ---------------------------- việc nền ---------------------------- */

  function showStatus(s, ready) {
    var busy = s.state === "writing" || s.state === "rendering";
    $("wt-progress-wrap").hidden = !busy;
    $("wt-progress").style.width = Math.round((s.progress || 0) * 100) + "%";
    $("wt-msg").textContent = s.message || "";
    $("wt-state").textContent = s.state === "writing" ? "AI đang viết… " + Math.round((s.progress || 0) * 100) + "%" : "";
    $("wt-write").disabled = busy;
    $("wt-render").disabled = busy;
    if (ready && !busy) {
      var url = "/api/project/" + encodeURIComponent(W.id) + "/video?t=" + Date.now();
      $("wt-out").hidden = false;
      if ($("wt-video").getAttribute("data-for") !== W.id + (s.state || "")) {
        $("wt-video").src = url;
        $("wt-video").setAttribute("data-for", W.id + (s.state || ""));
      }
      $("wt-dl").href = url;
    } else if (!ready) {
      $("wt-out").hidden = true;
    }
  }

  function poll() {
    if (W.polling) clearInterval(W.polling);
    W.polling = setInterval(function () {
      if (!W.id) return;
      api("/api/project/" + encodeURIComponent(W.id) + "/status").then(function (s) {
        showStatus(s, s.video_ready);
        if (s.state !== "writing" && s.state !== "rendering") {
          clearInterval(W.polling); W.polling = null;
          if (s.state === "error") toast("error", "Có lỗi", s.message);
          if (s.state === "written") { toast("ok", "AI đã viết xong", "Xem lại phân cảnh ở mục 3"); open(W.id); }
          if (s.state === "done") { toast("ok", "Đã dựng xong video"); open(W.id); }
        }
      }).catch(function () {});
    }, 1500);
  }

  function writeAI() {
    if (!$("wt-brief").value.trim()) {
      toast("warn", "Thiếu yêu cầu", "Gõ vài câu về câu chuyện muốn làm.");
      return;
    }
    save(true).then(function () {
      return api("/api/webtoon/" + encodeURIComponent(W.id) + "/write", { method: "POST", body: {} });
    }).then(function () {
      showStatus({ state: "writing", progress: 0, message: "bắt đầu" });
      poll();
    }).catch(function (e) { toast("error", "AI viết thất bại", e.message); });
  }

  function renderVideo() {
    save(true).then(function () {
      return api("/api/webtoon/" + encodeURIComponent(W.id) + "/render", { method: "POST", body: {} });
    }).then(function () {
      showStatus({ state: "rendering", progress: 0, message: "bắt đầu" });
      poll();
    }).catch(function (e) { toast("error", "Dựng video thất bại", e.message); });
  }

  function addShot() {
    var w = wt();
    w.shots = w.shots || [];
    var last = w.shots[w.shots.length - 1] || {};
    w.shots.push({ type: "close", place: last.place || "", who: last.who || "", expr: "neutral", pose: "down",
                   camera: "push_in", line: { who: last.who || "narr", text: "" } });
    renderShots();
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!$("screen-webtoon")) return;
    $("wt-new").addEventListener("click", function () {
      W.id = null; W.data = null;
      createNew().then(function () { toast("ok", "Đã tạo tập mới"); })
        .catch(function (e) { toast("error", "Tạo tập thất bại", e.message); });
    });
    $("wt-open").addEventListener("change", function () { open(this.value); });
    $("wt-save").addEventListener("click", function () { save(false); });
    $("wt-write").addEventListener("click", writeAI);
    $("wt-render").addEventListener("click", renderVideo);
    $("wt-add").addEventListener("click", addShot);
    // lựa chọn thể loại / ngôn ngữ có sẵn cả khi chưa mở tập
    var g = [["thriller", "Giật gân / lừa đảo"], ["horror", "Kinh dị"], ["comedy", "Hài"], ["romance", "Tình cảm"],
             ["family", "Gia đình"], ["revenge", "Trả thù thoả mãn"], ["office", "Công sở"],
             ["school", "Học đường"], ["mystery", "Bí ẩn"]];
    fillSelect("wt-genre", g, "thriller");
    fillSelect("wt-lang", [["vi", "Tiếng Việt"], ["ko", "Tiếng Hàn"], ["en", "Tiếng Anh"]], "vi");
    var last = null;
    try { last = localStorage.getItem(LS); } catch (e) {}
    loadList(last).then(function () { if (last) open(last); });
  });
})();
