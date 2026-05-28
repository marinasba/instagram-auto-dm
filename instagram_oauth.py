import os
import httpx

META_APP_ID = os.environ.get("META_APP_ID", "1445863310917375")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
REDIRECT_URI = os.environ.get("REDIRECT_URI", "")

AUTH_URL = "https://www.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
GRAPH_URL = "https://graph.instagram.com"


def get_authorize_url(state: str = "") -> str:
    return (
        f"{AUTH_URL}"
        f"?client_id={META_APP_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments"
        f"&response_type=code"
        f"&state={state}"
    )


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data={
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code": code,
        })
    if resp.status_code != 200:
        return {"error": resp.text}
    return resp.json()


async def get_long_lived_token(short_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{GRAPH_URL}/access_token", params={
            "grant_type": "ig_exchange_token",
            "client_secret": META_APP_SECRET,
            "access_token": short_token,
        })
    if resp.status_code != 200:
        return {"error": resp.text}
    return resp.json()


async def get_profile(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{GRAPH_URL}/v21.0/me", params={
            "fields": "id,username",
            "access_token": access_token,
        })
    if resp.status_code != 200:
        return {"error": resp.text}
    return resp.json()
