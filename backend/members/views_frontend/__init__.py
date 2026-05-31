# backend/members/views_frontend/__init__.py

def base_context(extra=None):
    """
    Provides common context values for all frontend views
    """
    ctx = {
        "app_name": "Members Portal",
    }
    if extra:
        ctx.update(extra)
    return ctx
