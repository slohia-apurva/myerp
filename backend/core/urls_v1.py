from django.urls import path

from core import api, credit_terms

urlpatterns = [
    path("states/", api.StatesView.as_view(), name="states"),
    path("modules/", api.ModulesView.as_view(), name="modules"),
    path("currencies/", api.CurrencyListView.as_view(), name="currencies"),
    path("people/", api.PeopleView.as_view(), name="people"),
    path("parties/", api.PartyListView.as_view(), name="parties"),
    path(
        "credit-terms/",
        credit_terms.CreditTermListView.as_view(),
        name="credit_terms",
    ),
    path("credit-terms/<int:pk>/", credit_terms.CreditTermDetailView.as_view(), name="credit_term"),
    path("companies/", api.CompanyListView.as_view(), name="companies"),
    path("companies/<int:pk>/", api.CompanyDetailView.as_view(), name="company"),
    path("companies/<int:pk>/branches/", api.BranchListView.as_view(), name="branches"),
    path("branches/<int:pk>/", api.BranchDetailView.as_view(), name="branch"),
    path(
        "companies/<int:pk>/certificates/", api.CertificateListView.as_view(), name="certificates"
    ),
    path("certificates/<int:pk>/", api.CertificateDetailView.as_view(), name="certificate"),
    path(
        "companies/<int:pk>/ledger-groups/",
        api.LedgerGroupListView.as_view(),
        name="ledger-groups",
    ),
    path("ledger-groups/<int:pk>/", api.LedgerGroupDetailView.as_view(), name="ledger-group"),
    path("companies/<int:pk>/ledgers/", api.LedgerListView.as_view(), name="ledgers"),
    path("ledgers/<int:pk>/", api.LedgerDetailView.as_view(), name="ledger"),
]
