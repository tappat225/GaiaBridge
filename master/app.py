"""Master application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from shared.config import MasterConfig, load_master_config
from .registry import Registry
from .broker import Broker
from .router import Router
from .api.nodes import create_routes as node_routes
from .api.tasks import create_routes as task_routes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def create_app(config: MasterConfig = None) -> Starlette:
    if config is None:
        config = load_master_config()

    registry = Registry(db_path=config.db_path)
    broker = Broker()
    router = Router(broker)

    async def health(request):
        return JSONResponse({
            "status": "ok",
            "connected_nodes": broker.connected_nodes(),
        })

    routes = [Route("/health", health, methods=["GET"])]
    routes += node_routes(registry, broker, config.node_token)
    routes += task_routes(router, registry, config.node_token, config.client_token)

    @asynccontextmanager
    async def lifespan(app):
        async def sweeper():
            while True:
                await asyncio.sleep(config.heartbeat_timeout // 2)
                registry.sweep_stale(config.heartbeat_timeout)
                await broker.broadcast_ping()

        task = asyncio.create_task(sweeper())
        logger.info("master: started on %s:%d", config.host, config.port)
        yield
        task.cancel()

    return Starlette(routes=routes, lifespan=lifespan)


if __name__ == "__main__":
    import uvicorn
    config = load_master_config()
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port)
