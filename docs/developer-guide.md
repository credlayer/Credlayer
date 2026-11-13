# CredLayer Developer Guide

This guide documents the API that exists in the current `Backend/src/credlayer` implementation. It deliberately does not document roadmap or mock functionality as production features.

## Quick start

### 1. Base URL

The API is mounted under `/api/v1`.

- Local backend: `http://localhost:8000/api/v1`
- Production: use the backend URL assigned to your deployment, followed by `/api/v1`.

The repository does not currently define separate public production and sandbox API base URLs. Do not assume `credlayer.xyz` or a Vercel URL is an API host; configure the actual Railway/backend URL.

### 2. Create an API key

The current API-key creation endpoint is:

```http
POST /api/v1/api-keys
Content-Type: application/json
```

```json
{
  "owner_wallet": "YOUR_SOLANA_WALLET",
  "name": "local development",
  "permissions": {"scores:read": true}
}
```

Response secrets are shown once. Store the `data.key` value in a server-side secret manager immediately. Never put it in React, browser JavaScript, a URL, a database log, or a public repository.

> Deployment note: the API-key creation route must remain reachable without an API key. If the authentication middleware protects every `/api/v1/*` route, explicitly exempt `POST /api/v1/api-keys`; otherwise new developers cannot bootstrap credentials.

### 3. Authenticate

For protected API calls send the secret in the header:

```http
X-API-Key: sk_...
```

`Authorization: Bearer sk_...` is also accepted by the current middleware. Prefer `X-API-Key` for clarity.

### 4. First request

```bash
export CREDLAYER_BASE_URL="http://localhost:8000/api/v1"
export CREDLAYER_API_KEY="sk_replace_me"
export WALLET_ADDRESS="YOUR_SOLANA_WALLET"

curl --fail-with-body \
  -H "X-API-Key: $CREDLAYER_API_KEY" \
  "$CREDLAYER_BASE_URL/scores/$WALLET_ADDRESS"
```

A normal response is an envelope:

```json
{
  "success": true,
  "data": "WalletScore returned by the configured ML service",
  "timestamp": "<response timestamp>"
}
```

The score route fails with a service error when the ML service is unavailable or its trained artifacts are not ready. It never returns a substitute score.

## Copy-paste clients

### JavaScript/TypeScript (server-side only)

```ts
const baseUrl = process.env.CREDLAYER_BASE_URL!;
const apiKey = process.env.CREDLAYER_API_KEY!;

export async function getWalletScore(wallet: string) {
  const response = await fetch(`${baseUrl}/scores/${encodeURIComponent(wallet)}`, {
    headers: { 'X-API-Key': apiKey, Accept: 'application/json' },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.error?.message ?? `CredLayer HTTP ${response.status}`);
  return body.data;
}
```

### Python

```python
import os
import requests

base_url = os.environ["CREDLAYER_BASE_URL"]
headers = {"X-API-Key": os.environ["CREDLAYER_API_KEY"]}
wallet = os.environ["WALLET_ADDRESS"]

response = requests.get(f"{base_url}/scores/{wallet}", headers=headers, timeout=30)
body = response.json()
response.raise_for_status()
print(body["data"])
```

### Node.js serverless function

Read `CREDLAYER_API_KEY` from the platform secret store. Do not prefix it with `NEXT_PUBLIC_`, `VITE_`, or another client-exposed variable. A server-side function can call the same `fetch` example above.

### Python/FastAPI

```python
import os
import httpx
from fastapi import FastAPI, HTTPException

app = FastAPI()

@app.get("/score/{wallet}")
async def score(wallet: str):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{os.environ['CREDLAYER_BASE_URL']}/scores/{wallet}",
            headers={"X-API-Key": os.environ["CREDLAYER_API_KEY"]},
        )
    if response.is_error:
        raise HTTPException(response.status_code, response.text)
    return response.json()["data"]
```

## API reference

All responses use the envelope `{success, data, message, timestamp}` unless an exception handler returns an error envelope.

