from audit import recorder


class AuditMiddleware:
    """Opens an audit scope for each request, so the log knows who made each
    change and merges a screen's saves into one entry per record. Sits below
    the authentication middleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with recorder.scope(user=getattr(request, "user", None)):
            return self.get_response(request)
