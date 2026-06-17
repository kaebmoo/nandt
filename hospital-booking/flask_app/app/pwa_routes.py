"""Tenant-aware PWA manifest and service worker endpoints."""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify

from shared_db import models

pwa_bp = Blueprint("pwa", __name__)


def _messaging_config():
    # messaging_config is tenant-only; without a bound tenant g.db is on public and the
    # query would 500. Callers treat None as "not configured".
    if not getattr(g, "tenant", None):
        return None
    return (g.db.query(models.MessagingConfig)
            .order_by(models.MessagingConfig.id.asc()).first())


@pwa_bp.route("/manifest.json")
def manifest():
    hospital_name = getattr(getattr(g, "hospital", None), "name", None) or "NudDee"
    return jsonify({
        "name": f"{hospital_name} Queue",
        "short_name": hospital_name[:12] or "NudDee",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#f8fafc",
        "theme_color": "#6d28d9",
        "lang": "th",
    })


@pwa_bp.route("/pwa/config")
def pwa_config():
    config = _messaging_config()
    public_key = getattr(config, "pwa_vapid_public_key", None)
    active = bool(config and config.pwa_status == "active" and public_key)
    return jsonify({
        "active": active,
        "vapidPublicKey": public_key if active else None,
    })


@pwa_bp.route("/service-worker.js")
def service_worker():
    body = """
self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let payload = { title: "NudDee", body: "มีการแจ้งเตือนใหม่" };
  if (event.data) {
    try {
      payload = Object.assign(payload, event.data.json());
    } catch (_) {
      payload.body = event.data.text();
    }
  }
  event.waitUntil(self.registration.showNotification(payload.title || "NudDee", {
    body: payload.body || "",
    data: { url: payload.url || "/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification.data && event.notification.data.url || "/";
  event.waitUntil(self.clients.openWindow(targetUrl));
});
""".strip()
    return Response(body, mimetype="application/javascript")