| Method | Path | Parameters/body | Current behavior |
|---|---|---|---|
| POST | `/api-keys` | `owner_wallet`, `name`, optional `permissions` | Creates a secret key; secret is returned once |
| GET | `/api-keys?owner_wallet={wallet}` | query `owner_wallet` | Lists key metadata |
| DELETE | `/api-keys/{key_id}` | path `key_id` | Sets `is_active=false` |
| GET | `/scores/{address}` | path wallet address | Gets one score; may return ML fallback |
| POST | `/scores/batch` | `{ "addresses": string[] }`, max 100 | Gets scores for multiple addresses |
| GET | `/credentials/{wallet}` | path wallet | Lists credentials |
| POST | `/credentials/verify` | `{ "credential_id": UUID }` | Sets an existing credential to pending; does not run a verifier yet |
| GET | `/connections/{wallet}` | path wallet | Gets active incoming/outgoing connections |
| GET | `/agents/{agent_id}` | path agent ID | Gets an agent |
| POST | `/agents` | `agent_id`, `owner_wallet`, `name`, `permissions` | Registers an agent |
| GET | `/agents/{agent_id}/activity?limit=100` | query `limit` | Lists agent activity |
| GET | `/activity/{wallet}?limit=100` | query `limit` | Lists activity events |
| GET | `/settings/{wallet}` | path wallet | Gets settings or defaults |
| PUT | `/settings/{wallet}` | optional `preferences`, `notifications`, `privacy` | Persists settings |
| POST | `/webhooks` | `owner_wallet`, `url`, `event_types`, optional `secret` | Stores webhook configuration |
| GET | `/webhooks?owner_wallet={wallet}` | query `owner_wallet` | Lists webhook configurations |
| DELETE | `/webhooks/{webhook_id}` | path ID | Deletes configuration |
| GET | `/developer/requests?owner_wallet={wallet}&limit=100` | query owner and limit | Lists request logs |
| GET | `/request-logs/stats/{owner_wallet}` | path wallet | Aggregates request counts |

### Batch score example

```bash
curl -X POST "$CREDLAYER_BASE_URL/scores/batch" \
  -H "X-API-Key: $CREDLAYER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"addresses":["WALLET_ONE","WALLET_TWO"]}'
```

### Error responses

| Status | Meaning |
|---:|---|
| 400 | Invalid request or invalid parameter |
| 401 | Missing, invalid, revoked, or expired API key |
| 403 | Forbidden (reserved for future permission enforcement) |
| 404 | Resource not found |
| 409 | Duplicate resource, such as an existing `agent_id` |
| 422 | Validation failure |
| 429 | Rate limited; no rate-limit implementation is currently present in the backend |
| 500 | Unexpected server error |

Example:

```json
{
  "success": false,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid API key",
    "statusCode": 401
  },
  "timestamp": "2026-01-01T00:00:00Z"
}
```

## Key management and security

- Secret keys are server credentials, not public/client keys. The current API has no public client-key type.
- Keep keys in environment secrets, AWS/GCP/Azure secret storage, Vercel/Railway secrets, or an equivalent vault.
- Never place a secret in a browser bundle, React component, `NEXT_PUBLIC_*` variable, URL query string, issue, screenshot, or log.
- The backend stores a SHA-256 digest of newly created keys and exposes only the prefix in metadata.
- Rotate by creating a replacement key, deploying it, verifying it, then revoking the old key. There is currently no dedicated atomic `/rotate` endpoint.
- Revocation is soft deletion (`is_active=false`). Existing keys created before hashed-secret validation was deployed must be regenerated.
- Permissions are stored as JSON metadata, but endpoint-level scope enforcement is not implemented yet. Do not describe scopes as an active authorization boundary.

## Webhooks

Webhook registration metadata is supported at `/webhooks`. The current backend stores URL, event types, optional secret, and active state. A delivery/dispatch worker, signature protocol, retry policy, and delivery verification endpoint are not implemented in the inspected backend. Do not rely on webhook delivery until those pieces exist.

## Troubleshooting

- `401` immediately after key creation: ensure the deployed API-key creation code hashes the actual secret, not a random unrelated value; regenerate keys after deploying the fix.
- `relation request_logs does not exist`: run `alembic upgrade head`.
- Scoring is unavailable: check ML service readiness and the deployment-specific `ML_SERVICE_URL`. No score is returned unless the configured service produces a valid model result.
- `404` on `/request-logs/stats/...`: deploy the request-log stats route and register its router in `api/router.py`.
- API key appears to work after revocation: deploy the authentication middleware and verify that the request includes the same secret; revocation is enforced server-side, not by the frontend list refresh.
- CORS/browser failures: use a server-side proxy or configure backend `CORS_ORIGINS`; never solve CORS by exposing the secret to the browser.

## What is not currently supported

The current repository does not provide a production-ready Python package, a REST-focused published SDK, atomic key rotation, enforced permissions/scopes, rate limiting, or working webhook delivery. The vendored Solana SDK is a separate on-chain reader and currently contains placeholder PDAs and mocked score decoding; it must not be presented as a verified production SDK until those placeholders are replaced.
