import os
import json
import logging
import random
import httpx
from fastapi import FastAPI, Request, Query, Depends, HTTPException
from datetime import datetime, timedelta
from fastapi.responses import PlainTextResponse, HTMLResponse, RedirectResponse, JSONResponse
import database as db
from auth import hash_password, verify_password, create_token, get_current_user, TOKEN_EXPIRE_DAYS
import instagram_oauth

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("insta-dm")

import base64

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = "marinasba/instagram-auto-dm"
CONFIG_FILE = "config.json"


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


async def save_config_to_github(config):
    if not GITHUB_TOKEN:
        return
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CONFIG_FILE}",
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
        )
        sha = r.json().get("sha", "") if r.status_code == 200 else ""
        content = base64.b64encode(json.dumps(config, indent=2, ensure_ascii=False).encode()).decode()
        await client.put(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CONFIG_FILE}",
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
            json={"message": "Update config via admin", "content": content, "sha": sha},
        )
    logger.info("Config sauvegardee sur GitHub")


CONFIG = load_config()

VERIFY_TOKEN = os.environ["VERIFY_TOKEN"]
ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", VERIFY_TOKEN)
GRAPH_API = "https://graph.instagram.com/v21.0"

sent_comments: set[str] = set()
recent_events: list[dict] = []


@app.on_event("startup")
def startup():
    db.init_db()
    migrate_gariguettes()


def migrate_gariguettes():
    user = db.get_user_by_email("contact@gariguettes.fr")
    if user:
        if not db.get_instagram_account(user["id"]):
            db.create_instagram_account(user["id"], "17841447700219621", "gariguettes_fr", ACCESS_TOKEN)
            logger.info("Instagram account added for Gariguettes")
        return
    pw = os.environ.get("GARIGUETTES_PASSWORD", ADMIN_TOKEN)
    user_id = db.create_user("contact@gariguettes.fr", hash_password(pw))
    keyword_posts = CONFIG.get("keyword_posts", {})
    for kw, msg in CONFIG["keywords"].items():
        kp = keyword_posts.get(kw) or {}
        db.create_keyword(user_id, kw, msg, kp.get("url"), kp.get("media_id"))
    for txt in CONFIG.get("replies", []):
        db.create_reply(user_id, txt)
    expires = (datetime.utcnow() + timedelta(days=365)).isoformat()
    db.create_subscription(user_id, expires)
    db.create_instagram_account(user_id, "17841447700219621", "gariguettes_fr", ACCESS_TOKEN)
    logger.info(f"Migration Gariguettes OK (user_id={user_id})")


def check_admin(token: str = Query(default="")):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Token invalide")


@app.get("/")
async def root():
    return {"status": "ok", "app": "instagram-auto-dm"}


@app.get("/privacy", response_class=HTMLResponse)
async def privacy():
    return """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>Politique de confidentialité</title>
<style>body{font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px;color:#333;}</style></head><body>
<h1>Politique de confidentialité</h1>
<p>Cette application envoie des messages directs automatisés sur Instagram en réponse aux commentaires contenant des mots-clés spécifiques.</p>
<p><strong>Données collectées :</strong> Aucune donnée personnelle n'est stockée. Seul l'identifiant du commentaire est temporairement conservé en mémoire pour éviter les doublons.</p>
<p><strong>Utilisation :</strong> Les données sont utilisées uniquement pour envoyer le message automatique correspondant.</p>
<p><strong>Contact :</strong> contact@gariguettes.fr</p>
</body></html>"""


# ─── Auth pages ───

AUTH_STYLE = """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f0eb; color: #2d2d2d; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px; }
  .container { background: white; border-radius: 16px; padding: 40px; width: 100%; max-width: 400px; box-shadow: 0 4px 16px rgba(0,0,0,0.1); }
  h1 { font-size: 1.5em; color: #4a7c59; margin-bottom: 8px; }
  .subtitle { color: #888; font-size: 0.9em; margin-bottom: 24px; }
  label { display: block; font-weight: 600; margin-bottom: 6px; font-size: 0.9em; }
  input { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 12px; font-size: 1em; margin-bottom: 16px; font-family: inherit; }
  input:focus { outline: none; border-color: #4a7c59; }
  .btn { width: 100%; border: none; border-radius: 8px; padding: 14px; font-size: 1em; font-weight: 600; cursor: pointer; background: #4a7c59; color: white; transition: background 0.3s; }
  .btn:hover { background: #3d6a4c; }
  .error { background: #fef2f2; color: #c0392b; padding: 12px; border-radius: 8px; margin-bottom: 16px; font-size: 0.9em; display: none; }
  .link { text-align: center; margin-top: 20px; font-size: 0.9em; }
  .link a { color: #4a7c59; text-decoration: none; font-weight: 600; }
"""

