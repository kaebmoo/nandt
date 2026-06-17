(function () {
  "use strict";

  const cfg = window.NUDDEE_MINI_APP || {};

  // --- Deep-link router (Phase 4.5/4.10) -----------------------------------
  // The /queue/enter page (it sets entryDefaultUrl) is the Mini App / LIFF entry:
  // it resolves the deep link and forwards to the right check-in page.
  //   • Telegram direct Mini App (?startapp=sp_<id>) → tgWebAppStartParam in the hash
  //   • LINE LIFF → service_point_id / ready-made checkin_url, delivered INSIDE
  //     liff.state on the primary redirect (may only surface after liff.init()).
  function sameOrigin(url) {
    try { return new URL(url, window.location.href).origin === window.location.origin; }
    catch (_) { return false; }
  }

  function deepLinkTarget() {
    const params = new URLSearchParams(
      (window.location.search || "").replace(/^\?/, "") +
      "&" + (window.location.hash || "").replace(/^#/, "")
    );
    // LINE LIFF carries the original query inside liff.state — fold it in.
    const liffState = params.get("liff.state");
    if (liffState) {
      const q = liffState.indexOf("?") >= 0 ? liffState.slice(liffState.indexOf("?") + 1) : liffState;
      new URLSearchParams(q).forEach((value, key) => {
        if (!params.has(key)) params.set(key, value);
      });
    }
    const checkinUrl = params.get("checkin_url");
    if (checkinUrl && sameOrigin(checkinUrl)) return checkinUrl;   // else: open-redirect, ignore
    let sp = params.get("service_point_id");
    if (!sp) {
      const m = /^sp_(\d+)$/.exec(params.get("startapp") || params.get("tgWebAppStartParam") || "");
      if (m) sp = m[1];
    }
    if (!sp || !/^\d+$/.test(sp)) return null;
    const sub = params.get("subdomain");   // keep tenant context in query mode; drop liff.state noise
    return `/queue/checkin/${sp}${sub ? `?subdomain=${encodeURIComponent(sub)}` : ""}`;
  }

  if (cfg.entryDefaultUrl !== undefined) {
    // Entry page: resolve + forward, then stop. For LINE, liff.state may only resolve
    // after liff.init() (the documented primary-redirect flow) — try it best-effort.
    (async function () {
      let target = deepLinkTarget();
      if (!target && cfg.lineLiffId) {
        try {
          await loadScript("https://static.line-scdn.net/liff/edge/2/sdk.js");
          await window.liff.init({ liffId: cfg.lineLiffId });
          target = deepLinkTarget();
        } catch (_) { /* fall through to the default */ }
      }
      window.location.replace(target || cfg.entryDefaultUrl);
    })();
    return;
  }

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const form = document.querySelector("[data-mini-app-checkin-form]");
  const pwaButton = document.querySelector("[data-pwa-subscribe]");
  const pwaStatus = document.querySelector("[data-pwa-status]");
  let context = { type: "web" };
  let submitted = false;
  let confirmSent = false;

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[src="${src}"]`);
      if (existing) {
        existing.addEventListener("load", resolve, { once: true });
        existing.addEventListener("error", reject, { once: true });
        if (existing.dataset.loaded === "1") resolve();
        return;
      }
      const script = document.createElement("script");
      script.src = src;
      script.async = true;
      script.onload = () => {
        script.dataset.loaded = "1";
        resolve();
      };
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  function withTimeout(promise, ms) {
    return Promise.race([
      promise,
      new Promise((resolve) => window.setTimeout(resolve, ms)),
    ]);
  }

  function isTelegramLaunch() {
    const marker = `${window.location.search || ""}${window.location.hash || ""}`;
    return marker.indexOf("tgWebAppData=") !== -1 || /Telegram/i.test(navigator.userAgent);
  }

  function isLineLaunch() {
    return Boolean(cfg.lineLiffId) && /\bLine\//i.test(navigator.userAgent);
  }

  async function setupTelegram() {
    if (!isTelegramLaunch()) return false;
    await loadScript("https://telegram.org/js/telegram-web-app.js");
    const webApp = window.Telegram && window.Telegram.WebApp;
    if (!webApp || !webApp.initData) return false;
    webApp.ready();
    if (typeof webApp.expand === "function") webApp.expand();
    context = { type: "telegram", initData: webApp.initData };
    document.documentElement.dataset.nuddeeChannel = "telegram";
    return true;
  }

  async function setupLine() {
    if (!isLineLaunch()) return false;
    await loadScript("https://static.line-scdn.net/liff/edge/2/sdk.js");
    if (!window.liff) return false;
    await window.liff.init({ liffId: cfg.lineLiffId });
    if (!window.liff.isLoggedIn()) return false;
    const idToken = window.liff.getIDToken();
    if (!idToken) return false;
    context = { type: "line", idToken };
    document.documentElement.dataset.nuddeeChannel = "line";
    return true;
  }

  async function detectContext() {
    try {
      if (await setupTelegram()) return context;
    } catch (_) {
      context = { type: "web" };
    }
    try {
      if (await setupLine()) return context;
    } catch (_) {
      context = { type: "web" };
    }
    return context;
  }

  const ready = detectContext();

  async function linkCurrentChannel() {
    if (!cfg.channelAuthUrl || !form || context.type === "web") return;
    const payload = {
      channel: context.type,
      booking_reference: form.elements.booking_reference?.value || "",
      patient_phone: form.elements.patient_phone?.value || "",
    };
    if (!payload.booking_reference && !payload.patient_phone) return;
    if (context.type === "line") payload.idToken = context.idToken;
    if (context.type === "telegram") payload.initData = context.initData;

    await fetch(cfg.channelAuthUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
      },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
  }

  async function sendLineCheckinConfirm() {
    if (!cfg.checkinConfirm || confirmSent || !cfg.confirmationText) return;
    await withTimeout(ready, 1500);
    if (context.type !== "line" || !window.liff || !window.liff.isInClient()) return;
    confirmSent = true;
    const url = new URL(window.location.href);
    url.searchParams.delete("checkin_confirm");
    window.history.replaceState({}, document.title, url.toString());
    try {
      await window.liff.sendMessages([{ type: "text", text: cfg.confirmationText }]);
    } catch (_) {
      confirmSent = false;
    }
  }

  function setPwaStatus(message) {
    if (pwaStatus) pwaStatus.textContent = message;
  }

  function base64UrlToUint8Array(value) {
    const padding = "=".repeat((4 - (value.length % 4)) % 4);
    const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = window.atob(base64);
    const output = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) {
      output[i] = raw.charCodeAt(i);
    }
    return output;
  }

  async function subscribePwa() {
    if (!cfg.pwaSubscribeUrl || !cfg.serviceWorkerUrl || !cfg.vapidPublicKey) return;
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setPwaStatus("เบราว์เซอร์นี้ยังไม่รองรับ Web Push");
      return;
    }
    pwaButton.disabled = true;
    setPwaStatus("กำลังขอสิทธิ์แจ้งเตือน...");
    try {
      const permission = await window.Notification.requestPermission();
      if (permission !== "granted") {
        setPwaStatus("ยังไม่ได้อนุญาตการแจ้งเตือน");
        pwaButton.disabled = false;
        return;
      }
      const registration = await navigator.serviceWorker.register(cfg.serviceWorkerUrl);
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: base64UrlToUint8Array(cfg.vapidPublicKey),
      });
      const response = await fetch(cfg.pwaSubscribeUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        credentials: "same-origin",
        body: JSON.stringify({ subscription: subscription.toJSON() }),
      });
      if (!response.ok) throw new Error("subscribe failed");
      setPwaStatus("เปิดรับแจ้งเตือนผ่านเว็บแล้ว");
    } catch (_) {
      pwaButton.disabled = false;
      setPwaStatus("เปิดรับแจ้งเตือนไม่สำเร็จ");
    }
  }

  if (form) {
    form.addEventListener("submit", async (event) => {
      if (submitted) return;
      event.preventDefault();
      submitted = true;
      await withTimeout(ready, 1500);
      await withTimeout(linkCurrentChannel(), 2500);
      form.submit();
    });
  }

  if (pwaButton) {
    pwaButton.addEventListener("click", subscribePwa);
  }

  sendLineCheckinConfirm();
})();
