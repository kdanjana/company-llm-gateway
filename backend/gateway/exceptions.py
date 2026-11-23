"""One error format for every API response:

    {"error": {"code": "budget_exceeded", "message": "...", "details": {...optional...}}}
"""
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler


class GatewayError(APIException):
    """An expected gateway error with its own code and HTTP status (budget used up, model not allowed...)."""

    def __init__(self, code: str, message: str, http_status: int):
        super().__init__(detail=message, code=code)
        self.status_code = http_status
        self.error_code = code


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None  # unexpected error: Django's normal 500 handling (and the traceback in the log)

    details = None
    if isinstance(exc, GatewayError):
        code, message = exc.error_code, str(exc.detail)
    elif isinstance(exc, ValidationError):
        code, message, details = "invalid_request", "The request is not valid.", response.data
    else:
        code = getattr(exc, "default_code", "error")
        detail = getattr(exc, "detail", "")
        if isinstance(detail, dict):  # e.g. simplejwt's {"detail": "...", "code": "...", "messages": [...]}
            code = str(detail.get("code", code))
            message = str(detail.get("detail", "Request failed."))
        else:
            message = str(detail)

    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    response.data = body  # keeps the status code and headers (e.g. WWW-Authenticate on 401)
    return response