LOGIN_HTML = f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connexion - Messages Auto</title>
<style>{AUTH_STYLE}</style></head>
<body>
<div class="container">
  <h1>Connexion</h1>
  <p class="subtitle">Messages Auto Instagram</p>
  <div class="error" id="error"></div>
  <form onsubmit="login(event)">
    <label>Email</label>
    <input type="email" id="email" required placeholder="ton@email.com">
    <label>Mot de passe</label>
    <input type="password" id="password" required placeholder="\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022">
    <button type="submit" class="btn">Se connecter</button>
  </form>
  <div class="link">Pas encore de compte ? <a href="/signup">Cr\u00e9er un compte</a></div>
</div>
<script>
async function login(e) {{
  e.preventDefault();
  const r = await fetch('/api/login', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{email: document.getElementById('email').value, password: document.getElementById('password').value}})
  }});
  if (r.ok) {{ window.location.href = '/dashboard'; }}
  else {{ const d = await r.json(); const err = document.getElementById('error'); err.textContent = d.detail || 'Erreur'; err.style.display = 'block'; }}
}}
</script>
</body></html>"""

SIGNUP_HTML = f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Inscription - Messages Auto</title>
<style>{AUTH_STYLE}</style></head>
<body>
<div class="container">
  <h1>Cr\u00e9er un compte</h1>
  <p class="subtitle">Messages Auto Instagram</p>
  <div class="error" id="error"></div>
  <form onsubmit="signup(event)">
    <label>Email</label>
    <input type="email" id="email" required placeholder="ton@email.com">
    <label>Mot de passe</label>
    <input type="password" id="password" required minlength="6" placeholder="6 caract\u00e8res minimum">
    <label>Confirmer le mot de passe</label>
    <input type="password" id="password2" required placeholder="\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022">
    <button type="submit" class="btn">Cr\u00e9er mon compte</button>
  </form>
  <div class="link">D\u00e9j\u00e0 un compte ? <a href="/login">Se connecter</a></div>
</div>
<script>
async function signup(e) {{
  e.preventDefault();
  const pw = document.getElementById('password').value;
  const pw2 = document.getElementById('password2').value;
  const err = document.getElementById('error');
  if (pw !== pw2) {{ err.textContent = 'Les mots de passe ne correspondent pas'; err.style.display = 'block'; return; }}
  const r = await fetch('/api/signup', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{email: document.getElementById('email').value, password: pw}})
  }});
  if (r.ok) {{ window.location.href = '/dashboard'; }}
  else {{ const d = await r.json(); err.textContent = d.detail || 'Erreur'; err.style.display = 'block'; }}
}}
</script>
</body></html>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tableau de bord - Messages Auto</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f0eb; color: #2d2d2d; padding: 20px; max-width: 700px; margin: 0 auto; }
  h1 { font-size: 1.5em; color: #4a7c59; }
  .subtitle { color: #888; font-size: 0.9em; margin-bottom: 24px; }
  .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
  .card { background: white; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
  .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .keyword { font-weight: 700; font-size: 1.1em; color: #4a7c59; text-transform: uppercase; }
  .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: 600; }
  .badge-ok { background: #dcfce7; color: #16a34a; }
  .badge-ko { background: #fef2f2; color: #c0392b; }
  .btn { border: none; border-radius: 8px; padding: 8px 16px; cursor: pointer; font-size: 0.9em; font-weight: 600; }
  .btn-delete { background: #f5e6e6; color: #c0392b; }
  .btn-delete:hover { background: #e8d0d0; }
  .btn-save { background: #2563eb; color: white; width: 100%; padding: 12px; font-size: 1em; transition: background 0.3s; }
  .btn-save:hover { background: #1d4ed8; }
  .btn-save.saved { background: #16a34a; }
  .btn-add { background: white; color: #4a7c59; border: 2px dashed #4a7c59; width: 100%; padding: 14px; font-size: 1em; margin-bottom: 16px; border-radius: 12px; }
  .btn-add:hover { background: #f0f7f2; }
  .btn-logout { background: #f5e6e6; color: #c0392b; text-decoration: none; padding: 10px 20px; border-radius: 8px; }
  .btn-logout:hover { background: #e8d0d0; }
  textarea { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 12px; font-family: inherit; font-size: 0.9em; resize: vertical; min-height: 100px; }
  input[type=text] { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 10px 12px; font-family: inherit; font-size: 1em; margin-bottom: 12px; }
  .tabs { display: flex; gap: 0; margin-bottom: 20px; }
  .tab { flex: 1; padding: 12px; text-align: center; font-weight: 600; font-size: 1em; cursor: pointer; border: none; background: white; color: #888; border-bottom: 3px solid #ddd; transition: all 0.2s; }
  .tab.active { color: #4a7c59; border-bottom-color: #4a7c59; }
  .tab:first-child { border-radius: 8px 0 0 0; }
  .tab:last-child { border-radius: 0 8px 0 0; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .empty { text-align: center; color: #999; padding: 40px; }
</style></head>
<body>
<div class="header">
  <div><h1>Messages Auto</h1><p class="subtitle" id="user-info"></p></div>
  <a href="/logout" class="btn btn-logout">D\u00e9connexion</a>
</div>

<div class="tabs">
  <button class="tab active" onclick="switchTab('keywords')">Mots-cl\u00e9s</button>
  <button class="tab" onclick="switchTab('replies')">R\u00e9ponses aux commentaires</button>
</div>

<button class="btn btn-save" onclick="saveAll()" style="margin-bottom:16px;">Enregistrer</button>

<div id="tab-keywords" class="tab-content active">
  <button class="btn btn-add" onclick="addNew()">+ Ajouter un mot-cl\u00e9</button>
  <div id="keywords"></div>
  <button class="btn btn-save" onclick="saveAll()">Enregistrer</button>
</div>

<div id="tab-replies" class="tab-content">
  <button class="btn btn-add" onclick="addReply()">+ Ajouter une r\u00e9ponse</button>
  <p class="subtitle">Une r\u00e9ponse sera choisie au hasard pour chaque commentaire</p>
  <div id="replies" class="card" style="margin-bottom:16px;"></div>
  <button class="btn btn-save" onclick="saveAll()">Enregistrer</button>
</div>

<div class="card" id="ig-card">
  <h2 style="margin-bottom:8px;">Instagram</h2>
  <p id="ig-status"></p>
</div>

<script>
let keywords = [];
let replies = [];

function esc(s) {
  return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function loadUser() {
  const r = await fetch('/api/me');
  if (!r.ok) { window.location.href = '/login'; return; }
  const d = await r.json();
  const badge = d.has_subscription
    ? '<span class="badge badge-ok">Actif</span>'
    : '<span class="badge badge-ko">Inactif</span>';
  document.getElementById('user-info').innerHTML = d.email + ' \u2014 ' + badge;
  const ig = document.getElementById('ig-status');
  if (d.instagram_connected) {
    ig.innerHTML = '<span class="badge badge-ok">Connect\u00e9</span> @' + d.instagram_username + ' \u2014 <a href="/instagram/disconnect" style="color:#c0392b;">D\u00e9connecter</a>';
  } else {
    ig.innerHTML = '<a href="/instagram/connect" style="background:#4a7c59;color:white;display:inline-block;padding:10px 20px;text-decoration:none;border-radius:8px;font-weight:600;">Connecter Instagram</a>';
  }
}

function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
  document.querySelector('.tab[onclick*="' + tab + '"]').classList.add('active');
}

async function load() {
  await loadUser();
  const r = await fetch('/api/dashboard/config');
  if (!r.ok) return;
  const data = await r.json();
  keywords = data.keywords || [];
  replies = data.replies || [];
  render();
  renderReplies();
}

function render() {
  const el = document.getElementById('keywords');
  if (!keywords.length) { el.innerHTML = '<div class="empty">Aucun mot-cl\u00e9 configur\u00e9</div>'; return; }
  el.innerHTML = keywords.map((kw, i) => {
    const hasUrl = kw.post_url && kw.post_url.trim();
    const resolvedOk = hasUrl && kw.media_id;
    let urlStatus = '';
    if (hasUrl && resolvedOk) {
      urlStatus = '<p style="color:#16a34a;font-size:0.85em;margin-top:4px;">\u2713 Post associ\u00e9 (id ' + esc(kw.media_id) + ')</p>';
    } else if (hasUrl && !resolvedOk) {
      urlStatus = "<p style='color:#c0392b;font-size:0.85em;margin-top:4px;'>\u26a0 Post non trouv\u00e9. V\u00e9rifie l'URL et clique sur Enregistrer.</p>";
    } else {
      urlStatus = '<p style="color:#888;font-size:0.85em;margin-top:4px;">Vide = se d\u00e9clenche sur tous tes posts.</p>';
    }
    return `
    <div class="card">
      <div class="card-header">
        <span class="keyword">${esc(kw.keyword)}</span>
        <button class="btn btn-delete" onclick="remove(${i})">Supprimer</button>
      </div>
      <label style="display:block;font-weight:600;margin-bottom:6px;font-size:0.9em;">Message DM</label>
      <textarea onchange="keywords[${i}].message=this.value">${esc(kw.message)}</textarea>
      <label style="display:block;font-weight:600;margin:12px 0 6px;font-size:0.9em;">URL du post Instagram (optionnel)</label>
      <input type="text" placeholder="https://www.instagram.com/p/..." value="${esc(kw.post_url)}" onchange="keywords[${i}].post_url=this.value;keywords[${i}].media_id=null;render();" style="margin-bottom:0;">
      ${urlStatus}
    </div>
  `;
  }).join('');
}

function renderReplies() {
  const el = document.getElementById('replies');
  if (!replies.length) { el.innerHTML = '<div class="empty">Aucune r\u00e9ponse configur\u00e9e</div>'; return; }
  el.innerHTML = replies.map((r, i) => `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
      <input type="text" value="${esc(r)}" onchange="replies[${i}]=this.value" style="margin:0;flex:1;">
      <button class="btn btn-delete" onclick="replies.splice(${i},1);renderReplies();">X</button>
    </div>
  `).join('');
}

function addNew() {
  const kw = prompt('Nouveau mot-cl\u00e9 (ex: CHARIOT, GUIDE, TISANE) :');
  if (!kw) return;
  const key = kw.toUpperCase().trim();
  if (keywords.find(k => k.keyword === key)) { alert('Ce mot-cl\u00e9 existe d\u00e9j\u00e0 !'); return; }
  keywords.unshift({keyword: key, message: '', post_url: '', media_id: null});
  render();
  document.querySelector('.card:first-child textarea').focus();
}

function addReply() {
  replies.push('');
  renderReplies();
  document.querySelector('#replies input:last-of-type').focus();
}

function remove(i) {
  if (!confirm('Supprimer le mot-cl\u00e9 ' + keywords[i].keyword + ' ?')) return;
  keywords.splice(i, 1);
  render();
}

async function saveAll() {
  const btns = document.querySelectorAll('.btn-save');
  btns.forEach(btn => { btn.textContent = 'Enregistrement...'; });
  const r = await fetch('/api/dashboard/config', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({keywords, replies: replies.filter(r => r.trim())})
  });
  if (r.ok) {
    const d = await r.json();
    if (d.keywords) { keywords = d.keywords; render(); }
  }
  btns.forEach(btn => { btn.textContent = 'Enregistr\u00e9 !'; btn.classList.add('saved'); });
  setTimeout(() => btns.forEach(btn => { btn.textContent = 'Enregistrer'; btn.classList.remove('saved'); }), 2500);
}

load();
</script>
</body></html>"""


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard")
    return LOGIN_HTML


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard")
    return SIGNUP_HTML


