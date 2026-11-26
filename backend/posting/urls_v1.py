from django.urls import path

from posting import api, books, connections, reports, trace

urlpatterns = [
    path("postings/", api.PostingsView.as_view(), name="postings"),
    path("companies/<int:pk>/ask-ledgers/", api.AskLedgersView.as_view(), name="ask-ledgers"),
    path("batches/<int:pk>/trace/", trace.BatchTraceView.as_view(), name="batch-trace"),
    path(
        "companies/<int:pk>/connections/<str:kind>/<int:entry>/",
        connections.ConnectionsView.as_view(),
        name="connections",
    ),
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
    path(
        "companies/<int:pk>/item-stock/",
        reports.ItemStockView.as_view(),
        name="item-stock",
    ),
    path(
        "companies/<int:pk>/trial-balance/",
        books.TrialBalanceView.as_view(),
        name="trial-balance",
    ),
    path(
        "companies/<int:pk>/ledger-statement/",
        books.LedgerStatementView.as_view(),
        name="ledger-statement",
    ),
]
