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
    hands_face: "Hai tay che mặt", hands_hips: "Chống nạnh", shrug: "Nhún vai", fist: "Nắm tay", hold_out: "Chìa tay",
    hold_baby: "Bế con", hold_cup: "Cầm cốc", hold_paper: "Cầm giấy tờ" };
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
      genre: $("wt-genre").value || "thriller", language: $("wt-lang").value || "ko",
      art: $("wt-art").value || "saeon" } })
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
      style: $("wt-style").value, narrator_voice: $("wt-narrv").value, art: $("wt-art").value,
      language: $("wt-lang").value, minutes: parseFloat($("wt-minutes").value) || 4,
      part: parseInt($("wt-part").value, 10) || 1, cliffhanger: $("wt-cliff").value === "1",
      subtitles: $("wt-subs").value === "1", prev_summary: $("wt-prev").value,
      summary: $("wt-summary").value
    };
    if ($("wt-bgmode")) b.bg_mode = $("wt-bgmode").value;
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
          kind: row.querySelector(".kind").value, time: row.querySelector(".time").value,
          look: row.querySelector(".look").value });
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

  /* ---------------------------- nét vẽ nhân vật ---------------------------- */

  var ARTS = [];
  function artOf(id) { return ARTS.filter(function (a) { return a.id === id; })[0]; }
  function fillArt(value) {
    var s = $("wt-art");
    if (!s) return;
    s.innerHTML = "";
    ARTS.forEach(function (a) { s.appendChild(new Option((a.custom ? "★ " : "") + a.label, a.id)); });
    s.value = artOf(value) ? value : "saeon";
    artInfo();
  }
  // tả nét đang chọn + gợi ý nét hợp thể loại + danh sách nét chị tự thêm
  function artInfo() {
    var a = artOf($("wt-art").value);
    $("wt-art-note").textContent = a ? (a.note || a.prompt) : "";
    var g = $("wt-genre").value, hint = $("wt-art-hint");
    var best = ARTS.filter(function (x) { return (x.genres || []).indexOf(g) >= 0; })[0];
    hint.innerHTML = "";
    hint.hidden = !best || best.id === $("wt-art").value;
    if (!hint.hidden) {
      hint.appendChild(document.createTextNode("Gợi ý: thể loại " + (GENRE_VI[g] || g) + " hợp nét “" +
                                               best.label.split(" — ")[0] + "”. "));
      var b = el("button", "btn btn-sm", "Dùng nét này");
      b.type = "button";
      b.addEventListener("click", function () { $("wt-art").value = best.id; artChanged(); });
      hint.appendChild(b);
    }
    var box = $("wt-art-genres");
    if (box && !box.children.length) {
      Object.keys(GENRE_VI).forEach(function (k) {
        var lb = el("label", "wt-art-g");
        var cb = document.createElement("input");
        cb.type = "checkbox"; cb.value = k;
        lb.appendChild(cb); lb.appendChild(document.createTextNode(" " + GENRE_VI[k]));
        box.appendChild(lb);
      });
    }
    var list = $("wt-art-list");
    list.innerHTML = "";
    ARTS.filter(function (x) { return x.custom; }).forEach(function (x) {
      var row = el("div", "wt-art-item");
      row.appendChild(el("b", null, x.label));
      row.appendChild(el("span", "muted", " " + x.prompt.slice(0, 140) + (x.prompt.length > 140 ? "…" : "")));
      var rm = el("button", "btn btn-sm", "Xoá");
      rm.type = "button";
      rm.addEventListener("click", function () {
        if (!window.confirm("Xoá nét vẽ “" + x.label + "”? (Ảnh đã vẽ vẫn giữ nguyên.)")) return;
        api("/api/webtoon/art-styles/" + encodeURIComponent(x.id), { method: "DELETE" }).then(function (d) {
          ARTS = d.arts || ARTS;
          var keep = $("wt-art").value === x.id ? "saeon" : $("wt-art").value;
          fillArt(keep);
          if (keep !== x.id && W.id) save(true);
        }).catch(function (e) { toast("error", "Không xoá được", e.message); });
      });
      row.appendChild(rm);
      list.appendChild(row);
    });
  }
  function artChanged() {
    artInfo();
    if (!W.id) return;
    var have = Object.keys(wt().pics || {}).length;
    save(true).then(function () {
      toast("ok", "Đã đổi nét vẽ nhân vật", have ? "Câu lệnh vẽ đã đổi theo nét mới. Ảnh vẽ theo nét cũ được đánh dấu — vẽ lại để cả truyện cùng một nét." :
            "Câu lệnh vẽ nhân vật đã đổi theo nét mới.");
    });
  }
  function addArt() {
    var genres = Array.prototype.map.call(document.querySelectorAll("#wt-art-genres input:checked"),
                                          function (c) { return c.value; });
    api("/api/webtoon/art-styles", { method: "POST", body: { label: $("wt-art-name").value,
      prompt: $("wt-art-desc").value, genres: genres } }).then(function (d) {
      ARTS = d.arts || ARTS;
      $("wt-art-name").value = ""; $("wt-art-desc").value = "";
      document.querySelectorAll("#wt-art-genres input").forEach(function (c) { c.checked = false; });
      fillArt(d.id);
      artChanged();
      toast("ok", "Đã thêm nét vẽ", "Dùng được cho mọi truyện webtoon.");
    }).catch(function (e) { toast("error", "Chưa thêm được", e.message); });
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
    fillSelect("wt-genre", o.genres, w.genre || "marriage");
    fillSelect("wt-style", o.styles || STYLE_LIST, w.style || "saeon");
    if (o.arts) ARTS = o.arts;
    fillArt(w.art || "saeon");
    fillSelect("wt-narrv", o.narr_voices || NARRV_LIST, w.narrator_voice || "own");
    fillSelect("wt-lang", o.langs, w.language || "ko");
    $("wt-brief").value = w.brief || "";
    $("wt-title").value = w.title || "";
    $("wt-minutes").value = w.minutes || 4;
    $("wt-part").value = w.part || 1;
    $("wt-cliff").value = w.cliffhanger === false ? "0" : "1";
    $("wt-subs").value = w.subtitles === false ? "0" : "1";
    $("wt-prev").value = w.prev_summary || "";
    $("wt-summary").value = w.summary || "";
    if ($("wt-open").value !== W.id && W.id) $("wt-open").value = W.id;
    renderChars();
    renderPics();
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
    renderPlaces();
  }

  /* ---------------------------- địa điểm + nền 3D ---------------------------- */

  function bgUrl(place, time) {
    return "/api/webtoon/" + encodeURIComponent(W.id) + "/bg/" + encodeURIComponent(place) + "/" + time;
  }

  function renderPlaces() {
    var w = wt(), o = opts(), pb = $("wt-places");
    pb.innerHTML = "";
    if (!(w.places || []).length) return;
    var bgs = (W.data && W.data.bgs) || [], has3d = W.data && W.data.bg3d_installed;
    var top = el("div", "wt-bg-top");
    top.appendChild(el("b", null, "Nền"));
    var mode = sel([["2d", "Tranh nền 2D kiểu webtoon (như video mẫu)"], ["3d", "Nền 3D"],
                    ["draw", "Nền vẽ tay đơn giản của tool"]], w.bg_mode || "2d");
    mode.title = "Tranh nền 2D / 3D: ảnh tool vẽ trên máy hoặc chị vẽ bằng Gemini rồi tải lên. Đổi kiểu thì vẽ lại nền.";
    mode.id = "wt-bgmode";
    mode.addEventListener("change", function () { save(true); });
    top.appendChild(mode);
    if (has3d) {
      var all = el("button", "btn btn-sm btn-primary", "Tool vẽ nền cho mọi địa điểm còn thiếu");
      all.type = "button";
      all.addEventListener("click", function () { drawBg(null, false); });
      top.appendChild(all);
    }
    top.appendChild(el("span", "muted", has3d
      ? "Máy có phần vẽ ảnh AI: tool tự vẽ (20–60 giây mỗi ảnh), hoặc chị tự vẽ bằng Gemini rồi tải lên. Địa điểm 'Nền kể chuyện' tool tự vẽ, không cần ảnh."
      : "Máy chưa cài phần vẽ ảnh AI: bấm 'Chép câu lệnh nền', vẽ bằng Gemini / ChatGPT rồi 'Tải ảnh nền'. (Muốn tool tự vẽ: chạy cai_3d.bat, cần card NVIDIA.) Địa điểm 'Nền kể chuyện' tool tự vẽ, không cần ảnh."));
    pb.appendChild(top);
    (w.places || []).forEach(function (p) {
      var row = el("div", "wt-place");
      row.setAttribute("data-id", p.id);
      var f = el("div", "wt-place-f");
      var nm = document.createElement("input");
      nm.className = "name"; nm.value = p.name || ""; nm.placeholder = "Tên địa điểm";
      f.appendChild(nm);
      var k = sel(o.kinds || [], p.kind); k.className = "kind"; k.title = "Mẫu nền vẽ tay (dùng khi chưa có nền 3D)";
      var tm = sel([["ngay", "Ngày"], ["dem", "Đêm"]], p.time); tm.className = "time";
      f.appendChild(k); f.appendChild(tm);
      var lk = document.createElement("textarea");
      lk.className = "look"; lk.rows = 3; lk.value = p.look || "";
      lk.placeholder = "Tả bối cảnh bằng tiếng Anh để vẽ nền, vd: a small public restroom inside a Seoul subway station, white tiled walls, flickering fluorescent light";
      lk.title = "Tả đúng bối cảnh trong truyện (tiếng Anh). Sửa xong bấm Lưu rồi vẽ lại nền.";
      f.appendChild(lk);
      row.appendChild(f);
      var shots = el("div", "wt-bg-list");
      bgs.filter(function (b) { return b.place === p.id; }).forEach(function (b) {
        var cell = el("div", "wt-bg");
        cell.appendChild(el("div", "sub", b.time === "dem" ? "Ban đêm" : "Ban ngày"));
        if (b.have) {
          var img = document.createElement("img");
          img.src = bgUrl(p.id, b.time) + ".png?w=1&v=" + Date.now() % 1000000;
          img.addEventListener("click", function () { window.open(bgUrl(p.id, b.time) + ".png", "_blank"); });
          cell.appendChild(img);
        } else {
          cell.appendChild(el("div", "ph", "Chưa có ảnh nền — đang dùng nền vẽ tay"));
        }
        var acts = el("div", "acts");
        var cp = el("button", "btn btn-sm", "Chép câu lệnh nền");
        cp.type = "button";
        cp.addEventListener("click", function () {
          var lookNow = lk.value.trim();
          var text = lookNow && lookNow !== b.look ? b.prompt.replace(b.look, lookNow) : b.prompt;
          copyText(text).then(function () { toast("ok", "Đã chép câu lệnh nền", "Dán vào Gemini / ChatGPT để vẽ ảnh ngang 16:9."); });
        });
        acts.appendChild(cp);
        var file = document.createElement("input");
        file.type = "file"; file.accept = "image/*"; file.hidden = true;
        var up = el("button", "btn btn-sm", b.have ? "Thay ảnh nền" : "Tải ảnh nền");
        up.type = "button";
        up.addEventListener("click", function () { file.click(); });
        file.addEventListener("change", function () {
          if (!file.files || !file.files[0]) return;
          var fd = new FormData();
          fd.append("file", file.files[0]);
          up.disabled = true; up.textContent = "Đang tải...";
          api(bgUrl(p.id, b.time), { method: "POST", body: fd }).then(function (d) {
            W.data = d; renderPlaces(); refreshThumbs(); toast("ok", "Đã thêm ảnh nền");
          }).catch(function (e) { up.disabled = false; toast("error", "Tải ảnh thất bại", e.message); });
        });
        acts.appendChild(file); acts.appendChild(up);
        if (has3d) {
          var dr = el("button", "btn btn-sm", b.have ? "Tool vẽ lại" : "Tool vẽ nền");
          dr.type = "button";
          dr.addEventListener("click", function () { drawBg([p.id], b.have); });
          acts.appendChild(dr);
        }
        if (b.have) {
          var rm = el("button", "btn btn-ghost btn-sm", "Bỏ nền");
          rm.type = "button";
          rm.addEventListener("click", function () {
            api(bgUrl(p.id, b.time) + "/delete", { method: "POST", body: {} }).then(function (d) {
              W.data = d; renderPlaces(); refreshThumbs();
            }).catch(function (e) { toast("error", "Xoá thất bại", e.message); });
          });
          acts.appendChild(rm);
        }
        cell.appendChild(acts);
        shots.appendChild(cell);
      });
      row.appendChild(shots);
      pb.appendChild(row);
    });
  }

  function drawBg(places, force) {
    save(true).then(function () {
      return api("/api/webtoon/" + encodeURIComponent(W.id) + "/bg3d", { method: "POST",
        body: { places: places || [], force: !!force } });
    }).then(function () {
      showStatus({ state: "drawing", progress: 0, message: "nạp mô hình vẽ 3D (lần đầu mất 1–2 phút)" });
      poll();
    }).catch(function (e) { toast("error", "Chưa vẽ được nền 3D", e.message); });
  }

  /* ---------------------------- ảnh AI nhân vật ---------------------------- */

  function picUrl(cid, key) {
    return "/api/webtoon/" + encodeURIComponent(W.id) + "/pic/" + encodeURIComponent(cid) + "/" +
      encodeURIComponent(key);
  }
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    var ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
    return Promise.resolve();
  }
  function picLabel(n) {
    var t = POSE_VI[n.pose] || n.pose;
    if (n.expr && n.expr !== "neutral") t += " · " + (EXPR_VI[n.expr] || n.expr);
    return t;
  }

  function renderPics() {
    var box = $("wt-pics");
    if (!box) return;
    box.innerHTML = "";
    var w = wt(), need = (W.data && W.data.pics_needed) || [], have = w.pics || {};
    if (need.some(function (n) { return !n.have; })) {
      var top = el("div", "row-actions");
      var all = el("a", "btn btn-sm", "Tải file câu lệnh — tất cả nhân vật");
      all.href = promptsUrl(null);
      top.appendChild(all);
      top.appendChild(el("span", "muted", "Mỗi dòng một câu lệnh (chỉ những ảnh còn thiếu), đúng thứ tự các ô."));
      box.appendChild(top);
    }
    (w.characters || []).forEach(function (c) {
      var items = need.filter(function (n) { return n.cid === c.id; });
      if (!items.length) return;
      var wrap = el("div");
      var done = items.filter(function (n) { return n.have; }).length;
      var miss = items.filter(function (n) { return !n.have; });
      var head = el("div", "wt-pics-head");
      head.appendChild(el("h3", null, (c.name || c.id) + " — " + done + "/" + items.length + " ảnh"));
      if (miss.length) {
        var dl = el("a", "btn btn-sm", "Tải file câu lệnh (" + miss.length + " dòng)");
        dl.href = promptsUrl(c.id);
        head.appendChild(dl);
        var many = document.createElement("input");
        many.type = "file"; many.accept = "image/*"; many.multiple = true; many.hidden = true;
        var mb = el("button", "btn btn-sm btn-primary", "Tải nhiều ảnh cùng lúc");
        mb.type = "button";
        mb.title = "Chọn cùng lúc các ảnh đã tạo theo file câu lệnh: ảnh tải về trước điền vào dòng trước";
        mb.addEventListener("click", function () { many.click(); });
        many.addEventListener("change", function () { bulkUpload(c, miss, many.files, mb); });
        head.appendChild(many); head.appendChild(mb);
      }
      wrap.appendChild(head);
      var row = el("div", "wt-pic-row");
      items.forEach(function (n) {
        var meta = (have[c.id] || {})[n.key];
        var card = el("div", "wt-pic" + (n.have ? "" : " missing") + (n.required ? " req" : ""));
        card.appendChild(el("div", "lb", picLabel(n)));
        var line = miss.indexOf(n);
        card.appendChild(el("div", "sub", (line >= 0 ? "Dòng " + (line + 1) + " · " : "") +
          (n.shots ? n.shots + " cảnh" : "ảnh gốc") + (n.required ? "" : " · nên có")));
        if (n.have && meta) {
          var img = document.createElement("img");
          img.src = picUrl(c.id, n.key) + ".png?v=" + Date.now() % 1000000;
          img.title = "Bấm để chỉnh điểm mắt / miệng";
          img.addEventListener("click", function () { openMark(c.id, n.key, meta); });
          card.appendChild(img);
          if ((meta.art || "saeon") !== (w.art || "saeon")) {
            var ao = artOf(meta.art || "saeon");
            card.appendChild(el("div", "warn", "Ảnh vẽ theo nét cũ (" + (ao ? ao.label.split(" — ")[0] : meta.art) +
                                ") — chép câu lệnh mới để vẽ lại cho cùng nét"));
          }
          if (meta.sure === false) {
            card.appendChild(el("div", "warn", "Tool chưa tìm chắc mắt / miệng nên chưa nhép miệng — bấm vào ảnh để đánh dấu"));
          } else if (meta.auto) {
            card.appendChild(el("div", "sub", "Mắt, miệng do tool tự tìm — bấm ảnh để kiểm tra"));
          }
          openRow(card, c, n, meta);
        } else {
          card.appendChild(el("div", "ph", "Chưa có ảnh"));
        }
        var cp = el("button", "btn btn-sm", "Chép câu lệnh vẽ");
        cp.type = "button";
        cp.addEventListener("click", function () {
          copyText(n.prompt).then(function () { toast("ok", "Đã chép câu lệnh", "Dán vào Gemini / ChatGPT để vẽ."); });
        });
        card.appendChild(cp);
        var file = document.createElement("input");
        file.type = "file"; file.accept = "image/*"; file.hidden = true;
        file.addEventListener("change", function () {
          if (!file.files || !file.files[0]) return;
          var fd = new FormData();
          fd.append("file", file.files[0]);
          up.disabled = true; up.textContent = "Đang xử lý...";
          api(picUrl(c.id, n.key), { method: "POST", body: fd }).then(function (d) {
            W.data = d; renderPics(); renderChars(); refreshThumbs();
            var m = ((d.webtoon.pics || {})[c.id] || {})[n.key];
            toast("ok", "Đã tải ảnh", m && m.auto ? "Bấm vào ảnh để kiểm tra điểm mắt / miệng." : "");
          }).catch(function (e) {
            up.disabled = false; up.textContent = "Tải ảnh lên";
            toast("error", "Tải ảnh thất bại", e.message);
          });
        });
        var up = el("button", "btn btn-sm" + (n.have ? "" : " btn-primary"), n.have ? "Thay ảnh" : "Tải ảnh lên");
        up.type = "button";
        up.addEventListener("click", function () { file.click(); });
        card.appendChild(file); card.appendChild(up);
        if (n.have) {
          var rm = el("button", "btn btn-ghost btn-sm", "Xoá ảnh");
          rm.type = "button";
          rm.addEventListener("click", function () {
            api(picUrl(c.id, n.key) + "/delete", { method: "POST", body: {} }).then(function (d) {
              W.data = d; renderPics(); renderChars(); refreshThumbs();
            }).catch(function (e) { toast("error", "Xoá thất bại", e.message); });
          });
          card.appendChild(rm);
        }
        row.appendChild(card);
      });
      wrap.appendChild(row);
      box.appendChild(wrap);
    });
    if (!box.childNodes.length) box.appendChild(el("p", "hint", "Bấm 'AI viết truyện & phân cảnh' trước — tool sẽ liệt kê những ảnh cần vẽ."));
  }

  function promptsUrl(cid) {
    return "/api/webtoon/" + encodeURIComponent(W.id) + "/pics_prompts.txt" + (cid ? "?cid=" + encodeURIComponent(cid) : "");
  }

  // nhiều ảnh một lần: xếp theo lúc tải về (cũ trước), cùng lúc thì theo tên -> điền lần lượt
  // vào các ô còn thiếu, đúng thứ tự dòng trong file câu lệnh
  function bulkUpload(c, miss, fileList, btn) {
    var files = Array.prototype.slice.call(fileList || []);
    if (!files.length) return;
    files.sort(function (a, b) {
      return (a.lastModified - b.lastModified) ||
        a.name.localeCompare(b.name, undefined, { numeric: true });
    });
    var n = Math.min(files.length, miss.length);
    if (files.length > miss.length) {
      toast("warn", "Thừa ảnh", "Chọn " + files.length + " ảnh nhưng chỉ còn " + miss.length +
        " ô trống — bỏ qua " + (files.length - miss.length) + " ảnh cuối.");
    }
    btn.disabled = true;
    var k = 0, bad = 0;
    function next() {
      if (k >= n) {
        btn.disabled = false;
        renderPics(); renderChars(); refreshThumbs();
        toast(bad ? "warn" : "ok", "Đã tải " + (n - bad) + "/" + n + " ảnh cho " + (c.name || c.id),
          "Kiểm tra từng ô xem ảnh có đúng tư thế không; sai thì bấm 'Thay ảnh'.");
        return;
      }
      btn.textContent = "Đang xử lý " + (k + 1) + "/" + n + "...";
      var fd = new FormData();
      fd.append("file", files[k]);
      api(picUrl(c.id, miss[k].key), { method: "POST", body: fd })
        .then(function (d) { W.data = d; })
        .catch(function (e) { bad += 1; toast("error", "Ảnh " + files[k].name + " lỗi", e.message); })
        .then(function () { k += 1; next(); });
    }
    next();
  }

  // ảnh miệng mở (tuỳ chọn): AI sửa ảnh gốc cho mở miệng; khi nói tool hoà miệng thật vào
  function openRow(card, c, n, meta) {
    var o = meta.open;
    if (o) {
      card.appendChild(el("div", o.score < 0.5 ? "warn" : "ok",
        o.score < 0.5 ? "Ảnh miệng mở lệch nhiều so với ảnh gốc — nên tạo lại" : "✓ Có ảnh miệng mở (nhép miệng thật)"));
      var rm = el("button", "btn btn-ghost btn-sm", "Bỏ ảnh miệng mở");
      rm.type = "button";
      rm.addEventListener("click", function () {
        api(picUrl(c.id, n.key) + "/open/delete", { method: "POST", body: {} }).then(function (d) {
          W.data = d; renderPics(); refreshThumbs();
        }).catch(function (e) { toast("error", "Xoá thất bại", e.message); });
      });
      card.appendChild(rm);
      return;
    }
    var cp = el("button", "btn btn-sm", "Chép câu lệnh miệng mở");
    cp.type = "button";
    cp.title = "Gửi kèm ảnh này cho Gemini / ChatGPT, dán câu lệnh: AI sửa đúng ảnh này cho mở miệng";
    cp.addEventListener("click", function () {
      copyText((W.data && W.data.prompt_open) || "").then(function () {
        toast("ok", "Đã chép câu lệnh miệng mở", "Gửi KÈM ảnh này (tải ảnh gốc của bạn) rồi dán câu lệnh.");
      });
    });
    var file = document.createElement("input");
    file.type = "file"; file.accept = "image/*"; file.hidden = true;
    var up = el("button", "btn btn-sm", "Tải ảnh miệng mở");
    up.type = "button";
    up.title = "Không bắt buộc. Có ảnh này thì miệng nhép là miệng thật của tranh, hợp với tranh kiểu người thật.";
    up.addEventListener("click", function () { file.click(); });
    file.addEventListener("change", function () {
      if (!file.files || !file.files[0]) return;
      var fd = new FormData();
      fd.append("file", file.files[0]);
      up.disabled = true; up.textContent = "Đang căn khớp...";
      api(picUrl(c.id, n.key) + "/open", { method: "POST", body: fd }).then(function (d) {
        W.data = d; renderPics(); refreshThumbs();
        var m = ((d.webtoon.pics || {})[c.id] || {})[n.key] || {};
        toast(m.open && m.open.score < 0.5 ? "warn" : "ok", "Đã thêm ảnh miệng mở",
          m.open && m.open.score < 0.5 ? "Hai ảnh lệch nhau nhiều, nên nhờ AI sửa lại giữ nguyên khung hình." : "");
      }).catch(function (e) {
        up.disabled = false; up.textContent = "Tải ảnh miệng mở";
        toast("error", "Tải ảnh thất bại", e.message);
      });
    });
    card.appendChild(cp); card.appendChild(file); card.appendChild(up);
  }

  function refreshThumbs() {
    document.querySelectorAll("#wt-shots img").forEach(function (img, i) { img.src = shotThumb(i); });
  }

  // chỉnh điểm mắt / miệng: bấm mắt bên trái ảnh, mắt bên phải ảnh, rồi giữa miệng
  var MK = { cid: null, key: null, img: null, pts: [], k: 1 };
  var MK_TIP = ["Bấm vào MẮT bên trái ảnh (giữa con ngươi)", "Bấm vào MẮT bên phải ảnh",
                "Bấm vào giữa MIỆNG (đường môi)", "Xong — bấm Lưu điểm"];
  function drawMark() {
    var cv = $("wt-mark-cv"), g = cv.getContext("2d");
    g.clearRect(0, 0, cv.width, cv.height);
    g.drawImage(MK.img, 0, 0, cv.width, cv.height);
    MK.pts.forEach(function (p, i) {
      g.beginPath();
      g.arc(p[0] * MK.k, p[1] * MK.k, 7, 0, Math.PI * 2);
      g.lineWidth = 3; g.strokeStyle = i < 2 ? "#00b7ff" : "#ff2d6f"; g.stroke();
    });
    $("wt-mark-tip").textContent = MK_TIP[Math.min(3, MK.pts.length)];
  }
  function openMark(cid, key, meta) {
    MK.cid = cid; MK.key = key;
    MK.pts = (meta.eyes || []).map(function (p) { return p.slice(); });
    if (meta.mouth) MK.pts.push(meta.mouth.slice());
    var img = new Image();
    img.onload = function () {
      MK.img = img;
      var maxH = Math.min(window.innerHeight - 160, 640), maxW = Math.min(window.innerWidth - 60, 900);
      MK.k = Math.min(maxH / img.naturalHeight, maxW / img.naturalWidth, 1);
      var cv = $("wt-mark-cv");
      cv.width = Math.round(img.naturalWidth * MK.k); cv.height = Math.round(img.naturalHeight * MK.k);
      $("wt-mark").hidden = false;
      drawMark();
      $("wt-mark-tip").textContent = "Vòng xanh = mắt, vòng hồng = miệng. Sai thì bấm 'Bấm lại từ đầu' rồi bấm lại 3 điểm.";
    };
    img.src = picUrl(cid, key) + ".png?v=" + Date.now() % 1000000;
  }
  function initMark() {
    var cv = $("wt-mark-cv");
    if (!cv) return;
    cv.addEventListener("click", function (ev) {
      if (MK.pts.length >= 3) return;
      var r = cv.getBoundingClientRect();
      var sx = cv.width / r.width, sy = cv.height / r.height;
      MK.pts.push([(ev.clientX - r.left) * sx / MK.k, (ev.clientY - r.top) * sy / MK.k]);
      drawMark();
    });
    $("wt-mark-reset").addEventListener("click", function () { MK.pts = []; drawMark(); });
    $("wt-mark-close").addEventListener("click", function () { $("wt-mark").hidden = true; });
    $("wt-mark-save").addEventListener("click", function () {
      if (MK.pts.length < 3) { toast("warn", "Chưa đủ điểm", "Bấm đủ 2 mắt và miệng."); return; }
      api(picUrl(MK.cid, MK.key) + "/marks", { method: "POST",
        body: { eyes: [MK.pts[0], MK.pts[1]], mouth: MK.pts[2] } }).then(function (d) {
        W.data = d; $("wt-mark").hidden = true; renderPics(); refreshThumbs();
        toast("ok", "Đã lưu điểm mắt / miệng");
      }).catch(function (e) { toast("error", "Lưu thất bại", e.message); });
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
        add("front", [["", "Không đạo cụ"], ["table", "Bàn cà phê + cốc"], ["dining", "Bàn ăn (cơm canh)"],
                      ["bed", "Giường + chăn"], ["car", "Trong xe (vô lăng)"], ["desk", "Bàn làm việc + laptop"],
                      ["sofa", "Ghế sofa + bàn trà"]]).title = "Đạo cụ quanh người";
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
    var busy = s.state === "writing" || s.state === "rendering" || s.state === "drawing";
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
        if (s.state !== "writing" && s.state !== "rendering" && s.state !== "drawing") {
          clearInterval(W.polling); W.polling = null;
          if (s.state === "error") toast("error", "Có lỗi", s.message);
          if (s.state === "written") { toast("ok", "AI đã viết xong", "Xem lại phân cảnh ở mục 3"); open(W.id); }
          if (s.state === "done") { toast("ok", "Đã dựng xong video"); open(W.id); }
          if (s.state === "drawn") { toast("ok", "Xong nền 3D", s.message); open(W.id); }
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

  /* ---------------------------- ý tưởng tham khảo ---------------------------- */
  var LS_IDEAS = "tool_hai_webtoon_ideas_seen";
  var STYLE_LIST = [["saeon", "Kể chuyện 사연 (nhân vật chính tự kể + thoại, như kênh 썰)"],
                    ["drama", "Toàn thoại (rất ít lời kể)"]];
  var NARRV_LIST = [["own", "Giọng riêng cho người kể (khác mọi nhân vật)"],
                    ["self", "Lời kể dùng giọng nhân vật chính (nhép miệng khi kể)"]];
  var GENRE_VI = {};

  function seenIdeas() {
    try { return JSON.parse(localStorage.getItem(LS_IDEAS) || "[]"); } catch (e) { return []; }
  }
  function moreIdeas() {
    var btn = $("wt-ideas-btn");
    btn.disabled = true; btn.textContent = "AI đang nghĩ...";
    $("wt-ideas-state").textContent = "Khoảng 20–60 giây.";
    api("/api/webtoon/ideas", { method: "POST", body: {
      genre: $("wt-idea-genre").value, language: $("wt-lang").value || "ko", avoid: seenIdeas(),
      style: $("wt-style").value || "saeon" } })
      .then(function (d) {
        var list = d.ideas || [];
        try {
          localStorage.setItem(LS_IDEAS, JSON.stringify(seenIdeas().concat(list.map(function (x) { return x.title; })).slice(-60)));
        } catch (e) {}
        var box = $("wt-ideas");
        box.innerHTML = "";
        list.forEach(function (it) {
          var card = el("div", "wt-idea");
          card.appendChild(el("div", "t", it.title));
          card.appendChild(el("div", "g", GENRE_VI[it.genre] || it.genre));
          if (it.hook) card.appendChild(el("div", "h", "“" + it.hook + "”"));
          card.appendChild(el("div", null, it.brief));
          if (it.why) card.appendChild(el("div", "w", it.why));
          var use = el("button", "btn btn-sm btn-primary", "Dùng ý này");
          use.type = "button";
          use.addEventListener("click", function () {
            $("wt-brief").value = it.brief;
            if (it.genre) $("wt-genre").value = it.genre;
            if (!$("wt-title").value.trim()) $("wt-title").value = it.title;
            if (W.id) save(true);
            toast("ok", "Đã điền ý tưởng", "Bấm 'AI viết truyện & phân cảnh' để viết.");
            $("wt-brief").scrollIntoView({ behavior: "smooth", block: "center" });
          });
          card.appendChild(use);
          box.appendChild(card);
        });
        $("wt-ideas-state").textContent = "Bấm lại để có loạt khác.";
      })
      .catch(function (e) {
        $("wt-ideas-state").textContent = "";
        toast("error", "Chưa gợi ý được", e.message);
      })
      .then(function () { btn.disabled = false; btn.textContent = "Gợi ý ý tưởng mới"; });
  }

  /* ---------------------------- làm series ---------------------------- */
  function summaryAI() {
    var b = $("wt-sum-ai");
    b.disabled = true; b.textContent = "AI đang tóm tắt...";
    save(true).then(function () {
      return api("/api/webtoon/" + encodeURIComponent(W.id) + "/summary", { method: "POST", body: { ai: true } });
    }).then(function (d) {
      W.data = d; $("wt-summary").value = d.webtoon.summary || "";
      toast("ok", "Đã tóm tắt tập này");
    }).catch(function (e) { toast("error", "Chưa tóm tắt được", e.message); })
      .then(function () { b.disabled = false; b.textContent = "Tóm tắt bằng AI"; });
  }
  function nextPart() {
    if (!W.id) return;
    save(true).then(function () {
      return api("/api/webtoon/" + encodeURIComponent(W.id) + "/next", { method: "POST", body: {} });
    }).then(function (d) {
      W.id = d.id; W.data = d;
      try { localStorage.setItem(LS, d.id); } catch (e) {}
      return loadList(d.id).then(function () {
        render();
        toast("ok", "Đã tạo phần " + (d.webtoon.part || ""), "Bấm 'AI viết truyện & phân cảnh' để viết tiếp.");
        $("wt-brief").scrollIntoView({ behavior: "smooth", block: "center" });
      });
    }).catch(function (e) { toast("error", "Chưa tạo được phần tiếp theo", e.message); });
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
    initMark();
    $("wt-sum-ai").addEventListener("click", summaryAI);
    $("wt-next").addEventListener("click", nextPart);
    $("wt-sum-copy").addEventListener("click", function () {
      copyText($("wt-summary").value || "").then(function () { toast("ok", "Đã chép nội dung tập này"); });
    });
    // lựa chọn thể loại / ngôn ngữ có sẵn cả khi chưa mở tập
    var g = [["marriage", "Hôn nhân / nhà chồng (사연)"], ["thriller", "Giật gân / lừa đảo"], ["horror", "Kinh dị"], ["comedy", "Hài"], ["romance", "Tình cảm"],
             ["family", "Gia đình"], ["revenge", "Trả thù thoả mãn"], ["office", "Công sở"],
             ["school", "Học đường"], ["mystery", "Bí ẩn"]];
    fillSelect("wt-genre", g, "marriage");
    fillSelect("wt-style", STYLE_LIST, "saeon");
    fillSelect("wt-narrv", NARRV_LIST, "own");
    g.forEach(function (kv) { GENRE_VI[kv[0]] = kv[1]; });
    api("/api/webtoon/art-styles").then(function (d) {
      if (!ARTS.length) { ARTS = d.arts || []; fillArt((wt() || {}).art || "saeon"); }
    }).catch(function () {});
    $("wt-art").addEventListener("change", artChanged);
    $("wt-genre").addEventListener("change", artInfo);
    $("wt-art-save").addEventListener("click", addArt);
    fillSelect("wt-idea-genre", [["", "Mọi thể loại"]].concat(g), "");
    $("wt-ideas-btn").addEventListener("click", moreIdeas);
    fillSelect("wt-lang", [["ko", "Tiếng Hàn"], ["vi", "Tiếng Việt"], ["en", "Tiếng Anh"]], "ko");
    var last = null;
    try { last = localStorage.getItem(LS); } catch (e) {}
    loadList(last).then(function () { if (last) open(last); });
  });
})();
