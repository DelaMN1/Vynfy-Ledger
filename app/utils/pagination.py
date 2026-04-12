from __future__ import annotations

from flask import current_app, request


def current_page() -> int:
    try:
        return max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        return 1


def page_size() -> int:
    try:
        return max(int(request.args.get("per_page", current_app.config["DEFAULT_PAGE_SIZE"])), 1)
    except (TypeError, ValueError):
        return current_app.config["DEFAULT_PAGE_SIZE"]
