from django.urls import path

from posting import api, reports

urlpatterns = [
    path("postings/", api.PostingsView.as_view(), name="postings"),
    path("companies/<int:pk>/ask-ledgers/", api.AskLedgersView.as_view(), name="ask-ledgers"),
    path("bins/<int:pk>/", api.BinContentsView.as_view(), name="bin-contents"),
    path(
        "companies/<int:pk>/stock-summary/",
        reports.StockSummaryView.as_view(),
        name="stock-summary",
    ),
    path(
        "companies/<int:pk>/stock-ledger/",
        reports.StockLedgerView.as_view(),
        name="stock-ledger",
    ),
]
