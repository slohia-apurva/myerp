"""The columns a person has chosen for a list ("Choose Columns…", Sidharth 2026-11-24).

Each person keeps their own choice per list, so it follows them to any computer.
The screen knows which columns it can show; the server only keeps the keys in
the person's order. An empty list puts the screen back to its standard columns.
"""

import re

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from tenancy.context import tenant_atomic

KEY = re.compile(r"^[a-z0-9_-]{1,40}$")


class ListColumnsView(APIView):
    def get(self, request, key: str):
        if not KEY.match(key):
            raise ValidationError({"list": ["Unknown list."]})
        return Response({"columns": request.user.list_columns.get(key, [])})

    @tenant_atomic()
    def put(self, request, key: str):
        if not KEY.match(key):
            raise ValidationError({"list": ["Unknown list."]})
        columns = request.data.get("columns")
        if not isinstance(columns, list) or len(columns) > 60:
            raise ValidationError({"columns": ["Send the list of columns to show."]})
        if not all(isinstance(c, str) and KEY.match(c) for c in columns):
            raise ValidationError({"columns": ["Unknown column."]})
        user = request.user
        chosen = dict(user.list_columns or {})
        if columns:
            chosen[key] = list(dict.fromkeys(columns))
        else:
            chosen.pop(key, None)
        user.list_columns = chosen
        user.save(update_fields=["list_columns"])
        return Response({"columns": chosen.get(key, [])})