@app.post("/api/signup")
async def api_signup(request: Request):
    data = await request.json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email et mot de passe requis")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Le mot de passe doit faire au moins 6 caract\u00e8res")
    if db.get_user_by_email(email):
        raise HTTPException(status_code=400, detail="Un compte existe d\u00e9j\u00e0 avec cet email")
    user_id = db.create_user(email, hash_password(password))
    token = create_token(user_id, email)
    response = JSONResponse({"status": "ok"})
    response.set_cookie("session", token, httponly=True, max_age=TOKEN_EXPIRE_DAYS * 86400, samesite="lax")
    return response


@app.post("/api/login")
async def api_login(request: Request):
    data = await request.json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    user = db.get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    token = create_token(user["id"], email)
    response = JSONResponse({"status": "ok"})
    response.set_cookie("session", token, httponly=True, max_age=TOKEN_EXPIRE_DAYS * 86400, samesite="lax")
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login")
    response.delete_cookie("session")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not get_current_user(request):
        return RedirectResponse("/login")
    return DASHBOARD_HTML


@app.get("/api/me")
async def api_me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Non connect\u00e9")
    sub = db.get_active_subscription(user["user_id"])
    ig = db.get_instagram_account(user["user_id"])
    return {
        "email": user["email"],
        "has_subscription": sub is not None,
        "expires_at": dict(sub)["expires_at"] if sub else None,
        "instagram_connected": ig is not None,
        "instagram_username": ig["username"] if ig else None,
    }


