from contextvars import ContextVar

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
trace_id_context: ContextVar[str | None] = ContextVar("trace_id", default=None)


def current_request_id() -> str | None:
    return request_id_context.get()


def current_trace_id() -> str | None:
    return trace_id_context.get()
