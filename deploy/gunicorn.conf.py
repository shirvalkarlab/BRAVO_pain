"""No startup analysis, sync or refresh jobs; resource counts are explicit."""
import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("BRAVO_WEB_WORKERS", "4"))
worker_class = "uvicorn.workers.UvicornWorker"
timeout = int(os.environ.get("BRAVO_REQUEST_TIMEOUT", "300"))
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
capture_output = True
preload_app = False


def post_worker_init(worker):
    # Register cleanup only; source scientific warmup/refresh is not a startup job.
    from modules.DecodeCommon.parallel import stop_pool_on_signals
    stop_pool_on_signals()


def worker_exit(server, worker):
    from modules.DecodeCommon.parallel import shutdown_pool
    shutdown_pool()
