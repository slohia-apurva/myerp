from django.db import models


class Company(models.Model):
    """A legal entity inside a tenant, e.g. Apurvam Organics LLP.

    Phase 0 keeps only what the tenancy tests need; Module 1 adds GSTIN
    validation, PAN, addresses, fiscal year start and the rest.
    """

    name = models.CharField(max_length=200, unique=True)
    gstin = models.CharField(max_length=15, blank=True)
    state_code = models.CharField(max_length=2, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self) -> str:
        return self.name
