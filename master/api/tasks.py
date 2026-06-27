"""Task dispatch and result API endpoints."""

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from shared.protocol import Task, TaskPayload, TaskResult, TaskStatus
from master.auth import require_client_token, require_node_token


def create_routes(router, registry, node_token: str, client_token: str) -> list[Route]:

    async def dispatch(request: Request):
        err = await require_client_token(request, client_token)
        if err:
            return err
        body = await request.json()
        task = Task(
            target_node=body["target_node"],
            payload=TaskPayload(**body["payload"]),
            timeout=body.get("timeout", 120))
        sent = await router.dispatch(task)
        if not sent:
            return JSONResponse(
                {"error": "node offline or not connected", "task_id": task.task_id},
                status_code=503)
        return JSONResponse({"task_id": task.task_id, "status": "dispatched"})

    async def dispatch_sync(request: Request):
        err = await require_client_token(request, client_token)
        if err:
            return err
        body = await request.json()
        task = Task(
            target_node=body["target_node"],
            payload=TaskPayload(**body["payload"]),
            timeout=body.get("timeout", 120))
        sent = await router.dispatch(task)
        if not sent:
            return JSONResponse(
                {"error": "node offline or not connected"}, status_code=503)
        result = await router.wait_result(task.task_id, timeout=task.timeout)
        if result:
            return JSONResponse(result.model_dump(mode="json"))
        return JSONResponse({"error": "timeout"}, status_code=504)

    async def report_result(request: Request):
        err = await require_node_token(request, node_token)
        if err:
            return err
        body = await request.json()
        result = TaskResult(**body)
        router.submit_result(result)
        return JSONResponse({"status": "ok"})

    async def get_result(request: Request):
        task_id = request.path_params["task_id"]
        result = router.get_result(task_id)
        if not result:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(result.model_dump(mode="json"))

    return [
        Route("/api/tasks/dispatch", dispatch, methods=["POST"]),
        Route("/api/tasks/dispatch_sync", dispatch_sync, methods=["POST"]),
        Route("/api/tasks/result", report_result, methods=["POST"]),
        Route("/api/tasks/{task_id}", get_result, methods=["GET"]),
    ]
