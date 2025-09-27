// content.js
(() => {
  // ===== 可按需修改的默认参数 =====
  const API_BASE = "http://localhost:8000";
  const API_PATH = "/v1/ocr";
  const LANG = "ch_en";
  const RETURN_BOXES = true;
  const IMAGE_TYPE = "image/jpeg";  // 仅控制上传 MIME；后台截图固定走 JPEG
  const JPEG_QUALITY = 0.92;        // 传给后台截图与上传
  const HOTKEY = { alt: true, key: "0" };

  // ===== 小工具：提示与结果窗 =====
  const toast = (m, ok = true) => {
    const d = document.createElement("div");
    d.textContent = m;
    Object.assign(d.style, {
      position: "fixed",
      right: "16px",
      top: "16px",
      zIndex: 2147483647,
      background: ok ? "rgba(16,185,129,.95)" : "rgba(239,68,68,.95)",
      color: "#fff",
      padding: "8px 12px",
      borderRadius: "8px",
      fontSize: "12px",
      boxShadow: "0 6px 18px rgba(0,0,0,.25)"
    });
    document.body.appendChild(d);
    setTimeout(() => d.remove(), 2200);
  };

  const showResult = (text) => {
    const w = document.createElement("div");
    Object.assign(w.style, {
      position: "fixed",
      right: "16px",
      bottom: "16px",
      zIndex: 2147483647,
      width: "min(520px,60vw)",
      height: "min(280px,40vh)",
      background: "#111",
      color: "#fff",
      borderRadius: "10px",
      boxShadow: "0 10px 30px rgba(0,0,0,.35)",
      overflow: "hidden",
      display: "grid",
      gridTemplateRows: "36px 1fr"
    });
    const b = document.createElement("div");
    b.textContent = "OCR 结果（点击此栏关闭 / ESC）";
    Object.assign(b.style, { padding: "8px 12px", background: "#222", fontSize: "12px" });
    const ta = document.createElement("textarea");
    ta.readOnly = true;
    ta.value = text;
    Object.assign(ta.style, {
      width: "100%",
      height: "100%",
      padding: "10px",
      border: "0",
      background: "transparent",
      color: "#fff",
      fontFamily: "ui-monospace,Menlo,Consolas,monospace",
      fontSize: "12px"
    });
    w.append(b, ta);
    document.body.appendChild(w);
    const close = () => w.remove();
    b.onclick = close;
    function onEsc(e) { if (e.key === "Escape") { close(); window.removeEventListener("keydown", onEsc); } }
    window.addEventListener("keydown", onEsc);
  };

  // ===== 关键：为“fixed 选框”做 transform/zoom 矫正 =====
  function applyViewportCorrection(overlay) {
    overlay.style.position = "fixed";
    overlay.style.left = "0";
    overlay.style.top = "0";
    overlay.style.width = "100vw";
    overlay.style.height = "100vh";
    overlay.style.transform = "none";
    overlay.style.transformOrigin = "0 0";
    overlay.style.visibility = "hidden";
    document.documentElement.appendChild(overlay);

    // 探针
    const probe = document.createElement("div");
    Object.assign(probe.style, { position: "fixed", left: "0", top: "0", width: "1px", height: "1px", pointerEvents: "none" });
    overlay.appendChild(probe);

    const r = overlay.getBoundingClientRect();
    const dx = r.left;
    const dy = r.top;
    const sx = window.innerWidth / r.width;
    const sy = window.innerHeight / r.height;

    overlay.style.transform = `translate(${-dx}px, ${-dy}px) scale(${sx}, ${sy})`;
    overlay.style.visibility = "visible";
    return { sx, sy, dx, dy };
  }

  // ===== 后台截图并按选框裁剪（高成功率） =====
  async function captureAndCrop(rectAbs, quality = JPEG_QUALITY) {
    // rectAbs: 以 viewport client 坐标为基准的矩形 {x,y,w,h}
    const resp = await chrome.runtime.sendMessage({ type: "captureVisibleTab", quality });
    if (!resp?.ok) throw new Error(resp?.error || "captureVisibleTab failed");

    const img = new Image();
    await new Promise((res, rej) => {
      img.onload = res;
      img.onerror = rej;
      img.src = resp.dataUrl;
    });

    // 可见截图像素尺寸 与 viewport client 尺寸 的映射
    // 在高 DPI/缩放场景下，img.width 通常 ≈ window.innerWidth * devicePixelRatio
    const ratioX = img.width  / window.innerWidth;
    const ratioY = img.height / window.innerHeight;

    const sx = Math.max(0, Math.round(rectAbs.x * ratioX));
    const sy = Math.max(0, Math.round(rectAbs.y * ratioY));
    const sw = Math.max(1, Math.round(rectAbs.w * ratioX));
    const sh = Math.max(1, Math.round(rectAbs.h * ratioY));

    // 先把整张截图画到画布（可选，用于 debug 或后续标注）
    const stage = document.createElement("canvas");
    stage.width = img.width;
    stage.height = img.height;
    stage.getContext("2d").drawImage(img, 0, 0);

    // 再裁剪指定区域
    const cut = document.createElement("canvas");
    cut.width = sw;
    cut.height = sh;
    cut.getContext("2d").drawImage(stage, sx, sy, sw, sh, 0, 0, sw, sh);

    return cut;
  }

  // ===== 上传 OCR =====
  async function uploadAndOcr(canvas) {
    toast("正在上传识别…");
    const blob = await new Promise(r => canvas.toBlob(r, IMAGE_TYPE, JPEG_QUALITY));
    const fd = new FormData();
    fd.append("file", new File([blob], IMAGE_TYPE === "image/png" ? "sel.png" : "sel.jpg", { type: IMAGE_TYPE }));

    // 可调 OCR 参数
    const OCR_PARAMS = {
      lang: LANG,                // "auto" | "ch" | "en" | "ch_en"
      return_boxes: RETURN_BOXES,
      char_type: "en_sensitive",
      box_thresh: 0.45,
      unclip_ratio: 1.9,
      drop_score: 0.30,
      max_text_length: 128,
      preprocess: 1
    };
    const qs = new URLSearchParams(Object.entries(OCR_PARAMS).map(([k, v]) => [k, String(v)])).toString();
    const url = `${API_BASE}${API_PATH}?${qs}`;

    try {
      const t0 = performance.now();
      const res = await fetch(url, { method: "POST", body: fd, cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      const dt = performance.now() - t0;
      showResult(json.text || JSON.stringify(json, null, 2));
      toast(`识别完成（${dt.toFixed(0)} ms）`, true);
    } catch (e) {
      console.error("[OCR] upload failed:", e);
      toast("OCR 调用失败（看控制台/Network）", false);
    }
  }

  // ===== 启动框选：Alt + 0 =====
  window.addEventListener("keydown", async (e) => {
    const hitAlt = HOTKEY.alt ? e.altKey : true;
    const isZero = e.key === "0" || e.code === "Digit0" || e.code === "Numpad0";
    if (hitAlt && isZero) {
      e.preventDefault();
      // 健康检查（可选）
      try { await fetch(`${API_BASE}/healthz`, { cache: "no-store" }); }
      catch { toast("后端不可达，请先启动 FastAPI 或检查端口/CORS", false); return; }

      startBox();
    }
  });

  // ===== 框选 UI 与交互 =====
  async function startBox() {
    // 遮罩
    const overlay = document.createElement("div");
    overlay.setAttribute("ocr-overlay", "1");
    Object.assign(overlay.style, { zIndex: 2147483646, cursor: "crosshair" });

    // 十字线
    const hline = document.createElement("div"), vline = document.createElement("div");
    Object.assign(hline.style, { position: "fixed", left: 0, width: "100vw", height: "1px", background: "rgba(255,255,255,.6)", pointerEvents: "none", display: "none", zIndex: 2147483647 });
    Object.assign(vline.style, { position: "fixed", top: 0, height: "100vh", width: "1px", background: "rgba(255,255,255,.6)", pointerEvents: "none", display: "none", zIndex: 2147483647 });
    overlay.append(hline, vline);

    // 暗化四周
    const dimTop = mkDim(), dimLeft = mkDim(), dimRight = mkDim(), dimBottom = mkDim();
    overlay.append(dimTop, dimLeft, dimRight, dimBottom);
    function mkDim() { const d = document.createElement("div"); Object.assign(d.style, { position: "fixed", background: "rgba(0,0,0,.38)", pointerEvents: "none", zIndex: 2147483646 }); return d; }
    function placeDims(r) {
      dimTop.style.left = "0px"; dimTop.style.top = "0px";
      dimTop.style.width = "100vw"; dimTop.style.height = r ? `${r.y}px` : "100vh";
      dimLeft.style.left = "0px"; dimLeft.style.top = r ? `${r.y}px` : "0px";
      dimLeft.style.width = r ? `${r.x}px` : "0px"; dimLeft.style.height = r ? `${r.h}px` : "0px";
      dimRight.style.left = r ? `${r.x + r.w}px` : "100vw";
      dimRight.style.top = r ? `${r.y}px` : "0px";
      dimRight.style.width = r ? `calc(100vw - ${r.x + r.w}px)` : "0px";
      dimRight.style.height = r ? `${r.h}px` : "0px";
      dimBottom.style.left = "0px"; dimBottom.style.top = r ? `${r.y + r.h}px` : "0px";
      dimBottom.style.width = "100vw"; dimBottom.style.height = r ? `calc(100vh - ${r.y + r.h}px)` : "0px";
    }

    // 选框
    const box = document.createElement("div");
    Object.assign(box.style, { position: "fixed", outline: "2px solid #4ade80", boxSizing: "border-box", pointerEvents: "none", display: "none", zIndex: 2147483647 });
    overlay.appendChild(box);

    // 标注尺寸
    const tag = document.createElement("div");
    Object.assign(tag.style, { position: "fixed", padding: "2px 6px", fontSize: "12px", background: "rgba(17,24,39,.95)", color: "#fff", borderRadius: "4px", pointerEvents: "none", display: "none", zIndex: 2147483647 });
    overlay.appendChild(tag);

    // 应用矫正
    applyViewportCorrection(overlay);

    // 禁止文本选择
    const prevSel = document.body.style.userSelect; document.body.style.userSelect = "none";
    toast("按下设置左上角 → 拖到右下角；ESC 取消。");

    let start = null, rectAbs = null, dragging = false;

    function cleanup() {
      overlay.remove();
      document.body.style.userSelect = prevSel;
      window.removeEventListener("keydown", onKey);
    }
    function onKey(e) { if (e.key === "Escape") cleanup(); }

    overlay.addEventListener("mousemove", (e) => {
      // 十字线跟随鼠标（使用 client 坐标）
      hline.style.top = e.clientY + "px";
      vline.style.left = e.clientX + "px";
      hline.style.display = vline.style.display = "block";

      if (!dragging || !start) return;
      const cx = Math.max(e.clientX, start.absX);
      const cy = Math.max(e.clientY, start.absY);
      rectAbs = { x: start.absX, y: start.absY, w: cx - start.absX, h: cy - start.absY };

      Object.assign(box.style, { left: rectAbs.x + "px", top: rectAbs.y + "px", width: rectAbs.w + "px", height: rectAbs.h + "px", display: "block" });
      placeDims({ x: rectAbs.x, y: rectAbs.y, w: rectAbs.w, h: rectAbs.h });
      Object.assign(tag.style, { left: (rectAbs.x + rectAbs.w + 8) + "px", top: (rectAbs.y + rectAbs.h + 8) + "px", display: "block" });
      tag.textContent = `${rectAbs.w} × ${rectAbs.h}`;
    });

    overlay.addEventListener("mousedown", (e) => {
      const r = overlay.getBoundingClientRect(); // 未直接使用，仅保留以防后续扩展
      start = { absX: e.clientX, absY: e.clientY };
      dragging = true;
      rectAbs = { x: start.absX, y: start.absY, w: 0, h: 0 };
      Object.assign(box.style, { left: rectAbs.x + "px", top: rectAbs.y + "px", width: "0px", height: "0px", display: "block" });
      placeDims({ x: rectAbs.x, y: rectAbs.y, w: 0, h: 0 });
      Object.assign(tag.style, { left: (rectAbs.x + 8) + "px", top: (rectAbs.y + 8) + "px", display: "block" });
    });

    overlay.addEventListener("mouseup", async () => {
      if (!dragging) return; dragging = false;
      if (!rectAbs || rectAbs.w < 2 || rectAbs.h < 2) { cleanup(); return; }
      try {
        // 先移除遮罩，确保截图不包含遮罩元素
        overlay.remove();
        const cut = await captureAndCrop(rectAbs, JPEG_QUALITY);
        await uploadAndOcr(cut);
      } catch (err) {
        console.error("[OCR] capture/crop failed:", err);
        toast("截图失败（captureVisibleTab）", false);
      } finally { cleanup(); }
    });

    window.addEventListener("keydown", onKey, { passive: false });
  }
})();
