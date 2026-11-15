from django.urls import path

from posting import api

urlpatterns = [
    path("postings/", api.PostingsView.as_view(), name="postings"),
]
