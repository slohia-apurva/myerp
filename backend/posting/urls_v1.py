from django.urls import path

from posting import api

urlpatterns = [
    path("postings/", api.PostingsView.as_view(), name="postings"),
    path("companies/<int:pk>/ask-ledgers/", api.AskLedgersView.as_view(), name="ask-ledgers"),
    path("bins/<int:pk>/", api.BinContentsView.as_view(), name="bin-contents"),
]
