/* Tab "2ch": video dọc 9:16 kiểu Shorts Nhật. AI viết truyện tiếng Nhật, mỗi câu một
   cảnh (nhân vật / hai người / hình trong kho / đồ vật); ảnh nhân vật vẽ bằng AI theo câu
   lệnh tool soạn; dựng video có giọng tiếng Nhật. */
(function () {
  "use strict";

  var LS = "tool_hai_2ch_id";
  var N = { id: null, data: null, polling: null };

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
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
    if (body && !(body instanceof FormData)) { headers["Content-Type"] = "application/json"; body = JSON.stringify(body); }
    return fetch(path, { method: opts.method || (body ? "POST" : "GET"), headers: headers, body: body })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (d) {
          if (!res.ok) throw new Error((d && d.error) || ("Lỗi " + res.status));
          return d;
        });
      });
  }
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    var ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
    return Promise.resolve();
  }
  function st() { return (N.data && N.data.nichan) || {}; }
  function opts() { return (N.data && N.data.options) || {}; }
  function base() { return "/api/2ch/" + encodeURIComponent(N.id); }
  function sel(list, value) {
    var s = document.createElement("select");
    list.forEach(function (kv) { s.appendChild(new Option(kv[1], kv[0])); });
    if (value !== undefined) s.value = value;
    return s;
  }
  function fillSelect(id, list, value) {
    var s = $(id);
    s.innerHTML = "";
    (list || []).forEach(function (kv) { s.appendChild(new Option(kv[1], kv[0])); });
    if (value) s.value = value;
  }
  function picker(accept, cb) {
    var f = document.createElement("input");
    f.type = "file"; f.accept = accept || "image/*";
    f.addEventListener("change", function () { if (f.files && f.files[0]) cb(f.files[0]); });
    f.click();
  }
  function upload(url, file) {
    var fd = new FormData();
    fd.append("file", file);
    return api(url, { method: "POST", body: fd });
  }

  /* ---------------------------- mở / tạo / lưu ---------------------------- */

  function loadList(selectId) {
    return api("/api/2ch/list").then(function (d) {
      var s = $("nc-open");
      s.innerHTML = "";
      s.appendChild(new Option("— chọn —", ""));
      (d.items || []).forEach(function (it) { s.appendChild(new Option(it.title + " · " + it.id, it.id)); });
      if (selectId) s.value = selectId;
    });
  }
  function open(id) {
    if (!id) return Promise.resolve();
    return api("/api/2ch/" + encodeURIComponent(id)).then(function (d) {
      N.id = d.id; N.data = d;
      try { localStorage.setItem(LS, d.id); } catch (e) {}
      render();
      var s = d.status || {};
      if (s.state === "writing" || s.state === "rendering") poll();
    }).catch(function (e) { toast("error", "Không mở được", e.message); });
  }
  function createNew() {
    return api("/api/2ch", { method: "POST", body: { brief: $("nc-brief").value.trim(), genre: $("nc-genre").value } })
      .then(function (d) {
        N.id = d.id; N.data = d;
        try { localStorage.setItem(LS, d.id); } catch (e) {}
        return loadList(d.id).then(function () { return d; });
      });
  }
  function collectHead() {
    return {
      brief: $("nc-brief").value, genre: $("nc-genre").value, minutes: parseFloat($("nc-minutes").value) || 3,
      voice_mode: $("nc-voicemode").value, cta: $("nc-cta").value === "1", art: $("nc-art").value,
      title1: $("nc-t1").value.trim(), title2: $("nc-t2").value.trim(),
      narrator: { voice: ((st().narrator || {}).voice) || "", instruct: $("nc-narr").value.trim() }
    };
  }
  function collectAll() {
    var b = collectHead();
    if (!N.data) return b;
    b.characters = Array.prototype.map.call(document.querySelectorAll("#nc-chars .nc-char"), function (row) {
      var c = JSON.parse(row.getAttribute("data-raw"));
      c.name = row.querySelector("[data-k=name]").value;
      c.desc_en = row.querySelector("[data-k=desc]").value;
      c.voice = { voice: (c.voice || {}).voice || "", instruct: row.querySelector("[data-k=voice]").value };
      return c;
    });
    b.places = Array.prototype.map.call(document.querySelectorAll("#nc-places .nc-place"), function (row) {
      var p = JSON.parse(row.getAttribute("data-raw"));
      row.querySelectorAll("[data-k]").forEach(function (f) { p[f.getAttribute("data-k")] = f.value; });
      return p;
    });
    b.scenes = Array.prototype.map.call(document.querySelectorAll("#nc-scenes .nc-scene"), sceneOf);
    return b;
  }
  function save(quiet, all) {
    var go = N.id ? Promise.resolve() : createNew();
    return go.then(function () {
      return api(base() + "/save", { body: all === false ? collectHead() : collectAll() });
    }).then(function (d) {
      N.data = d;
      render();
      if (!quiet) toast("ok", "Đã lưu");
      return d;
    }).catch(function (e) { toast("error", "Lưu thất bại", e.message); });
  }

  /* ---------------------------- vẽ giao diện ---------------------------- */

  function render() {
    var s = st(), o = opts();
    fillSelect("nc-genre", o.genres, s.genre || "kando");
    fillSelect("nc-voicemode", o.voice_modes, s.voice_mode || "cast");
    fillSelect("nc-art", o.arts, s.art || "flat");
    $("nc-brief").value = s.brief || "";
    $("nc-minutes").value = s.minutes || 3;
    $("nc-cta").value = s.cta === false ? "0" : "1";
    $("nc-t1").value = s.title1 || "";
    $("nc-t2").value = s.title2 || "";
    $("nc-narr").value = (s.narrator || {}).instruct || "";
    if ($("nc-open").value !== N.id && N.id) $("nc-open").value = N.id;
    renderChars();
    renderStickers(o.stickers);
    renderPlaces();
    renderScenes();
    showStatus((N.data && N.data.status) || {}, N.data && N.data.video_ready);
  }

  function emoVi(e) { return (opts().emo_vi || {})[e] || e; }

  // thanh "Tải file câu lệnh" + "Tải nhiều ảnh cùng lúc" (giống tab Webtoon): miss = các ô còn
  // thiếu đúng thứ tự dòng trong file, mỗi ô {url, label}
  function promptBar(kind, cid, miss, what) {
    var bar = el("div", "row-actions nc-bar");
    if (!miss.length) { bar.appendChild(el("span", "muted", "✓ Đã đủ ảnh " + what)); return bar; }
    var dl = el("a", "btn btn-sm", "Tải file câu lệnh " + what + " (" + miss.length + " dòng)");
    dl.href = base() + "/prompts/" + kind + ".txt" + (cid ? "?cid=" + encodeURIComponent(cid) : "");
    bar.appendChild(dl);
    var many = document.createElement("input");
    many.type = "file"; many.accept = "image/*"; many.multiple = true; many.hidden = true;
    var mb = el("button", "btn btn-sm btn-primary", "Tải nhiều ảnh cùng lúc");
    mb.type = "button";
    mb.title = "Chọn cùng lúc các ảnh đã vẽ theo file câu lệnh: ảnh tải về trước điền vào dòng trước";
    mb.addEventListener("click", function () { many.click(); });
    many.addEventListener("change", function () { bulkUpload(miss, many.files, mb); });
    bar.appendChild(many); bar.appendChild(mb);
    bar.appendChild(el("span", "muted", "Mỗi dòng một câu lệnh (chỉ ảnh còn thiếu), đúng thứ tự các ô."));
    return bar;
  }

  // nhiều ảnh một lần: xếp theo lúc tải về (cũ trước), cùng lúc thì theo tên -> điền lần lượt
  function bulkUpload(miss, fileList, btn) {
    var files = Array.prototype.slice.call(fileList || []);
    if (!files.length) return;
    files.sort(function (a, b) {
      return (a.lastModified - b.lastModified) || a.name.localeCompare(b.name, undefined, { numeric: true });
    });
    if (files.length > miss.length) {
      toast("warn", "Thừa ảnh", "Chọn " + files.length + " ảnh nhưng chỉ còn " + miss.length +
        " ô trống — bỏ qua " + (files.length - miss.length) + " ảnh cuối.");
    }
    var n = Math.min(files.length, miss.length), k = 0, bad = 0;
    btn.disabled = true;
    function next() {
      if (k >= n) {
        btn.disabled = false;
        open(N.id);
        toast(bad ? "warn" : "ok", "Đã tải " + (n - bad) + "/" + n + " ảnh",
          "Kiểm tra từng ô xem ảnh có đúng không; sai thì bấm 'Thay ảnh'.");
        return;
      }
      btn.textContent = "Đang xử lý " + (k + 1) + "/" + n + "...";
      upload(miss[k].url, files[k])
        .catch(function (e) { bad += 1; toast("error", "Ảnh " + files[k].name + " lỗi", e.message); })
        .then(function () { k += 1; next(); });
    }
    next();
  }
  function picMiss(cid) {
    return ((N.data && N.data.pics_needed) || []).filter(function (n) { return !n.have && (!cid || n.cid === cid); })
      .map(function (n) { return { url: base() + "/pic/" + encodeURIComponent(n.cid) + "/" + n.emo }; });
  }

  function renderChars() {
    var box = $("nc-chars"), s = st(), need = (N.data && N.data.pics_needed) || [];
    box.innerHTML = "";
    if (!(s.characters || []).length) { box.appendChild(el("p", "muted", "Chưa có nhân vật — bấm 'AI viết truyện' ở mục 1.")); return; }
    box.appendChild(promptBar("chars", null, picMiss(null), "— tất cả nhân vật"));
    (s.characters || []).forEach(function (c) {
      var row = el("div", "nc-char");
      row.setAttribute("data-raw", JSON.stringify(c));
      row.appendChild(el("b", null, c.name || c.id));
      row.appendChild(promptBar("chars", c.id, picMiss(c.id), "của " + (c.name || c.id)));
      var fr = el("div", "field-row");
      [["name", "Tên", c.name], ["desc", "Ngoại hình (tiếng Anh, dùng cho câu lệnh vẽ)", c.desc_en],
       ["voice", "Giọng (mô tả, tuỳ chọn)", (c.voice || {}).instruct || ""]].forEach(function (f) {
        var fd = el("div", "field");
        fd.appendChild(el("label", null, f[1]));
        var inp = document.createElement("input");
        inp.type = "text"; inp.value = f[2] || ""; inp.setAttribute("data-k", f[0]);
        inp.addEventListener("change", function () { save(true); });
        fd.appendChild(inp);
        fr.appendChild(fd);
      });
      row.appendChild(fr);
      var pics = el("div", "nc-pics");
      var have = (s.pics || {})[c.id] || {};
      need.filter(function (n) { return n.cid === c.id; }).forEach(function (n) {
        var card = el("div", "nc-pic" + (n.have ? " have" : ""));
        card.appendChild(el("b", null, emoVi(n.emo) + (n.emo === "neutral" ? " (ảnh gốc)" : "")));
        card.appendChild(el("span", "muted", n.scenes ? n.scenes + " cảnh" : "vẽ trước tiên"));
        var url = base() + "/pic/" + encodeURIComponent(c.id) + "/" + n.emo;
        if (n.have) {
          var img = document.createElement("img");
          img.src = url + "?v=" + ((have[n.emo] || {}).v || "0");
          card.appendChild(img);
        }
        var cp = el("button", "btn btn-sm", "Chép câu lệnh vẽ");
        cp.type = "button";
        cp.addEventListener("click", function () {
          copyText(n.prompt).then(function () { toast("ok", "Đã chép câu lệnh", n.emo === "neutral" ? "Dán vào Gemini / ChatGPT để vẽ." : "Gửi KÈM ảnh gốc của nhân vật rồi dán câu lệnh."); });
        });
        card.appendChild(cp);
        var up = el("button", "btn btn-sm" + (n.have ? "" : " btn-primary"), n.have ? "Thay ảnh" : "Tải ảnh lên");
        up.type = "button";
        up.addEventListener("click", function () {
          picker("image/*", function (file) {
            up.disabled = true; up.textContent = "Đang xử lý…";
            upload(url, file).then(function (d) { N.data = d; render(); toast("ok", "Đã tải ảnh " + emoVi(n.emo)); })
              .catch(function (e) { up.disabled = false; toast("error", "Tải ảnh thất bại", e.message); });
          });
        });
        card.appendChild(up);
        if (n.have) {
          var rm = el("button", "btn btn-ghost btn-sm", "Xoá ảnh");
          rm.type = "button";
          rm.addEventListener("click", function () {
            api(url, { method: "DELETE" }).then(function (d) { N.data = d; render(); })
              .catch(function (e) { toast("error", "Xoá thất bại", e.message); });
          });
          card.appendChild(rm);
        }
        pics.appendChild(card);
      });
      row.appendChild(pics);
      box.appendChild(row);
    });
  }

  function renderStickers(items) {
    var box = $("nc-stickers");
    box.innerHTML = "";
    (items || []).forEach(function (k) {
      var c = el("div", "nc-sticker");
      var img = document.createElement("img");
      img.loading = "lazy";
      img.src = "/api/2ch/stickers/" + encodeURIComponent(k.id) + ".png";
      c.appendChild(img);
      c.appendChild(el("div", null, k.name));
      c.appendChild(el("div", "muted", k.builtin ? "Có sẵn" : "Chị thêm"));
      if (!k.builtin) {
        var rm = el("button", "btn btn-ghost btn-sm", "Xoá");
        rm.type = "button";
        rm.addEventListener("click", function () {
          if (!window.confirm("Xoá hình “" + k.name + "” khỏi kho?")) return;
          api("/api/2ch/stickers/" + encodeURIComponent(k.id), { method: "DELETE" }).then(function (d) {
            if (N.data) N.data.options.stickers = d.items;
            renderStickers(d.items); renderScenes();
          }).catch(function (e) { toast("error", "Xoá thất bại", e.message); });
        });
        c.appendChild(rm);
      }
      box.appendChild(c);
    });
  }

  function addSticker() {
    var name = $("nc-k-name").value.trim();
    if (!name) { toast("warn", "Đặt tên cho hình trước"); return; }
    picker("image/*", function (file) {
      var fd = new FormData();
      fd.append("file", file); fd.append("name", name); fd.append("desc", $("nc-k-desc").value.trim());
      api("/api/2ch/stickers", { method: "POST", body: fd }).then(function (d) {
        $("nc-k-name").value = ""; $("nc-k-desc").value = "";
        if (N.data) N.data.options.stickers = d.items;
        renderStickers(d.items); renderScenes();
        toast("ok", "Đã thêm vào kho", "AI viết truyện lần sau sẽ dùng khi đúng nội dung.");
      }).catch(function (e) { toast("error", "Chưa thêm được", e.message); });
    });
  }

  function renderPlaces() {
    var box = $("nc-places"), s = st(), d = N.data || {};
    box.innerHTML = "";
    if (!(s.places || []).length) { box.appendChild(el("p", "muted", "Chưa có địa điểm.")); return; }
    box.appendChild(promptBar("bgs", null, (s.places || []).filter(function (p) { return (d.bgs_have || []).indexOf(p.id) < 0; })
      .map(function (p) { return { url: base() + "/bg/" + encodeURIComponent(p.id) }; }), "nền"));
    (s.places || []).forEach(function (p) {
      var row = el("div", "nc-place");
      row.setAttribute("data-raw", JSON.stringify(p));
      var nm = document.createElement("input");
      nm.type = "text"; nm.value = p.name || ""; nm.setAttribute("data-k", "name");
      row.appendChild(nm);
      var kd = sel(opts().kinds || [], p.kind); kd.setAttribute("data-k", "kind");
      row.appendChild(kd);
      var tm = sel([["ngay", "Ngày"], ["dem", "Đêm"]], p.time); tm.setAttribute("data-k", "time");
      row.appendChild(tm);
      var lk = document.createElement("input");
      lk.type = "text"; lk.className = "look"; lk.value = p.look || ""; lk.setAttribute("data-k", "look");
      lk.placeholder = "Tả bối cảnh bằng tiếng Anh (dùng cho câu lệnh vẽ nền)";
      row.appendChild(lk);
      [nm, kd, tm, lk].forEach(function (f) { f.addEventListener("change", function () { save(true); }); });
      var act = el("div", "row-actions");
      var have = (d.bgs_have || []).indexOf(p.id) >= 0;
      act.appendChild(el("span", "muted", have ? "✓ Có ảnh nền riêng" : "Nền tool tự vẽ (mờ)"));
      var cp = el("button", "btn btn-sm", "Chép câu lệnh nền");
      cp.type = "button";
      cp.addEventListener("click", function () {
        copyText((d.bg_prompts || {})[p.id] || "").then(function () { toast("ok", "Đã chép câu lệnh nền", "Ảnh dọc 9:16."); });
      });
      act.appendChild(cp);
      var up = el("button", "btn btn-sm", have ? "Thay ảnh nền" : "Tải ảnh nền");
      up.type = "button";
      up.addEventListener("click", function () {
        picker("image/*", function (file) {
          upload(base() + "/bg/" + encodeURIComponent(p.id), file).then(function (dd) { N.data = dd; render(); toast("ok", "Đã thêm ảnh nền"); })
            .catch(function (e) { toast("error", "Tải ảnh thất bại", e.message); });
        });
      });
      act.appendChild(up);
      if (have) {
        var rm = el("button", "btn btn-ghost btn-sm", "Bỏ ảnh nền");
        rm.type = "button";
        rm.addEventListener("click", function () {
          api(base() + "/bg/" + encodeURIComponent(p.id), { method: "DELETE" }).then(function (dd) { N.data = dd; render(); });
        });
        act.appendChild(rm);
      }
      row.appendChild(act);
      box.appendChild(row);
    });
  }

  /* ---------------------------- các cảnh ---------------------------- */

  var VTYPES = [["char", "Nhân vật"], ["two", "Hai người"], ["sticker", "Hình trong kho"], ["object", "Đồ vật"]];

  function thumb(i) { return base() + "/preview/" + i + ".png?v=" + Date.now() % 1000000; }

  function sceneOf(row) {
    var s = JSON.parse(row.getAttribute("data-raw") || "{}");
    var q = function (k) { var f = row.querySelector("[data-k=" + k + "]"); return f ? f.value : ""; };
    s.text = q("text"); s.who = q("who"); s.place = q("place"); s.fx = q("fx");
    var t = q("vtype");
    if (t === "two") s.visual = { type: "two", cids: [q("cid"), q("cid2")], emos: [q("emo"), q("emo2")] };
    else if (t === "sticker") s.visual = { type: "sticker", id: q("sticker") };
    else if (t === "object") s.visual = { type: "object", desc_en: q("desc") };
    else s.visual = { type: "char", cid: q("cid"), emo: q("emo") };
    return s;
  }

  function sceneRow(s, i) {
    var o = opts(), w = st();
    var chars = (w.characters || []).map(function (c) { return [c.id, c.name || c.id]; });
    var emos = (o.emos || []).map(function (e) { return [e, emoVi(e)]; });
    var v = s.visual || {};
    var row = el("div", "nc-scene");
    row.setAttribute("data-raw", JSON.stringify(s));
    row.appendChild(el("div", "num", String(i + 1)));
    var img = document.createElement("img");
    img.className = "th"; img.loading = "lazy"; img.src = thumb(i);
    img.title = "Xem lớn";
    img.addEventListener("click", function () { N.big = i; $("nc-big").src = thumb(i); });
    row.appendChild(img);
    var ctl = el("div", "ctl");
    var ta = document.createElement("textarea");
    ta.rows = 2; ta.value = s.text || ""; ta.setAttribute("data-k", "text");
    ctl.appendChild(ta);
    var who = sel([["narr", "Lời kể"]].concat(chars), s.who); who.setAttribute("data-k", "who"); who.title = "Ai nói";
    ctl.appendChild(who);
    var vt = sel(VTYPES, v.type || "char"); vt.setAttribute("data-k", "vtype"); vt.title = "Hình";
    ctl.appendChild(vt);
    var extra = el("span");
    extra.style.display = "contents";
    ctl.appendChild(extra);
    function drawExtra() {
      extra.innerHTML = "";
      var t = vt.value;
      if (t === "char" || t === "two") {
        var c1 = sel(chars, t === "two" ? (v.cids || [])[0] : v.cid); c1.setAttribute("data-k", "cid");
        var e1 = sel(emos, t === "two" ? (v.emos || [])[0] : v.emo); e1.setAttribute("data-k", "emo");
        extra.appendChild(c1); extra.appendChild(e1);
        if (t === "two") {
          var c2 = sel(chars, (v.cids || [])[1] || (chars[1] || [])[0]); c2.setAttribute("data-k", "cid2");
          var e2 = sel(emos, (v.emos || [])[1]); e2.setAttribute("data-k", "emo2");
          extra.appendChild(c2); extra.appendChild(e2);
        }
      } else if (t === "sticker") {
        var ks = sel((o.stickers || []).map(function (k) { return [k.id, k.name]; }), v.id); ks.setAttribute("data-k", "sticker");
        extra.appendChild(ks);
      } else {
        var dsc = document.createElement("input");
        dsc.type = "text"; dsc.className = "wide"; dsc.value = v.desc_en || ""; dsc.setAttribute("data-k", "desc");
        dsc.placeholder = "Tả đồ vật bằng tiếng Anh (vd: a brown paper envelope with the kanji 清)";
        extra.appendChild(dsc);
      }
    }
    drawExtra();
    vt.addEventListener("change", drawExtra);
    var pl = sel((w.places || []).map(function (p) { return [p.id, p.name || p.id]; }), s.place); pl.setAttribute("data-k", "place"); pl.title = "Địa điểm";
    ctl.appendChild(pl);
    var fx = sel(o.fx || [], s.fx || ""); fx.setAttribute("data-k", "fx"); fx.title = "Hiệu ứng";
    ctl.appendChild(fx);
    // ảnh riêng cho cảnh (đồ vật, hoặc bất kỳ hình nào chị muốn)
    var url = base() + "/scene/" + encodeURIComponent(s.id);
    if (v.type === "object") {
      var cp = el("button", "btn btn-sm", "Chép câu lệnh vẽ đồ vật");
      cp.type = "button";
      cp.addEventListener("click", function () {
        var ob = ((N.data && N.data.objects) || []).filter(function (x) { return x.sid === s.id; })[0];
        copyText(ob ? ob.prompt : "").then(function () { toast("ok", "Đã chép câu lệnh vẽ đồ vật"); });
      });
      ctl.appendChild(cp);
    }
    var up = el("button", "btn btn-sm", s.img ? "Thay ảnh riêng" : "Tải ảnh riêng cho cảnh");
    up.type = "button";
    up.addEventListener("click", function () {
      save(true).then(function () {
        picker("image/*", function (file) {
          upload(url, file).then(function (d) { N.data = d; render(); toast("ok", "Đã thêm ảnh cho cảnh " + (i + 1)); })
            .catch(function (e) { toast("error", "Tải ảnh thất bại", e.message); });
        });
      });
    });
    ctl.appendChild(up);
    if (s.img) {
      var rm = el("button", "btn btn-ghost btn-sm", "Bỏ ảnh riêng");
      rm.type = "button";
      rm.addEventListener("click", function () {
        api(url, { method: "DELETE" }).then(function (d) { N.data = d; render(); });
      });
      ctl.appendChild(rm);
    }
    row.appendChild(ctl);
    var side = el("div", "ctl");
    var del = el("button", "btn btn-ghost btn-sm", "✕");
    del.type = "button"; del.title = "Xoá cảnh";
    del.addEventListener("click", function () { row.parentNode.removeChild(row); });
    side.appendChild(del);
    row.appendChild(side);
    return row;
  }

  function renderScenes() {
    var box = $("nc-scenes"), w = st();
    box.innerHTML = "";
    var objs = (N.data && N.data.objects) || [];
    if (objs.length) {
      box.appendChild(promptBar("objects", null, objs.filter(function (o) { return !o.have; })
        .map(function (o) { return { url: base() + "/scene/" + encodeURIComponent(o.sid) }; }), "đồ vật"));
    }
    (w.scenes || []).forEach(function (s, i) { box.appendChild(sceneRow(s, i)); });
    if ((w.scenes || []).length) $("nc-big").src = thumb(Math.min(N.big || 0, w.scenes.length - 1));
  }

  function addScene() {
    if (!N.id) { toast("warn", "Tạo video trước", "Bấm 'AI viết truyện' hoặc '+ Video mới'."); return; }
    var w = st(), box = $("nc-scenes");
    var n = box.querySelectorAll(".nc-scene").length;
    var c0 = (w.characters || [])[0];
    var s = { id: "c" + Date.now().toString(36), text: "", who: "narr",
              visual: { type: "char", cid: c0 ? c0.id : "", emo: "neutral" },
              place: ((w.places || [])[0] || {}).id || "", fx: "" };
    box.appendChild(sceneRow(s, n));
  }

  /* ---------------------------- việc nền ---------------------------- */

  function showStatus(s, ready) {
    var busy = s.state === "writing" || s.state === "rendering";
    $("nc-progress-wrap").hidden = !busy;
    $("nc-progress").style.width = Math.round((s.progress || 0) * 100) + "%";
    $("nc-msg").textContent = busy || s.state === "error" ? (s.message || "") : "";
    $("nc-state").textContent = s.state === "writing" ? "AI đang viết… " + Math.round((s.progress || 0) * 100) + "%" : "";
    $("nc-write").disabled = busy;
    $("nc-render").disabled = busy;
    if (ready && !busy) {
      var url = "/api/project/" + encodeURIComponent(N.id) + "/video?t=" + Date.now();
      $("nc-out").hidden = false;
      if ($("nc-video").getAttribute("data-for") !== N.id + (s.state || "")) {
        $("nc-video").src = url;
        $("nc-video").setAttribute("data-for", N.id + (s.state || ""));
      }
      $("nc-dl").href = url;
    } else if (!ready) {
      $("nc-out").hidden = true;
    }
  }

  function poll() {
    if (N.polling) clearInterval(N.polling);
    N.polling = setInterval(function () {
      if (!N.id) return;
      api("/api/project/" + encodeURIComponent(N.id) + "/status").then(function (s) {
        showStatus(s, s.video_ready);
        if (s.state !== "writing" && s.state !== "rendering") {
          clearInterval(N.polling); N.polling = null;
          if (s.state === "error") toast("error", "Có lỗi", s.message);
          if (s.state === "written") { toast("ok", "AI đã viết xong", "Xem lại các cảnh ở mục 4"); open(N.id).then(function () { loadList(N.id); }); }
          if (s.state === "done") { toast("ok", "Đã dựng xong video"); open(N.id); }
        }
      }).catch(function () {});
    }, 1500);
  }

  function writeAI() {
    save(true, false).then(function (d) {
      if (!d) return;
      if ((st().scenes || []).length && !window.confirm("AI viết lại truyện mới? Các cảnh hiện có sẽ bị thay.")) return;
      return api(base() + "/write", { body: {} }).then(function () {
        showStatus({ state: "writing", progress: 0, message: "bắt đầu" }); poll();
      });
    }).catch(function (e) { toast("error", "Không bắt đầu được", e.message); });
  }

  function renderVideo() {
    save(true).then(function (d) {
      if (!d) return;
      return api(base() + "/render", { body: {} }).then(function () {
        showStatus({ state: "rendering", progress: 0, message: "bắt đầu" }); poll();
      });
    }).catch(function (e) { toast("error", "Không dựng được", e.message); });
  }

  function remove() {
    if (!N.id || !window.confirm("Xoá video 2ch này? (Vào thùng rác, lấy lại được trong 30 ngày.)")) return;
    api("/api/story/" + encodeURIComponent(N.id), { method: "DELETE" }).then(function () {
      N.id = null; N.data = null;
      try { localStorage.removeItem(LS); } catch (e) {}
      ["nc-chars", "nc-places", "nc-scenes"].forEach(function (id) { $(id).innerHTML = ""; });
      $("nc-out").hidden = true; $("nc-big").removeAttribute("src");
      loadList(); toast("ok", "Đã xoá");
    }).catch(function (e) { toast("error", "Xoá thất bại", e.message); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!$("screen-nichan")) return;
    $("nc-open").addEventListener("change", function () { open(this.value); });
    $("nc-new").addEventListener("click", function () {
      N.id = null; N.data = null;
      ["nc-brief", "nc-t1", "nc-t2", "nc-narr"].forEach(function (id) { $(id).value = ""; });
      ["nc-chars", "nc-places", "nc-scenes"].forEach(function (id) { $(id).innerHTML = ""; });
      $("nc-out").hidden = true; $("nc-big").removeAttribute("src"); $("nc-open").value = "";
      $("nc-brief").focus();
    });
    $("nc-del").addEventListener("click", remove);
    $("nc-save").addEventListener("click", function () { save(false); });
    $("nc-save2").addEventListener("click", function () { save(false); });
    $("nc-write").addEventListener("click", writeAI);
    $("nc-render").addEventListener("click", renderVideo);
    $("nc-add").addEventListener("click", addScene);
    $("nc-k-add").addEventListener("click", addSticker);
    $("nc-art").addEventListener("change", function () {
      if (!N.id) return;
      save(true).then(function () { toast("ok", "Đã đổi phong cách", "Câu lệnh vẽ nhân vật và đồ vật đã đổi theo phong cách mới."); });
    });
    fillSelect("nc-art", [["flat", "Minh hoạ phẳng dễ thương (giống 5 hình có sẵn)"], ["chibi", "Chibi anime (như video mẫu 昭和)"]], "flat");
    // lựa chọn có sẵn cả khi chưa mở video nào
    fillSelect("nc-genre", [["kando", "Cảm động 感動"], ["showa", "Chuyện thời Showa 昭和"], ["sukatto", "Trả đũa đã đời スカッと"],
      ["giji", "Nhà chồng 義実家"], ["shokuba", "Công sở 職場"], ["kinjo", "Hàng xóm ご近所"], ["gakko", "Học đường 学校"],
      ["koi", "Tình cảm 恋愛"], ["warai", "Chuyện cười 笑える話"], ["kowai", "Chuyện rợn người 怖い話"]], "kando");
    fillSelect("nc-voicemode", [["cast", "Mỗi nhân vật một giọng + giọng người kể"], ["one", "Một người kể đọc tất cả"]], "cast");
    api("/api/2ch/stickers").then(function (d) { if (!N.data) renderStickers(d.items); }).catch(function () {});
    var last = null;
    try { last = localStorage.getItem(LS); } catch (e) {}
    loadList(last).then(function () {
      var ids = Array.prototype.map.call($("nc-open").options, function (o) { return o.value; });
      if (last && ids.indexOf(last) >= 0) open(last);
    });
  });
})();
