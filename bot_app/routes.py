"""Flask routes: Telegram webhook + health + expiry cron.

⚠️ IMPORTANT (Vercel behaviour)
The project rewrites every request to ``/api/index.py`` and the WSGI app
receives PATH_INFO = the *rewrite destination*, NOT the client's path.
That is why the old monolith used one universal catch-all route, and why
``/health``, ``/webhook`` style routes never match on Vercel.

So this module is intentionally **path-agnostic**:

- any **POST** → Telegram update (webhook works on ``/``, ``/webhook``,
  ``/index.py``, ``/api/index.py`` — whatever the webhook URL is)
- **GET + Vercel Cron user-agent** → run the nightly expiry cron
- any other **GET** → 200 health text (uptime monitors); dotted probe paths
  (``/.env`` etc.) return 404 when the real path is visible (local/dev)
"""

import hashlib
import hmac
import os
import platform

import telebot
from flask import jsonify, redirect, render_template_string, request, send_from_directory

from bot_app.config import (
    MY_PAYMENT_PHONES, OCR_API_KEY, REQUIRED_CHANNEL, TELEGRAM_TOKEN,
    admin_chat_ids, admin_env_sources, admin_ids_masked, is_telegram_configured,
    outline_api_urls, reminder_cron_secret,
)
from bot_app.extensions import bot
from bot_app.extensions import flask_app as app
from bot_app.helpers.webhook_guard import ensure_webhook, expected_webhook_url
from bot_app.services.notifier import run_expiry_cron
from bot_app.services.points_reminder import run_cooldown_reminders

CRON_USER_AGENT = "vercel-cron"


def diag_key():
    """Access key for /diag: sha256(TELEGRAM_TOKEN)[:16] — token = the secret."""
    return hashlib.sha256((TELEGRAM_TOKEN or "").encode()).hexdigest()[:16]



def _process_update():
    """Parse and dispatch one Telegram update (always ACK 200)."""
    try:
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        if update:
            bot.process_new_updates([update])
    except Exception as e:
        print("Webhook Processing Error:", e)
    return jsonify({"status": "ok"}), 200


def _is_cron_request():
    ua = request.headers.get("User-Agent", "")
    return ua.startswith(CRON_USER_AGENT) or request.headers.get("x-vercel-cron") == "1"


def _is_reminder_request():
    """True for an authorised cooldown-reminder ping.

    Driven by an EXTERNAL scheduler (Vercel Hobby crons only fire daily), so it
    is guarded by a shared secret instead of the Vercel cron user-agent. The
    secret may arrive as ``Authorization: Bearer <secret>`` or ``?key=<secret>``.
    Disabled (never matches) when ``REMINDER_CRON_SECRET`` is unset.
    """
    secret = reminder_cron_secret()
    if not secret:
        return False
    auth = request.headers.get("Authorization", "")
    if auth == f"Bearer {secret}":
        return True
    return request.args.get("key") == secret


def _notify_webhook_restore(guard):
    """Tell admins the delivery path drifted and was auto-repaired."""
    text = (
        "🛠️ Webhook auto-repair: Telegram delivery ပြန်တောင့်တင်းပါပြီ။\n"
        f"Drifted URL: {guard.get('previous') or '∅'}\n"
        f"Restored URL: {guard.get('url')}"
    )
    for chat_id in admin_chat_ids():
        try:
            bot.send_message(chat_id, text)
        except Exception:
            pass


def _is_diag_request():
    key = request.args.get("key", "")
    return bool(key) and hmac.compare_digest(key, diag_key())


