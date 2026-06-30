"""Node management API endpoints."""

import asyncio
import json

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from sse_starlette.sse import EventSourceResponse

from shared.protocol import NodeRegisterRequest
from master.auth import require_node_token


def create_routes(registry, broker, node_token: str) -> list[Route]:

    async def register(request: Request):
        err = await require_node_token(request, node_token)
        if err:
            return err
        body = await request.json()
        req = NodeRegisterRequest(**body)
        node = registry.register(
            node_id=req.node_id, hostname=req.hostname,
            os_name=req.os, mode=req.mode, capabilities=req.capabilities,
            workspace=req.workspace)
        return JSONResponse(node.model_dump(mode="json"))

    async def heartbeat(request: Request):
        err = await require_node_token(request, node_token)
        if err:
            return err
        body = await request.json()
        node_id = body.get("node_id", "")
        if registry.heartbeat(node_id):
            return JSONResponse({"status": "ok"})
        return JSONResponse({"error": "node not found"}, status_code=404)

    async def list_nodes(request: Request):
        nodes = registry.list_all()
        return JSONResponse([n.model_dump(mode="json") for n in nodes])

    async def events(request: Request):
        err = await require_node_token(request, node_token)
        if err:
            return err
        node_id = request.query_params.get("node_id", "")
        if not node_id:
            return JSONResponse({"error": "node_id required"}, status_code=400)

        queue = broker.connect(node_id)
        registry.heartbeat(node_id)

        async def event_generator():
            try:
                while True:
                    try:
                        msg = await asyncio.wait_for(queue.get(), timeout=30)
                        yield {"event": msg["event"], "data": json.dumps(msg["data"])}
                    except asyncio.TimeoutError:
                        yield {"event": "ping", "data": ""}
                        registry.heartbeat(node_id)
            except asyncio.CancelledError:
                pass
            finally:
                broker.disconnect(node_id)
                registry.mark_offline(node_id)

        return EventSourceResponse(event_generator())

    return [
        Route("/api/nodes/register", register, methods=["POST"]),
        Route("/api/nodes/heartbeat", heartbeat, methods=["POST"]),
        Route("/api/nodes", list_nodes, methods=["GET"]),
        Route("/api/events", events, methods=["GET"]),
    ]
