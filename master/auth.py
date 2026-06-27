"""Authentication middleware for Master API."""

from starlette.requests import Request
from starlette.responses import JSONResponse


def get_bearer_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return ""


async def require_node_token(request: Request, node_token: str):
    """Verify node token for worker endpoints."""
    token = get_bearer_token(request)
    if token != node_token:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


async def require_client_token(request: Request, client_token: str):
    """Verify client token for task dispatch endpoints."""
    token = get_bearer_token(request)
    if token != client_token:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None
