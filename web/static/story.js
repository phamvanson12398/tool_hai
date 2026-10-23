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


  var KIT_LABEL = { species: "Loài", age: "Tuổi", sex: "Giới", skin: "Da", hair: "Tóc",
    hair_color: "Màu tóc", hat: "Mũ nón", glasses: "Kính", facial: "Râu", top: "Áo",
    top_color: "Màu áo", bottom_color: "Màu quần/váy", fur: "Màu lông", extra: "Thêm" };
  var OPT_VI = {
    human: "người", dog: "chó", cat: "mèo", child: "trẻ con", young: "thanh niên", adult: "trung niên",
    old: "già", male: "nam", female: "nữ", light: "trắng", fair: "sáng", tan: "rám nắng", dark: "ngăm",
    short: "ngắn", bangs: "mái bằng", messy: "rối", side_part: "rẽ ngôi", bun: "búi", long: "dài",
    bob: "ngang vai", bald: "hói", balding: "hói đỉnh", wavy: "bồng xoăn", none: "không",
    non_la: "nón lá", khan_van: "khăn vấn", khan_dau: "khăn quấn", hat: "mũ phớt", round: "kính tròn",
    square: "kính vuông", mustache: "ria", beard: "râu quai nón", stubble: "râu lún phún",
    goatee: "chòm râu dê", ao_nau: "áo nâu", ao_ba_ba: "áo bà ba", ao_cach: "áo cánh + váy",
    dress: "áo + váy", jacket: "áo khoác", shirt: "sơ mi", sweater: "áo len", robe: "áo thụng",
    ao_dai: "áo dài", brown: "nâu", darkbrown: "nâu đậm", indigo: "chàm", navy: "xanh than",
    blue: "xanh dương", lightblue: "xanh nhạt", white: "trắng", cream: "kem", beige: "be",
    gray: "xám", darkgray: "xám đậm", black: "đen", red: "đỏ", pink: "hồng", green: "xanh lá",
    olive: "ô liu", yellow: "vàng", purple: "tím", orange: "cam", salt: "muối tiêu", spotted: "đốm"
  };
  var HUMAN_KEYS = ["age", "sex", "skin", "hair", "hair_color", "hat", "glasses", "facial", "top",
                    "top_color", "bottom_color", "extra"];
  var PART_KIND_VI = { head: "Đồ đội / đeo trên đầu", body: "Hoa văn, đồ khoác trên áo",
                       animal: "Con vật", scene: "Bối cảnh" };

  function optName(o) {
    var pn = (st.data && st.data.part_names) || {};
    return pn[o] ? "★ " + pn[o] : (OPT_VI[o] || o);
  }

  function isTool() { return $("st-visual").value !== "images"; }

  function stamp() { return st.stamp || (st.stamp = Date.now()); }

  function kitSelect(key, opts, val) {
    var sel = document.createElement("select");
    sel.setAttribute("data-k", key);
    sel.title = KIT_LABEL[key] || key;
    opts.forEach(function (o) { sel.appendChild(new Option((KIT_LABEL[key] || key) + ": " + optName(o), o)); });
    sel.value = val;
    return sel;
  }

  function loadVoices() {
    return api("/api/library").then(function (d) {
      var sel = $("st-voice");
      sel.innerHTML = "";
      sel.appendChild(new Option("— Dùng mô tả giọng bên cạnh —", ""));
      st.voices = [];
      (d.voices || []).forEach(function (v) {
        if (v && v.name) sel.appendChild(new Option(v.name, v.name));
        if (v && v.name) st.voices = (st.voices || []).concat([v.name]);
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
      visual: $("st-visual").value,
      bg_mode: $("st-bgmode").value,
      dialogue: $("st-dialogue").value,
      subtitles: $("st-subs").value === "1",
      source_text: $("st-source").value,
      narrator: { voice: $("st-voice").value, instruct: $("st-instruct").value.trim() }
    };
    // nhân vật / địa điểm đã sửa
    var bible = { characters: [], places: [] };
    document.querySelectorAll("#st-bible [data-kind]").forEach(function (row) {
      var item = {
        id: row.getAttribute("data-id"),
        name: row.querySelector("input[type=text]").value,
        look: row.querySelector("textarea").value
      };
      var kit = {};
      row.querySelectorAll("select[data-k]").forEach(function (s) { kit[s.getAttribute("data-k")] = s.value; });
      var pt = row.querySelector("input[type=checkbox]");
      if (pt) kit.patched = pt.checked;
      if (row.getAttribute("data-kind") === "characters") {
        if (Object.keys(kit).length) item.kit = Object.assign({}, row._kit || {}, kit);
        var vs = row.querySelector("select.st-cvoice"), vi = row.querySelector("input.st-cinstruct");
        if (vs || vi) item.voice = { voice: vs ? vs.value : "", instruct: vi ? vi.value.trim() : "" };
      } else {
        if (kit.kind) item.kind = kit.kind;
        if (kit.time) item.time = kit.time;
      }
      bible[row.getAttribute("data-kind")].push(item);
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
            out.camera = box.querySelector("select.st-cam").value;
            var acts = {}, any = false;
            box.querySelectorAll("select[data-act]").forEach(function (s) {
              acts[s.getAttribute("data-act")] = s.value; any = true;
            });
            if (any) out.acts = acts;
            var tk = box.querySelector("select.st-talk");
            if (tk) out.talk = tk.value;
            var lines = [];
            box.querySelectorAll(".st-line").forEach(function (lr) {
              var t = lr.querySelector("input").value.trim();
              if (t) lines.push({ who: lr.querySelector("select").value, text: t });
            });
            if (lines.length) out.lines = lines; else delete out.lines;
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

  function showStyleRef(d) {
    var has = !!(d && d.style_ref);
    var img = $("st-ref-img");
    $("st-ref-wrap").hidden = !has;
    if (has) {
      img.src = "/api/story/" + encodeURIComponent(st.id) + "/style_ref?v=" + Date.now();
      $("st-ref-dl").href = "/api/story/" + encodeURIComponent(st.id) + "/style_ref?dl=1";
    }
  }

  function render(d) {
    st.data = d;
    var s = d.story || {};
    $("st-title").value = s.title || "";
    $("st-author").value = s.author || "";
    $("st-minutes").value = s.minutes || 25;
    $("st-format").value = d.format || "16:9";
    var sty = $("st-style");
    sty.innerHTML = "";
    (d.styles || []).forEach(function (kv) { sty.appendChild(new Option(kv[1], kv[0])); });
    sty.value = s.style || "doodle";
    $("st-visual").value = s.visual || "tool";
    $("st-bgmode").value = s.bg_mode || "draw";
    applyVisual();
    showStyleRef(d);
    $("st-subs").value = s.subtitles ? "1" : "0";
    $("st-source").value = s.source_text || "";
    $("st-dialogue").innerHTML = "";
    (d.dialogues || [["none", "Không"], ["some", "Thỉnh thoảng"], ["many", "Nhiều"]]).forEach(function (kv) {
      $("st-dialogue").appendChild(new Option(kv[1], kv[0]));
    });
    $("st-dialogue").value = s.dialogue || "some";
    var nar = s.narrator || {};
    $("st-voice").value = nar.voice || "";
    $("st-instruct").value = nar.instruct || "";
    renderBible(s);
    renderParts(d);
    renderScenes(d);
    var n = d.scene_count || 0;
    st.stamp = Date.now();
    $("st-img-count").textContent = (n && isTool())
      ? ("Tool tự vẽ " + n + " cảnh. Tranh tải lên (nếu có) sẽ thay cảnh tool vẽ: " +
         (n - (d.missing || []).length) + " tranh.")
      : n
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
    var d = st.data || {};
    var opt = d.kit_options || {};
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
      look.className = "st-look";
      var left = el("div", "st-bible-left");
      left.appendChild(name);
      var right = el("div", "");
      if (isTool() && st.id) {
        var img = document.createElement("img");
        img.className = r[0] === "characters" ? "st-char-img" : "st-place-img";
        img.loading = "lazy";
        img.src = "/api/story/" + encodeURIComponent(st.id) + "/" +
          (r[0] === "characters" ? "char/" : "place/") + encodeURIComponent(r[1].id) + ".png?v=" + stamp();
        var is3d = r[0] === "places" && $("st-bgmode").value === "ai3d";
        var key3d = r[1].id + "_" + (r[1].time || "ngay");
        var has3d = (d.bg3d || []).indexOf(key3d) >= 0 || (d.bg3d || []).indexOf(r[1].id + "_ngay") >= 0;
        if (is3d && has3d) {
          var k = (d.bg3d || []).indexOf(key3d) >= 0 ? key3d : r[1].id + "_ngay";
          img.src = "/api/story/" + encodeURIComponent(st.id) + "/bg3d/" + encodeURIComponent(k) + ".png?w=1&v=" + stamp();
        }
        left.appendChild(img);
        if (is3d) {
          var b3 = el("button", "btn btn-sm", has3d ? "Vẽ lại 3D" : "Vẽ 3D");
          b3.type = "button";
          b3.title = has3d ? "AI vẽ lại bối cảnh này (bố cục khác)" : "AI vẽ bối cảnh 3D cho địa điểm này";
          b3.addEventListener("click", function () { drawBg3d([r[1].id], has3d); });
          left.appendChild(b3);
        }
        var kits = el("div", "st-kit");
        if (r[0] === "characters") {
          var kit = r[1].kit || {};
          row._kit = kit;
          kits.appendChild(kitSelect("species", opt.species || ["human"], kit.species || "human"));
          var sp = kit.species || "human";
          var keys = (sp === "dog" || sp === "cat") ? ["fur"] : (sp === "human" ? HUMAN_KEYS : []);
          keys.forEach(function (k) { kits.appendChild(kitSelect(k, opt[k] || [], kit[k] || (opt[k] || [""])[0])); });
          if (!kit.species || kit.species === "human") {
            var lab = el("label", "st-patch");
            var cb = document.createElement("input");
            cb.type = "checkbox";
            cb.checked = !!kit.patched;
            lab.appendChild(cb);
            lab.appendChild(document.createTextNode(" áo vá"));
            kits.appendChild(lab);
          }
        } else {
          var ks = document.createElement("select");
          ks.setAttribute("data-k", "kind");
          (d.kinds || []).forEach(function (kv) { ks.appendChild(new Option(kv[1], kv[0])); });
          ks.value = r[1].kind || "nha_ngoi";
          var ts = document.createElement("select");
          ts.setAttribute("data-k", "time");
          ts.appendChild(new Option("Ban ngày", "ngay"));
          ts.appendChild(new Option("Ban đêm", "dem"));
          ts.value = r[1].time || "ngay";
          kits.appendChild(ks);
          kits.appendChild(ts);
        }
        // đổi lựa chọn -> lưu rồi vẽ lại ảnh xem trước
        kits.addEventListener("change", function () { save(true); });
        right.appendChild(kits);
        look.rows = 1;
        look.title = "Mô tả tiếng Anh (dùng khi xuất câu lệnh vẽ)";
      }
      if (r[0] === "characters" && (!(r[1].kit || {}).species || r[1].kit.species === "human")) {
        // giọng riêng của nhân vật cho các câu thoại
        var vrow = el("div", "st-kit");
        var vsel = document.createElement("select");
        vsel.className = "st-cvoice";
        vsel.appendChild(new Option("Giọng: tạo theo mô tả →", ""));
        (st.voices || []).forEach(function (n) { vsel.appendChild(new Option("Giọng: " + n, n)); });
        vsel.value = (r[1].voice || {}).voice || "";
        var vin = document.createElement("input");
        vin.type = "text";
        vin.className = "st-cinstruct";
        vin.placeholder = "male, elderly, low pitch";
        vin.title = "Mô tả giọng (tiếng Anh, theo OmniVoice): male/female, child/teenager/young adult/middle-aged/elderly, low/moderate/high pitch";
        vin.value = (r[1].voice || {}).instruct || "";
        vrow.appendChild(vsel);
        vrow.appendChild(vin);
        right.appendChild(vrow);
      }
      right.appendChild(look);
      row.appendChild(left);
      row.appendChild(right);
      box.appendChild(row);
    });
  }

  function renderParts(d) {
    var box = $("st-parts-list");
    if (!box) return;
    box.innerHTML = "";
    var parts = d.parts || [];
    if (!parts.length) {
      box.appendChild(el("p", "hint", "Chưa có bộ phận nào vẽ thêm."));
      return;
    }
    parts.forEach(function (p) {
      var card = el("div", "st-part");
      var img = document.createElement("img");
      img.loading = "lazy";
      img.src = "/api/doodle/part/" + encodeURIComponent(p.id) + ".png?v=" + stamp();
      card.appendChild(img);
      card.appendChild(el("div", "st-part-name", p.name));
      card.appendChild(el("div", "muted", PART_KIND_VI[p.kind] || p.kind));
      var row = el("div", "row-actions");
      var re = el("button", "btn btn-sm", "Vẽ lại");
      re.type = "button";
      re.addEventListener("click", function () {
        var desc = window.prompt("Mô tả thêm cho AI (để trống: giữ mô tả cũ):", p.desc || "");
        if (desc === null) return;
        re.disabled = true;
        re.textContent = "AI đang vẽ…";
        api("/api/doodle/parts/" + encodeURIComponent(p.id) + "/redraw", { body: { desc: desc } })
          .then(function () { toast("ok", "Đã vẽ lại", p.name); return open(st.id); })
          .catch(fail("Vẽ lại thất bại"))
          .then(function () { re.disabled = false; re.textContent = "Vẽ lại"; });
      });
      var del = el("button", "btn btn-sm", "Xoá");
      del.type = "button";
      del.addEventListener("click", function () {
        if (!confirm("Xoá “" + p.name + "” khỏi thư viện? Nhân vật đang dùng sẽ quay về kiểu có sẵn.")) return;
        api("/api/doodle/parts/" + encodeURIComponent(p.id), { method: "DELETE" })
          .then(function () { return open(st.id); }).catch(fail("Xoá thất bại"));
      });
      row.appendChild(re);
      row.appendChild(del);
      card.appendChild(row);
      box.appendChild(card);
    });
  }

  function drawBg3d(places, force) {
    if (!st.id) return;
    var d = st.data || {};
    if (!d.bg3d_installed) {
      toast("warn", "Chưa cài phần vẽ 3D", "Chạy cai_3d.bat một lần (tải khoảng 7 GB) rồi mở lại tool.");
      return;
    }
    save(true).then(function () {
      return api("/api/story/" + encodeURIComponent(st.id) + "/bg3d",
                 { body: { places: places || [], force: !!force } });
    }).then(function () { toast("ok", "AI đang vẽ bối cảnh 3D", "Theo dõi tiến độ ở mục 1."); })
      .catch(fail("Không vẽ được bối cảnh 3D"));
  }

  function newPart() {
    var name = $("st-part-name").value.trim();
    if (!name) { toast("warn", "Nhập tên thứ cần vẽ", "Vd: mũ miện vua, con trâu, cung điện"); return; }
    var btn = $("st-part-make");
    btn.disabled = true;
    btn.textContent = "AI đang vẽ… (30–90 giây)";
    api("/api/doodle/parts", { body: { kind: $("st-part-kind").value, name: name,
                                       desc: $("st-part-desc").value.trim() } })
      .then(function (r) {
        toast("ok", "Đã vẽ thêm “" + r.part.name + "”", "Chọn nó trong các ô ngoại hình / bối cảnh ở trên.");
        $("st-part-name").value = "";
        $("st-part-desc").value = "";
        return st.id ? open(st.id) : null;
      })
      .catch(fail("AI chưa vẽ được"))
      .then(function () { btn.disabled = false; btn.textContent = "AI vẽ thêm"; });
  }

  /** Các câu thoại nhân vật của cảnh (đọc bằng giọng nhân vật sau lời kể). */
  function linesEditor(sc, s) {
    var wrap = el("div", "st-lines");
    var humans = (s.characters || []).filter(function (c) {
      return !(c.kit && c.kit.species && c.kit.species !== "human");
    });
    function addRow(ln) {
      var row = el("div", "st-line");
      var who = document.createElement("select");
      humans.forEach(function (c) { who.appendChild(new Option(c.name, c.id)); });
      who.value = ln.who || ((sc.chars || [])[0] || (humans[0] || {}).id || "");
      var txt = document.createElement("input");
      txt.type = "text";
      txt.placeholder = "Câu nhân vật nói (đọc bằng giọng nhân vật)";
      txt.value = ln.text || "";
      var rm = el("button", "btn btn-sm", "✕");
      rm.type = "button";
      rm.title = "Bỏ câu thoại";
      rm.addEventListener("click", function () { row.remove(); });
      row.appendChild(who);
      row.appendChild(txt);
      row.appendChild(rm);
      wrap.insertBefore(row, add);
    }
    var add = el("button", "btn btn-sm st-line-add", "+ Câu thoại");
    add.type = "button";
    add.addEventListener("click", function () { addRow({}); });
    wrap.appendChild(add);
    if (!humans.length) add.hidden = true;
    (sc.lines || []).forEach(addRow);
    return wrap;
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
        var tool = isTool();
        if (tool && !have[sc.id]) {
          thumb = document.createElement("img");
          thumb.className = "st-thumb";
          thumb.loading = "lazy";
          thumb.src = "/api/story/" + encodeURIComponent(st.id) + "/preview/" + sc.id + ".png?v=" + stamp();
        } else if (have[sc.id]) {
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
        cam.className = "st-cam";
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
        right.appendChild(linesEditor(sc, s));
        if (tool) {
          prompt.hidden = true;
          var names = {};
          (s.characters || []).forEach(function (c) { names[c.id] = c.name; });
          var actRow = el("div", "st-acts");
          (sc.chars || []).forEach(function (cid) {
            if (!names[cid]) return;
            var a = document.createElement("select");
            a.setAttribute("data-act", cid);
            (d.acts || []).forEach(function (kv) { a.appendChild(new Option(names[cid] + ": " + kv[1], kv[0])); });
            a.value = (sc.acts || {})[cid] || "idle";
            actRow.appendChild(a);
          });
          if ((sc.chars || []).length) {
            var talk = document.createElement("select");
            talk.className = "st-talk";
            talk.appendChild(new Option("Không ai nhép miệng", ""));
            (sc.chars || []).forEach(function (cid) {
              if (names[cid]) talk.appendChild(new Option("Nhép miệng: " + names[cid], cid));
            });
            talk.value = sc.talk || "";
            actRow.appendChild(talk);
          } else {
            actRow.appendChild(el("span", "muted", "Cảnh không có nhân vật (chỉ bối cảnh)"));
          }
          actRow.addEventListener("change", function () { save(true); });
          right.appendChild(actRow);
        }
        right.appendChild(prompt);
        row.appendChild(thumb);
        row.appendChild(right);
        box.appendChild(row);
      });
    });
  }

  function applyVisual() {
    var tool = isTool();
    var scr = $("screen-story");
    if (scr) scr.classList.toggle("st-tool", tool);
    if (scr) scr.classList.toggle("st-3d", tool && $("st-bgmode").value === "ai3d");
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
        var writing = s.state === "writing" || s.state === "drawing", rendering = s.state === "rendering";
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
        if (last === "drawing" && s.state === "drawn") { toast("ok", "Đã vẽ bối cảnh 3D", s.message || ""); open(st.id); }
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
    $("st-part-make").addEventListener("click", newPart);
    $("st-bg3d-all").addEventListener("click", function () { drawBg3d([], false); });
    $("st-bgmode").addEventListener("change", function () {
      applyVisual();
      if (st.id) save(true);
      if (this.value === "ai3d" && st.data && !st.data.bg3d_installed)
        toast("warn", "Cần cài phần vẽ 3D", "Chạy cai_3d.bat một lần (tải khoảng 7 GB). Chưa cài thì tool dùng bối cảnh vẽ tay.");
    });
    $("st-visual").addEventListener("change", function () {
      applyVisual();
      if (st.id) save(true); else if (st.data) render(st.data);
    });
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
    $("st-ref-file").addEventListener("change", function () {
      if (!st.id || !this.files.length) return;
      var fd = new FormData();
      fd.append("file", this.files[0]);
      var input = this;
      api("/api/story/" + encodeURIComponent(st.id) + "/style_ref", { body: fd })
        .then(function (d) {
          showStyleRef(d);
          toast("ok", "Đã lưu ảnh mẫu phong cách", "Tải lại bộ câu lệnh vẽ để có hướng dẫn gửi kèm ảnh.");
          input.value = "";
        }).catch(fail("Tải ảnh mẫu thất bại"));
    });
    $("st-ref-remove").addEventListener("click", function () {
      if (!st.id) return;
      var fd = new FormData();
      fd.append("remove", "1");
      api("/api/story/" + encodeURIComponent(st.id) + "/style_ref", { body: fd })
        .then(showStyleRef).catch(fail("Xoá ảnh mẫu thất bại"));
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
    [["doodle", "Vẽ tay webtoon Hàn (đầu tròn, thân con nhộng)"], ["anim2d", "Hoạt hình 2D"], ["watercolor", "Tranh màu nước"], ["oil", "Tranh sơn dầu"],
     ["book", "Tranh minh hoạ sách"]].forEach(function (o) { sty.appendChild(new Option(o[1], o[0])); });
    var last = null;
    try { last = localStorage.getItem(LS_STORY); } catch (e) {}
    loadVoices().then(function () { return loadList(last); }).then(function () {
      if (last) open(last);
    });
  });
})();
