from contextvars import ContextVar


_request_id_var = ContextVar("request_id", default="-")


def get_request_id():
    return _request_id_var.get()


def set_request_id(value):
    return _request_id_var.set(str(value or "-"))


def reset_request_id(token):
    _request_id_var.reset(token)