def _diag_payload():
    """Secret-safe config snapshot (no ids/tokens in full, booleans + counts)."""
    urls = outline_api_urls()
    connectivity = {}
    import requests as _requests

    for i, url in enumerate(urls, 1):
        label = f"s{i}"
        get_ok = post_ok = False
        try:
            gr = _requests.get(f"{url}/access-keys", verify=False, timeout=6)
            get_ok = 200 <= gr.status_code < 400
        except Exception:
            get_ok = False
        try:
            pr = _requests.post(f"{url}/access-keys", verify=False, timeout=8)
            post_ok = 200 <= pr.status_code < 400
            # remove the test key so the diag doesn't leave stray keys on the server
            if post_ok:
                try:
                    kid = pr.json().get("id")
                    if kid:
                        _requests.delete(f"{url}/access-keys/{kid}", verify=False, timeout=8)
                except Exception:
                    pass
        except Exception:
            post_ok = False
        connectivity[label] = {
            "url": url if url else None,
            "get": get_ok,
            "post": post_ok,
        }

    try:
        live_webhook = (getattr(bot.get_webhook_info(), "url", "") or "").strip()
    except Exception:
        live_webhook = ""
    expected_webhook = expected_webhook_url()

    return {
        "status": "ok",
        "platform": "vercel" if os.environ.get("VERCEL") else "local",
        "git_sha": os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:7],
        "python": platform.python_version(),
        "telegram_configured": is_telegram_configured(),
        "admins": len(admin_chat_ids()),
        "admin_ids_masked": admin_ids_masked(),
        "admin_env_sources": admin_env_sources(),
        "outline_servers": len(urls),
        "outline_connectivity": connectivity,
        "kv": bool(os.environ.get("KV_REST_API_URL")),
        "ocr": bool(OCR_API_KEY),
        "payment_phones": len(MY_PAYMENT_PHONES),
        "required_channel": REQUIRED_CHANNEL,
        "webhook_url": live_webhook,
        "webhook_ok": (live_webhook.rstrip("/") == expected_webhook.rstrip("/")
                       if expected_webhook else None),
    }


from bot_app.routes_admin import admin_bp
from bot_app.routes_app import app_bp
from bot_app.routes_user import user_bp

# Register Admin and Customer REST API Blueprints
app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)
app.register_blueprint(app_bp)

# ── One-tap key import landing page (/go/<token>) ───────────────────
# Telegram URL buttons reject custom schemes (ss://), so the bot hands out
# signed https links to this page; it fires the target app's scheme and keeps
# manual/copy fallbacks for restricted in-app browsers.
_GO_PAGE = """<!doctype html>
<html lang="my">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🔑 VPN Key Import</title>
<style>
  body { font-family:-apple-system,'Segoe UI',Roboto,sans-serif; background:#0b1120; color:#e2e8f0;
         display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; padding:24px; box-sizing:border-box; }
  .card { background:#1e293b; border-radius:16px; padding:28px 22px; max-width:420px; width:100%; text-align:center; }
  h1 { font-size:18px; margin:0 0 6px; color:#10b981; }
  p { font-size:13.5px; line-height:1.6; color:#94a3b8; margin:8px 0 18px; word-break:break-all; }
  a.btn, button.btn { display:block; width:100%; box-sizing:border-box; padding:13px 16px; margin:10px 0;
         border-radius:10px; border:none; font-size:15px; font-weight:600; text-decoration:none; cursor:pointer; }
  .primary { background:#10b981; color:#04281c; }
  .ghost { background:transparent; color:#10b981; border:1px solid rgba(16,185,129,.45); }
  .hint { font-size:12px; color:#64748b; margin-top:14px; }
  .ok { color:#10b981; display:none; margin:6px 0 0; }
</style>
</head>
<body>
<div class="card">
  <h1>🔑 VPN Key Import</h1>
  <p>{{ key_label }}</p>
  <a class="btn primary" href="{{ ss_attr }}">📲 Outline တွင် ဖွင့်မည်</a>
  <a class="btn ghost" href="{{ v2box_attr }}">🟩 V2Box တွင် ဖွင့်မည်</a>
  <a class="btn ghost" href="{{ incy_attr }}">🧩 INCY တွင် ဖွင့်မည်</a>
  <button class="btn ghost" id="copy">📋 Key ကို Copy မည်</button>
  <p class="ok" id="copied">✅ Copy ကူးပြီးပါပြီ — V2Box → ➕ → Import from clipboard မှလည်း ထည့်နိုင်ပါသည်</p>
  <p class="hint">ဖွင့်လို့ မရပါက Outline / V2Box / INCY app ကို နောက်ဆုံး version အထိ update လုပ်ပါ (သို့) install လုပ်ပါ။</p>
</div>
<script>
var ss = {{ ss_attr | tojson }};
var auto = {{ auto_url | tojson }};
try { window.location.href = auto; } catch (e) {}
document.getElementById('copy').addEventListener('click', function () {
  var done = function () { document.getElementById('copied').style.display = 'block'; };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(ss).then(done);
  } else {
    var t = document.createElement('textarea'); t.value = ss;
    document.body.appendChild(t); t.select();
    try { document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(t); done();
  }
});
</script>
</body>
</html>"""