@app.get("/api/dashboard/config")
async def get_dashboard_config(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Non connect\u00e9")
    keywords_rows = db.get_keywords(user["user_id"])
    replies_rows = db.get_replies(user["user_id"])
    keywords = [
        {
            "keyword": r["keyword"],
            "message": r["message"],
            "post_url": r["post_url"],
            "media_id": r["media_id"],
        }
        for r in keywords_rows
    ]
    replies = [row["text"] for row in replies_rows]
    return {"keywords": keywords, "replies": replies}


@app.put("/api/dashboard/config")
async def update_dashboard_config(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Non connect\u00e9")
    data = await request.json()
    raw_keywords = data.get("keywords", [])
    if isinstance(raw_keywords, dict):
        raw_keywords = [{"keyword": k, "message": v} for k, v in raw_keywords.items()]

    ig = db.get_instagram_account(user["user_id"])
    access_token = ig["access_token"] if ig else None
    ig_user_id = ig["instagram_id"] if ig else None

    existing = {row["keyword"]: row for row in db.get_keywords(user["user_id"])}
    resolved: list = []
    for item in raw_keywords:
        kw = (item.get("keyword") or "").strip().upper()
        if not kw:
            continue
        msg = item.get("message", "")
        post_url = (item.get("post_url") or "").strip() or None
        media_id = None
        if post_url:
            prev = existing.get(kw)
            if prev and prev["post_url"] == post_url and prev["media_id"]:
                media_id = prev["media_id"]
            elif access_token and ig_user_id:
                media_id = await instagram_oauth.resolve_media_id(post_url, ig_user_id, access_token)
                if not media_id:
                    logger.warning(f"URL non resolue: {post_url} (mot-cle {kw})")
        resolved.append({"keyword": kw, "message": msg, "post_url": post_url, "media_id": media_id})

    db.update_keywords(user["user_id"], resolved)
    db.update_replies(user["user_id"], data.get("replies", []))
    return {"status": "ok", "keywords": resolved}


# ─── Instagram OAuth ───

@app.get("/instagram/connect")
async def instagram_connect(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    url = instagram_oauth.get_authorize_url(state=str(user["user_id"]))
    return RedirectResponse(url)


@app.get("/instagram/callback")
async def instagram_callback(request: Request, code: str = "", state: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    token_data = await instagram_oauth.exchange_code(code)
    if "error" in token_data:
        logger.error(f"OAuth error: {token_data['error']}")
        return HTMLResponse("<h1>Erreur</h1><p>Impossible de connecter Instagram. <a href='/dashboard'>Retour</a></p>", status_code=400)

    short_token = token_data.get("access_token", "")
    long_data = await instagram_oauth.get_long_lived_token(short_token)
    access_token = long_data.get("access_token", short_token)
    expires_in = long_data.get("expires_in", 0)

    profile = await instagram_oauth.get_profile(access_token)
    ig_id = str(profile.get("id", token_data.get("user_id", "")))
    username = profile.get("username", "")

    expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() if expires_in else None

    db.delete_instagram_account(user["user_id"])
    db.create_instagram_account(user["user_id"], ig_id, username, access_token)
    logger.info(f"Instagram connecte: @{username} pour user {user['user_id']}")

    return RedirectResponse("/dashboard")


@app.get("/instagram/disconnect")
async def instagram_disconnect(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    db.delete_instagram_account(user["user_id"])
    logger.info(f"Instagram deconnecte pour user {user['user_id']}")
    return RedirectResponse("/dashboard")


@app.get("/logs")
async def get_logs(_=Depends(check_admin)):
    return recent_events[-50:]


# ─── Admin interface ───

ADMIN_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Messages Auto - Admin</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f0eb; color: #2d2d2d; padding: 20px; max-width: 700px; margin: 0 auto; }
  h1 { font-size: 1.5em; margin-bottom: 8px; color: #4a7c59; }
  .subtitle { color: #888; font-size: 0.9em; margin-bottom: 24px; }
  .card { background: white; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
  .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .keyword { font-weight: 700; font-size: 1.1em; color: #4a7c59; text-transform: uppercase; }
  .btn { border: none; border-radius: 8px; padding: 8px 16px; cursor: pointer; font-size: 0.9em; font-weight: 600; }
  .btn-delete { background: #f5e6e6; color: #c0392b; }
  .btn-delete:hover { background: #e8d0d0; }
  .btn-save { background: #2563eb; color: white; width: 100%; padding: 12px; font-size: 1em; transition: background 0.3s; }
  .btn-save:hover { background: #1d4ed8; }
  .btn-save.saved { background: #16a34a; }
  .btn-save.saved:hover { background: #16a34a; }
  .btn-add { background: white; color: #4a7c59; border: 2px dashed #4a7c59; width: 100%; padding: 14px; font-size: 1em; margin-bottom: 16px; border-radius: 12px; }
  .btn-add:hover { background: #f0f7f2; }
  textarea { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 12px; font-family: inherit; font-size: 0.9em; resize: vertical; min-height: 100px; }
  input[type=text] { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 10px 12px; font-family: inherit; font-size: 1em; margin-bottom: 12px; }
  .tabs { display: flex; gap: 0; margin-bottom: 20px; }
  .tab { flex: 1; padding: 12px; text-align: center; font-weight: 600; font-size: 1em; cursor: pointer; border: none; background: white; color: #888; border-bottom: 3px solid #ddd; transition: all 0.2s; }
  .tab.active { color: #4a7c59; border-bottom-color: #4a7c59; }
  .tab:first-child { border-radius: 8px 0 0 0; }
  .tab:last-child { border-radius: 0 8px 0 0; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .empty { text-align: center; color: #999; padding: 40px; }
</style>
</head>
<body>
<h1>Messages Auto Instagram</h1>
<p class="subtitle">gariguettes_fr</p>

<div class="tabs">
  <button class="tab active" onclick="switchTab('keywords')">Mots-cl\u00e9s</button>
  <button class="tab" onclick="switchTab('replies')">R\u00e9ponses aux commentaires</button>
</div>

<button class="btn btn-save" onclick="saveAll()" style="margin-bottom:16px;">Enregistrer</button>

<div id="tab-keywords" class="tab-content active">
  <button class="btn btn-add" onclick="addNew()">+ Ajouter un mot-cl\u00e9</button>
  <div id="keywords"></div>
  <button class="btn btn-save" onclick="saveAll()">Enregistrer</button>
</div>

<div id="tab-replies" class="tab-content">
  <button class="btn btn-add" onclick="addReply()">+ Ajouter une r\u00e9ponse</button>
  <p class="subtitle">Une r\u00e9ponse sera choisie au hasard pour chaque commentaire</p>
  <div id="replies" class="card" style="margin-bottom:16px;"></div>
  <button class="btn btn-save" onclick="saveAll()">Enregistrer</button>
</div>

<script>
const TOKEN = new URLSearchParams(location.search).get('token');
let keywords = {};
let keywordPosts = {};
let replies = [];

function escHtml(s) {
  return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
  document.querySelector('.tab[onclick*="' + tab + '"]').classList.add('active');
}

async function load() {
  const r = await fetch('/api/config?token=' + TOKEN);
  const data = await r.json();
  keywords = data.keywords || {};
  keywordPosts = data.keyword_posts || {};
  replies = data.replies || [];
  render();
  renderReplies();
}

function render() {
  const el = document.getElementById('keywords');
  const keys = Object.keys(keywords);
  if (!keys.length) { el.innerHTML = '<div class="empty">Aucun mot-clé configuré</div>'; return; }
  el.innerHTML = keys.map(k => {
    const post = keywordPosts[k] || {};
    const url = post.url || '';
    const mediaId = post.media_id || '';
    let urlStatus;
    if (url && mediaId) {
      urlStatus = '<p style="color:#16a34a;font-size:0.85em;margin-top:4px;">✓ Post associé (id ' + escHtml(mediaId) + ')</p>';
    } else if (url && !mediaId) {
      urlStatus = "<p style='color:#c0392b;font-size:0.85em;margin-top:4px;'>⚠ Post non trouvé. Vérifie l'URL puis Enregistre.</p>";
    } else {
      urlStatus = '<p style="color:#888;font-size:0.85em;margin-top:4px;">Vide = se déclenche sur tous les posts.</p>';
    }
    return `
    <div class="card">
      <div class="card-header">
        <span class="keyword">${k}</span>
        <button class="btn btn-delete" onclick="remove('${k}')">Supprimer</button>
      </div>
      <label style="display:block;font-weight:600;margin-bottom:6px;font-size:0.9em;">Message DM</label>
      <textarea onchange="keywords['${k}']=this.value">${keywords[k]}</textarea>
      <label style="display:block;font-weight:600;margin:12px 0 6px;font-size:0.9em;">URL du post Instagram (optionnel)</label>
      <input type="text" placeholder="https://www.instagram.com/p/..." value="${escHtml(url)}" onchange="setUrl('${k}', this.value)" style="margin-bottom:0;">
      ${urlStatus}
    </div>
  `;
  }).join('');
}

function setUrl(k, v) {
  const url = (v || '').trim();
  if (!url) { delete keywordPosts[k]; render(); return; }
  keywordPosts[k] = {url: url, media_id: null};
  render();
}

function renderReplies() {
  const el = document.getElementById('replies');
  if (!replies.length) { el.innerHTML = '<div class="empty">Aucune r\u00e9ponse configur\u00e9e</div>'; return; }
  el.innerHTML = replies.map((r, i) => `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
      <input type="text" value="${r}" onchange="replies[${i}]=this.value" style="margin:0;flex:1;">
      <button class="btn btn-delete" onclick="replies.splice(${i},1);renderReplies();">X</button>
    </div>
  `).join('');
}

function addNew() {
  const kw = prompt('Nouveau mot-clé (ex: CHARIOT, GUIDE, TISANE) :');
  if (!kw) return;
  const key = kw.toUpperCase().trim();
  if (keywords[key]) { alert('Ce mot-clé existe déjà !'); return; }
  const updated = {};
  updated[key] = '';
  Object.keys(keywords).forEach(k => updated[k] = keywords[k]);
  keywords = updated;
  render();
  document.querySelector('.card:first-child textarea').focus();
}

function addReply() {
  replies.push('');
  renderReplies();
  document.querySelector('#replies input:last-of-type').focus();
}

function remove(k) {
  if (!confirm('Supprimer le mot-clé ' + k + ' ?')) return;
  delete keywords[k];
  delete keywordPosts[k];
  render();
}

async function saveAll() {
  const btns = document.querySelectorAll('.btn-save');
  btns.forEach(btn => { btn.textContent = 'Enregistrement...'; });
  const resp = await fetch('/api/config?token=' + TOKEN, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({keywords, keyword_posts: keywordPosts, replies: replies.filter(r => r.trim())})
  });
  if (resp.ok) {
    const d = await resp.json();
    if (d.keyword_posts) { keywordPosts = d.keyword_posts; render(); }
  }
  btns.forEach(btn => { btn.textContent = 'Enregistr\u00e9 !'; btn.classList.add('saved'); });
  setTimeout(() => btns.forEach(btn => { btn.textContent = 'Enregistrer'; btn.classList.remove('saved'); }), 2500);
}

load();
</script>
</body>
</html>"""


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(token: str = Query(default="")):
    if token != ADMIN_TOKEN:
        return HTMLResponse("<h1>Accès refusé</h1><p>Ajoute ?token=TON_TOKEN à l'URL</p>", status_code=403)
    return ADMIN_HTML


@app.get("/api/keywords")
async def get_keywords(_=Depends(check_admin)):
    return CONFIG["keywords"]


@app.get("/api/config")
async def get_config(_=Depends(check_admin)):
    return {
        "keywords": CONFIG["keywords"],
        "replies": CONFIG.get("replies", []),
        "keyword_posts": CONFIG.get("keyword_posts", {}),
    }


@app.put("/api/config")
async def update_config(request: Request, _=Depends(check_admin)):
    data = await request.json()
    new_keywords = data.get("keywords", {})
    new_replies = data.get("replies", [])
    new_keyword_posts_input = data.get("keyword_posts", {})

    user = db.get_user_by_email("contact@gariguettes.fr")
    ig = db.get_instagram_account(user["id"]) if user else None
    access_token = ig["access_token"] if ig else None
    ig_user_id = ig["instagram_id"] if ig else None

    previous_posts = CONFIG.get("keyword_posts", {})
    resolved_posts: dict = {}
    for kw, post in new_keyword_posts_input.items():
        url = ((post.get("url") if isinstance(post, dict) else "") or "").strip()
        if not url:
            continue
        if kw not in new_keywords:
            continue
        prev = previous_posts.get(kw) or {}
        if isinstance(prev, dict) and prev.get("url") == url and prev.get("media_id"):
            resolved_posts[kw] = {"url": url, "media_id": prev["media_id"]}
            continue
        media_id = None
        if access_token and ig_user_id:
            media_id = await instagram_oauth.resolve_media_id(url, ig_user_id, access_token)
            if not media_id:
                logger.warning(f"URL admin non resolue: {url} (mot-cle {kw})")
        resolved_posts[kw] = {"url": url, "media_id": media_id}

    CONFIG["keywords"] = new_keywords
    CONFIG["replies"] = new_replies
    CONFIG["keyword_posts"] = resolved_posts
    save_config(CONFIG)
    await save_config_to_github(CONFIG)

    if user:
        kw_list = [
            {
                "keyword": kw,
                "message": msg,
                "post_url": (resolved_posts.get(kw) or {}).get("url"),
                "media_id": (resolved_posts.get(kw) or {}).get("media_id"),
            }
            for kw, msg in new_keywords.items()
        ]
        db.update_keywords(user["id"], kw_list)
        db.update_replies(user["id"], new_replies)

    return {"status": "ok", "keyword_posts": resolved_posts}


@app.put("/api/keywords")
async def update_keywords(request: Request, _=Depends(check_admin)):
    CONFIG["keywords"] = await request.json()
    save_config(CONFIG)
    return {"status": "ok"}


# ─── Webhook ───

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    if hub_mode == "subscribe" and hub_token == VERIFY_TOKEN:
        logger.info("Webhook verifie")
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Forbidden", status_code=403)


@app.post("/webhook")
async def handle_webhook(request: Request):
    body = await request.json()
    recent_events.append(body)
    if len(recent_events) > 50:
        recent_events.pop(0)
    logger.info(f"Webhook recu: {json.dumps(body, ensure_ascii=False)[:500]}")

    for entry in body.get("entry", []):
        ig_id = entry.get("id")
        ig_account = db.get_instagram_account_by_ig_id(ig_id) if ig_id else None

        for change in entry.get("changes", []):
            if change.get("field") != "comments":
                continue

            value = change.get("value", {})
            comment_id = value.get("id")
            comment_text = value.get("text", "").upper().strip()
            username = value.get("from", {}).get("username", "inconnu")

            if not comment_id or comment_id in sent_comments:
                continue

            post_media_id = str(value.get("media", {}).get("id", "")) or None

            if ig_account:
                user_id = ig_account["user_id"]
                token = ig_account["access_token"]
                kw_rows = db.get_keywords(user_id)
                reply_texts = [r["text"] for r in db.get_replies(user_id)]
                for kw in kw_rows:
                    if kw["keyword"].upper() not in comment_text:
                        continue
                    if kw["post_url"]:
                        if not kw["media_id"] or kw["media_id"] != post_media_id:
                            logger.info(f"Mot-cle {kw['keyword']} ignore: post {post_media_id} != cible {kw['media_id']}")
                            continue
                    await send_dm(comment_id, kw["message"], username, kw["keyword"], token)
                    await reply_to_comment(comment_id, username, reply_texts, token)
                    break
            else:
                keyword_posts = CONFIG.get("keyword_posts", {})
                for keyword, message in CONFIG["keywords"].items():
                    if keyword.upper() not in comment_text:
                        continue
                    kp = keyword_posts.get(keyword) or {}
                    target_media_id = kp.get("media_id") if isinstance(kp, dict) else None
                    target_url = kp.get("url") if isinstance(kp, dict) else None
                    if target_url:
                        if not target_media_id or target_media_id != post_media_id:
                            logger.info(f"Mot-cle {keyword} ignore: post {post_media_id} != cible {target_media_id}")
                            continue
                    await send_dm(comment_id, message, username, keyword, ACCESS_TOKEN)
                    await reply_to_comment(comment_id, username, CONFIG.get("replies", []), ACCESS_TOKEN)
                    break

    return {"status": "ok"}


async def send_dm(comment_id: str, message: str, username: str, keyword: str, access_token: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAPH_API}/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "recipient": {"comment_id": comment_id},
                "message": {"text": message},
            },
        )

    if resp.status_code == 200:
        sent_comments.add(comment_id)
        logger.info(f"DM envoye a @{username} (mot-cle: {keyword})")
    else:
        logger.error(f"Erreur DM @{username}: {resp.status_code} - {resp.text}")


async def reply_to_comment(comment_id: str, username: str, replies: list, access_token: str):
    if not replies:
        return
    reply_text = random.choice(replies)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAPH_API}/{comment_id}/replies",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"message": reply_text},
        )
    if resp.status_code == 200:
        logger.info(f"Reponse commentaire @{username}: {reply_text}")
    else:
        logger.error(f"Erreur reponse commentaire @{username}: {resp.status_code} - {resp.text}")
