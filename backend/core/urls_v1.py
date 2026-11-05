from django.urls import path

from core import api

urlpatterns = [
    path("states/", api.StatesView.as_view(), name="states"),
    path("currencies/", api.CurrencyListView.as_view(), name="currencies"),
    path("companies/", api.CompanyListView.as_view(), name="companies"),
    path("companies/<int:pk>/", api.CompanyDetailView.as_view(), name="company"),
    path("companies/<int:pk>/branches/", api.BranchListView.as_view(), name="branches"),
    path("branches/<int:pk>/", api.BranchDetailView.as_view(), name="branch"),
    path(
        "companies/<int:pk>/ledger-groups/",
        api.LedgerGroupListView.as_view(),
        name="ledger-groups",
    ),
    path("ledger-groups/<int:pk>/", api.LedgerGroupDetailView.as_view(), name="ledger-group"),
    path("companies/<int:pk>/ledgers/", api.LedgerListView.as_view(), name="ledgers"),
    path("ledgers/<int:pk>/", api.LedgerDetailView.as_view(), name="ledger"),
]