@app.route("/go/<token>", methods=["GET"])
def go_deep_link(token):
    from bot_app.helpers.deeplink import verify_go_token
    from bot_app.services.registry import load_persistent_keys
    from urllib.parse import quote

    ref = verify_go_token(token)
    if not ref:
        return "Invalid link", 404

    entry = load_persistent_keys().get(f"{ref[0]}_{ref[1]}") or {}
    access_url = (entry.get("access_url") or "").strip()
    if not access_url:
        return "Key not found", 404

    key_label = access_url.split("#", 1)[1] if "#" in access_url else "VPN Access Key"
    scheme_for = {
        "outline": access_url,
        "incy": f"incy://add/{access_url}",
        # V2Box install-config expects a URL-encoded config link.
        "v2box": f"v2box://install-config?url={quote(access_url, safe='')}",
    }
    auto_url = scheme_for.get(request.args.get("app"), access_url)
    return render_template_string(
        _GO_PAGE,
        key_label=key_label,
        ss_attr=access_url,
        v2box_attr=scheme_for["v2box"],
        incy_attr=scheme_for["incy"],
        auto_url=auto_url,
    ), 200, {"Cache-Control": "no-store"}


class VercelPathFixMiddleware:
    """Restores real request path from Vercel rewrite headers if rewritten to /api/index.py."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        matched = environ.get("HTTP_X_MATCHED_PATH") or environ.get("HTTP_X_FORWARDED_URI")
        if matched and environ.get("PATH_INFO") in ("/api/index.py", "/index.py"):
            # Vercel forwards the RAW request-target, still percent-encoded
            # (e.g. %23 for '#'). WSGI requires a DECODED PATH_INFO — Flask's
            # own dev server decodes, which is why these routes worked locally
            # but 404'd on production ("Slip not found" for id '#082412').
            if "%" in matched:
                from urllib.parse import unquote
                matched = unquote(matched)
            environ["PATH_INFO"] = matched
        return self.wsgi_app(environ, start_response)


app.wsgi_app = VercelPathFixMiddleware(app.wsgi_app)
MINI_APP_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mini_app", "dist"))


@app.route("/app")
def mini_app_redirect():
    return redirect("/app/", code=302)


@app.route("/app/", defaults={"path": ""})
@app.route("/app/<path:path>")
def serve_mini_app(path=""):
    if not os.path.exists(MINI_APP_DIST):
        return "Mini App dist not found. Please build it with 'npm run build' in mini_app.", 404
    if path and os.path.exists(os.path.join(MINI_APP_DIST, path)):
        return send_from_directory(MINI_APP_DIST, path)
    return send_from_directory(MINI_APP_DIST, "index.html")


@app.route("/", defaults={"path": ""}, methods=["GET", "POST"])
@app.route("/<path:path>", methods=["GET", "POST"])
def entry(path=""):
    # If an admin API request was routed here (unmatched admin sub-path), return 404 JSON
    if request.path.startswith("/api/admin") or path.startswith("api/admin"):
        return jsonify({"error": "Admin endpoint not found"}), 404

    if request.method == "POST":
        return _process_update()

    # Protected self-check: GET /diag?key=<sha256(TELEGRAM_TOKEN)[:16]>
    if _is_diag_request():
        return jsonify(_diag_payload()), 200

    if _is_cron_request():
        guard = ensure_webhook(bot)
        if guard.get("fixed"):
            _notify_webhook_restore(guard)
        result = run_expiry_cron()
        return jsonify({"status": "cron completed", "webhook_guard": guard, **result}), 200

    if _is_reminder_request():
        result = run_cooldown_reminders()
        # Also move any in-flight broadcast forward: the ~15-minute
        # pinger guarantees a broadcast finishes even if the admin
        # never taps the "continue" button.
        try:
            from bot_app.services.broadcast import advance_broadcast

            advance_broadcast(bot, budget_s=30.0, cap=100)
        except Exception:
            pass
        return jsonify({"status": "reminder completed", **result}), 200

    # Hide secret-ish probe paths when the real path reaches us (dev/local).
    if path and path.rsplit("/", 1)[-1].startswith("."):
        return jsonify({"status": "not found"}), 404

    return "Bot is running perfectly!", 200



