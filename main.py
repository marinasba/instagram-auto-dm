import os
import json
import logging
import httpx
from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("insta-dm")

with open("config.json") as f:
    CONFIG = json.load(f)

VERIFY_TOKEN = os.environ["VERIFY_TOKEN"]
ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
GRAPH_API = "https://graph.instagram.com/v21.0"

# Évite les doublons (un DM par commentaire max)
sent_comments: set[str] = set()


@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    """Meta envoie un GET pour vérifier le webhook."""
    if hub_mode == "subscribe" and hub_token == VERIFY_TOKEN:
        logger.info("Webhook verifie")
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Forbidden", status_code=403)


@app.post("/webhook")
async def handle_webhook(request: Request):
    """Reçoit les notifications de commentaires Instagram."""
    body = await request.json()

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "comments":
                continue

            value = change.get("value", {})
            comment_id = value.get("id")
            comment_text = value.get("text", "").upper().strip()
            username = value.get("from", {}).get("username", "inconnu")

            if not comment_id or comment_id in sent_comments:
                continue

            for keyword, message in CONFIG["keywords"].items():
                if keyword.upper() in comment_text:
                    await send_dm(comment_id, message, username, keyword)
                    break

    return {"status": "ok"}


async def send_dm(comment_id: str, message: str, username: str, keyword: str):
    """Envoie un DM via l'API Instagram en réponse à un commentaire."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAPH_API}/me/messages",
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
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
