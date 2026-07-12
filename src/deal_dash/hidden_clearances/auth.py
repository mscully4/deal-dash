from typing import Any

import httpx

from deal_dash.deals.environment import DealsEnvironment


_SUPABASE_URL = "https://cdqqxarqppyvctffzsax.supabase.co"
# Public anon key — ships in Hidden Clearances' own frontend bundle, not a secret.
_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNkcXF4YXJxcHB5"
    "dmN0ZmZ6c2F4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE3OTk3OTgsImV4cCI6MjA3NzM3NTc5OH0."
    "Y5-b6AJwPkyrbJTU5oRJNbwbZzKiCJTbxtrCpD71mrI"
)


async def refresh_access_token(
    env: DealsEnvironment | None = None, secrets_client: Any = None
) -> str:
    """Rotate the stored Supabase refresh token, returning a fresh access token.

    Supabase refresh tokens are single-use — the rotated token must be
    written back immediately or the next refresh will be rejected.
    """
    env = env or DealsEnvironment.from_environment()
    sm = secrets_client if secrets_client is not None else env.secrets_manager_client
    refresh_token = sm.get_secret_value(SecretId=env.hc_refresh_token_secret_id)["SecretString"]

    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{_SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
            headers={"apikey": _ANON_KEY, "content-type": "application/json"},
            json={"refresh_token": refresh_token},
        )
        resp.raise_for_status()
        data = resp.json()

    sm.put_secret_value(SecretId=env.hc_refresh_token_secret_id, SecretString=data["refresh_token"])
    return str(data["access_token"])
