/* Tab "Kiểu nhân vật": xem trước từng kiểu (ảnh động hành động + dàn nhân vật),
   tạo kiểu mới từ ảnh nhân vật mẫu, đổi tên / xoá kiểu tự tạo. */
(function () {
  "use strict";

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
  function changed() { document.dispatchEvent(new CustomEvent("stylesChanged")); }

  var KIND = { preset: "Kiểu vẽ sẵn", builtin: "Có sẵn", saved: "Chị tự tạo" };
  var loaded = false;

  function card(it) {
    var c = el("div", "cs-card");
    c.setAttribute("data-style", it.id);
    var h = el("h3", "", it.name);
    h.appendChild(el("span", "cs-tag", KIND[it.kind] || ""));
    c.appendChild(h);
    if (it.note) c.appendChild(el("p", "cs-note", it.note));
    var v = Date.now();
    var anim = el("img", "cs-anim");
    anim.loading = "lazy";
    anim.alt = "Nhân vật diễn các hành động";
    anim.src = "/api/styles/" + encodeURIComponent(it.id) + "/anim.webp?v=" + v;
    c.appendChild(anim);
    var row2 = el("div", "cs-row");
    if (it.sample) {
      var smp = el("img", "cs-sample");
      smp.loading = "lazy";
      smp.alt = "Ảnh mẫu gốc";
      smp.title = "Ảnh mẫu gốc";
      smp.src = "/api/styles/" + encodeURIComponent(it.id) + "/sample.png?v=" + v;
      row2.appendChild(smp);
    }
    var cast = el("img", "cs-cast");
    cast.loading = "lazy";
    cast.alt = "Dàn nhân vật cùng nét vẽ";
    cast.src = "/api/styles/" + encodeURIComponent(it.id) + "/cast.png?v=" + v;
    row2.appendChild(cast);
    c.appendChild(row2);
    if (it.kind === "saved") {
      var row = el("div", "cs-actions");
      var rn = el("button", "btn btn-sm", "Đổi tên");
      rn.type = "button";
      rn.addEventListener("click", function () {
        var name = window.prompt("Tên mới cho kiểu nhân vật:", it.name);
        if (!name || !name.trim()) return;
        api("/api/styles/" + encodeURIComponent(it.id) + "/rename", { body: { name: name.trim() } })
          .then(function () { load(); changed(); })
          .catch(function (e) { toast("error", "Không đổi tên được", e.message); });
      });
      var del = el("button", "btn btn-sm", "🗑 Xoá");
      del.type = "button";
      del.addEventListener("click", function () {
        if (!window.confirm("Xoá kiểu “" + it.name + "”? (Truyện đang dùng kiểu này vẫn giữ nét vẽ đã chọn.)")) return;
        api("/api/styles/" + encodeURIComponent(it.id), { method: "DELETE" })
          .then(function () { load(); changed(); toast("ok", "Đã xoá kiểu nhân vật"); })
          .catch(function (e) { toast("error", "Không xoá được", e.message); });
      });
      row.appendChild(rn);
      row.appendChild(del);
      c.appendChild(row);
    }
    return c;
  }

  function load(focus) {
    return api("/api/styles").then(function (d) {
      loaded = true;
      var box = $("cs-list");
      box.innerHTML = "";
      var items = d.items || [];
      // kiểu tự tạo / có sẵn lên đầu, kiểu vẽ sẵn sau
      items.sort(function (a, b) { return (a.kind === "preset") - (b.kind === "preset"); });
      items.forEach(function (it) { box.appendChild(card(it)); });
      if (focus) {
        var c = box.querySelector('[data-style="' + focus + '"]');
        if (c) c.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }).catch(function (e) { toast("error", "Không tải được danh sách kiểu", e.message); });
  }

  function create() {
    var f = $("cs-file").files && $("cs-file").files[0];
    if (!f) { toast("warn", "Chọn ảnh nhân vật mẫu trước"); return; }
    var fd = new FormData();
    fd.append("file", f);
    fd.append("name", $("cs-name").value.trim());
    var btn = $("cs-create"), st = $("cs-status");
    btn.disabled = true;
    st.hidden = false;
    st.textContent = "Claude đang xem ảnh và thiết kế nhân vật… khoảng 20–60 giây.";
    api("/api/styles", { body: fd })
      .then(function (d) {
        st.textContent = "Đã tạo kiểu nhân vật: " + (d.note || "") + " — đang vẽ xem trước các hành động…";
        $("cs-file").value = "";
        $("cs-name").value = "";
        changed();
        return load(d.id);
      })
      .then(function () { st.hidden = true; toast("ok", "Đã tạo kiểu nhân vật mới"); })
      .catch(function (e) { st.textContent = e.message; toast("error", "Không tạo được kiểu", e.message); })
      .then(function () { btn.disabled = false; });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!$("screen-charstyles")) return;
    $("cs-create").addEventListener("click", create);
    $("cs-reload").addEventListener("click", function () { load(); });
    // nạp khi mở tab lần đầu (ảnh xem trước vẽ lần đầu mất vài giây mỗi kiểu)
    $("tabs").addEventListener("click", function (e) {
      var b = e.target.closest(".tab");
      if (b && b.dataset.screen === "charstyles" && !loaded) load();
    });
    document.addEventListener("switchTab", function (e) {
      if (e.detail && e.detail.name === "charstyles" && !loaded) load();
    });
    if ($("screen-charstyles").classList.contains("is-active")) load();
  });
})();
