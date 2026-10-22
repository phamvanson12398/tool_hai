/* ============================================================
   Màn hình Dựng khung xương (Bước C2)
   ============================================================ */

(function() {
  "use strict";

  var JOINT_NAMES = [
    "head", "neck",
    "shoulder_l", "elbow_l", "wrist_l",
    "shoulder_r", "elbow_r", "wrist_r",
    "hip", "hip_l", "knee_l", "ankle_l",
    "hip_r", "knee_r", "ankle_r"
  ];

  var JOINT_LABELS = {
    "head": "đầu", "neck": "cổ",
    "shoulder_l": "vai trái", "elbow_l": "khuỷu trái", "wrist_l": "cổ tay trái",
    "shoulder_r": "vai phải", "elbow_r": "khuỷu phải", "wrist_r": "cổ tay phải",
    "hip": "hông", "hip_l": "hông trái", "knee_l": "gối trái", "ankle_l": "mắt cá trái",
    "hip_r": "hông phải", "knee_r": "gối phải", "ankle_r": "mắt cá phải"
  };

  var state = {
    imagePath: null,
    imageNaturalSize: null,
    displaySize: null,
    joints: {},
    dragJoint: null,
    showLabels: true,
    previewFrames: []
  };

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
    var ttl = el("div", "toast-title", title || "");
    t.appendChild(ttl);
    if (body) t.appendChild(el("div", "toast-body", body));
    wrap.appendChild(t);
    setTimeout(function() {
      t.style.opacity = "0";
      setTimeout(function() { if (t.parentNode) t.parentNode.removeChild(t); }, 320);
    }, 3400);
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
    }).then(function(res) {
      if (res.status === 204) return {ok: true};
      var ct = res.headers.get("content-type") || "";
      var p = ct.indexOf("json") >= 0 ? res.json() : res.text();
      return p.then(function(data) {
        if (!res.ok) {
          var msg = (data && (data.error || data.message)) || "HTTP " + res.status;
          var err = new Error(msg);
          err.status = res.status;
          throw err;
        }
        return data;
      });
    });
  }

  function withBusy(btn, fn) {
    if (!btn || btn.dataset.busy === "1") return;
    btn.dataset.busy = "1";
    btn.disabled = true;
    var sp = btn.querySelector(".spinner");
    if (sp) sp.hidden = false;
    var done = function() {
      btn.dataset.busy = "";
      btn.disabled = false;
      if (sp) sp.hidden = true;
    };
    var r;
    try { r = fn(); } catch(e) { done(); throw e; }
    if (r && typeof r.then === "function") {
      return r.then(function(v) { done(); return v; }, function(e) { done(); throw e; });
    }
    done();
    return r;
  }

  // ---------------------- Upload & Estimate ----------------------

  function loadImage() {
    var input = $("rig-image");
    var file = input.files && input.files[0];
    if (!file) {
      toast("warn", "Chưa chọn ảnh", "Hãy chọn một file ảnh trước.");
      return;
    }

    var fd = new FormData();
    fd.append("file", file);

    withBusy($("btn-rig-load"), function() {
      return api("/api/rig/upload", {method: "POST", body: fd})
        .then(function(data) {
          state.imagePath = data.path;
          state.imageNaturalSize = data.size;
          state.joints = data.joints || {};

          var info = $("rig-image-info");
          info.textContent = file.name + " · " + data.size[0] + "×" + data.size[1];
          if (!data.valid) {
            info.textContent += " ⚠ ảnh không đạt (nửa người hoặc tay khoanh)";
            info.style.color = "var(--warn)";
          } else {
            info.style.color = "";
          }

          var box = $("rig-joint-info");
          box.innerHTML = "";
          var item = el("div", "item");
          item.appendChild(el("div", "item-body",
            "Nguồn khớp: " + (data.source === "mediapipe" ? "mediapipe (tự động)" : "mặc định") +
            " · " + Object.keys(state.joints).length + "/14 khớp"
          ));
          box.appendChild(item);

          // Hiện canvas
          $("rig-canvas-card").hidden = false;
          renderCanvas();
          toast("ok", "Đã load ảnh", "Kéo chấm khớp để điều chỉnh vị trí.");
        })
        .catch(function(e) {
          toast("error", "Load ảnh thất bại", e.message || e);
        });
    });
  }

  // ---------------------- Canvas ----------------------

  function renderCanvas() {
    var canvas = $("rig-canvas");
    var ctx = canvas.getContext("2d");
    if (!state.imagePath) return;

    var img = new Image();
    img.onload = function() {
      var maxW = 800, maxH = 800;
      var scale = Math.min(1, maxW / img.width, maxH / img.height);
      canvas.width = img.width * scale;
      canvas.height = img.height * scale;
      state.displaySize = [canvas.width, canvas.height];
      state.displayScale = scale;

      function redraw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

        // Vẽ xương nối
        ctx.strokeStyle = "rgba(56,189,248,0.6)";
        ctx.lineWidth = 3;
        var bones = [
          ["neck", "head"],
          ["hip", "neck"],
          ["neck", "shoulder_l"], ["shoulder_l", "elbow_l"], ["elbow_l", "wrist_l"],
          ["neck", "shoulder_r"], ["shoulder_r", "elbow_r"], ["elbow_r", "wrist_r"],
          ["hip", "hip_l"], ["hip_l", "knee_l"], ["knee_l", "ankle_l"],
          ["hip", "hip_r"], ["hip_r", "knee_r"], ["knee_r", "ankle_r"]
        ];
        bones.forEach(function(b) {
          var a = state.joints[b[0]], c = state.joints[b[1]];
          if (a && c) {
            ctx.beginPath();
            ctx.moveTo(a[0]*scale, a[1]*scale);
            ctx.lineTo(c[0]*scale, c[1]*scale);
            ctx.stroke();
          }
        });

        // Vẽ khớp
        JOINT_NAMES.forEach(function(jn) {
          var pos = state.joints[jn];
          if (!pos) return;
          var x = pos[0] * scale, y = pos[1] * scale;
          ctx.fillStyle = "#38BDF8";
          ctx.strokeStyle = "#FFF";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(x, y, 6, 0, Math.PI*2);
          ctx.fill();
          ctx.stroke();
        });

        // Nhãn khớp
        if (state.showLabels) {
          ctx.font = "12px Inter, sans-serif";
          ctx.fillStyle = "#0B0E14";
          ctx.strokeStyle = "#F8FAFC";
          ctx.lineWidth = 3;
          JOINT_NAMES.forEach(function(jn) {
            var pos = state.joints[jn];
            if (!pos) return;
            var x = pos[0] * scale, y = pos[1] * scale;
            var txt = JOINT_LABELS[jn] || jn;
            ctx.strokeText(txt, x + 10, y - 4);
            ctx.fillText(txt, x + 10, y - 4);
          });
        }
      }

      redraw();
      state.redraw = redraw;

      // Kéo chấm
      canvas.onmousedown = function(e) {
        var rect = canvas.getBoundingClientRect();
        var mx = e.clientX - rect.left, my = e.clientY - rect.top;
        var found = null;
        JOINT_NAMES.forEach(function(jn) {
          var pos = state.joints[jn];
          if (!pos) return;
          var dx = pos[0]*scale - mx, dy = pos[1]*scale - my;
          if (dx*dx + dy*dy < 144) found = jn;
        });
        if (found) {
          state.dragJoint = found;
          $("rig-status").textContent = "Đang kéo: " + JOINT_LABELS[found];
        }
      };

      canvas.onmousemove = function(e) {
        var rect = canvas.getBoundingClientRect();
        var mx = e.clientX - rect.left, my = e.clientY - rect.top;
        if (state.dragJoint) {
          state.joints[state.dragJoint] = [mx/scale, my/scale];
          redraw();
        } else {
          // hover highlight
          var hover = null;
          JOINT_NAMES.forEach(function(jn) {
            var pos = state.joints[jn];
            if (!pos) return;
            var dx = pos[0]*scale - mx, dy = pos[1]*scale - my;
            if (dx*dx + dy*dy < 144) hover = jn;
          });
          canvas.style.cursor = hover ? "pointer" : "crosshair";
          if (hover) $("rig-status").textContent = JOINT_LABELS[hover];
          else $("rig-status").textContent = "Sẵn sàng";
        }
      };

      canvas.onmouseup = function() {
        if (state.dragJoint) {
          $("rig-status").textContent = "Đã sửa " + JOINT_LABELS[state.dragJoint];
          state.dragJoint = null;
        }
      };
    };

    img.src = "/api/library/image/" + encodeURIComponent(state.imagePath);
  }

  // ---------------------- Lưu rig.json ----------------------

  function saveRig() {
    if (!state.imagePath || !Object.keys(state.joints).length) {
      toast("warn", "Chưa có dữ liệu", "Load ảnh trước khi lưu.");
      return;
    }

    withBusy($("btn-rig-save"), function() {
      return api("/api/rig/save", {
        method: "POST",
        body: {
          name: "photo",
          joints: state.joints,
          source: "manual"
        }
      }).then(function(data) {
        toast("ok", "Đã lưu rig.json", data.path || "");
        $("rig-preview-hint").textContent = "rig.json đã lưu tại " + (data.path || "tmp/rig");
      }).catch(function(e) {
        toast("error", "Lưu thất bại", e.message || e);
      });
    });
  }

  // ---------------------- Xem thử vẫy tay / đi bộ ----------------------

  function previewGesture(mode) {
    if (!state.imagePath) {
      toast("warn", "Chưa có ảnh", "Load ảnh trước khi xem thử.");
      return;
    }

    var btn = mode === "wave" ? $("btn-rig-preview-wave") : $("btn-rig-preview-walk");
    withBusy(btn, function() {
      return api("/api/rig/preview?path=" + encodeURIComponent(state.imagePath) + "&mode=" + mode)
        .then(function(data) {
          state.previewFrames = data.frames || [];
          if (state.previewFrames.length) {
            playPreview();
            toast("ok", "Xem thử " + (mode === "wave" ? "vẫy tay" : "đi bộ"), "Hiển thị " + state.previewFrames.length + " khung");
          } else {
            toast("warn", "Không có khung", "Server không trả về khung xem thử.");
          }
        })
        .catch(function(e) {
          toast("error", "Xem thử thất bại", e.message || e);
        });
    });
  }

  function playPreview() {
    var stage = $("rig-preview-stage");
    stage.innerHTML = "";

    // Tạo khung lớn (preview chính)
    var mainWrap = el("div");
    mainWrap.style.cssText = "margin-bottom:12px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#000";
    var mainImg = document.createElement("img");
    mainImg.style.cssText = "width:100%;height:auto;display:block";
    mainImg.src = state.previewFrames[0];
    mainWrap.appendChild(mainImg);
    stage.appendChild(mainWrap);

    // Tạo lưới 6 ảnh nhỏ
    var grid = el("div");
    grid.style.cssText = "display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px";
    state.previewFrames.forEach(function(src, i) {
      var thumb = document.createElement("img");
      thumb.src = src;
      thumb.style.cssText = "width:100%;height:auto;border:2px solid var(--line);border-radius:6px;cursor:pointer;transition:border-color .2s";
      thumb.addEventListener("mouseenter", function() { thumb.style.borderColor = "#38BDF8"; });
      thumb.addEventListener("mouseleave", function() { thumb.style.borderColor = "var(--line)"; });
      thumb.addEventListener("click", function() {
        mainImg.src = src;
        Array.from(grid.children).forEach(function(t) { t.style.borderColor = "var(--line)"; });
        thumb.style.borderColor = "#F97316";
      });
      grid.appendChild(thumb);
    });
    stage.appendChild(grid);

    // Nút phát
    var playBtn = el("button", "btn btn-primary", "▶ Phát animation");
    playBtn.style.cssText = "width:100%";
    var playing = false;
    var idx = 0;
    var timer = null;

    playBtn.addEventListener("click", function() {
      if (playing) {
        playing = false;
        clearInterval(timer);
        playBtn.textContent = "▶ Phát animation";
      } else {
        playing = true;
        playBtn.textContent = "⏸ Dừng";
        idx = 0;
        timer = setInterval(function() {
          mainImg.src = state.previewFrames[idx % state.previewFrames.length];
          idx++;
        }, 166);
      }
    });
    stage.appendChild(playBtn);
  }

  // ---------------------- Wiring ----------------------

  function wireRigScreen() {
    $("btn-rig-back").addEventListener("click", function() {
      // Quay về màn Tập mới
      var evt = new CustomEvent("switchTab", {detail: {name: "new"}});
      document.dispatchEvent(evt);
    });

    $("rig-image").addEventListener("change", function() {
      var f = this.files && this.files[0];
      if (f) {
        $("rig-image-info").textContent = f.name + " · " + (f.size / 1024).toFixed(1) + " KB";
      }
    });

    $("btn-rig-load").addEventListener("click", loadImage);
    $("btn-rig-reset").addEventListener("click", function() {
      state.imagePath = null;
      state.joints = {};
      $("rig-canvas-card").hidden = true;
      $("rig-image-info").textContent = "Chưa chọn ảnh";
      $("rig-joint-info").innerHTML = "";
      $("rig-image").value = "";
      toast("ok", "Đã bỏ qua", "Chọn ảnh mới để bắt đầu lại.");
    });

    $("rig-show-labels").addEventListener("change", function() {
      state.showLabels = this.checked;
      if (state.redraw) state.redraw();
    });

    $("btn-rig-save").addEventListener("click", saveRig);
    $("btn-rig-preview-wave").addEventListener("click", function() { previewGesture("wave"); });
    $("btn-rig-preview-walk").addEventListener("click", function() { previewGesture("walk"); });
  }

  // Lắng nghe sự kiện switch tab từ app.js
  document.addEventListener("switchTab", function(e) {
    if (e.detail && e.detail.name === "rig") {
      // Reset state khi vào màn dựng xương
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireRigScreen);
  } else {
    wireRigScreen();
  }

})();
