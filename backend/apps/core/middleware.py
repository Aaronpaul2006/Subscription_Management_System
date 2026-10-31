import time

from django.db import connection


class ServerTimingMiddleware:
    """Adds ``Server-Timing`` and ``X-Response-Time`` headers to API responses.

    The web app shows the time in its footer, so the "every page under two
    seconds" requirement is visible on every screen, not just claimed.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        queries_before = len(connection.queries) if connection.queries_log else 0
        response = self.get_response(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if request.path.startswith("/api/"):
            response["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
            response["X-Response-Time"] = f"{elapsed_ms:.1f}ms"
            if connection.queries_log:
                response["X-Query-Count"] = str(len(connection.queries) - queries_before)
            response["Access-Control-Expose-Headers"] = "Server-Timing, X-Response-Time"
        return response
