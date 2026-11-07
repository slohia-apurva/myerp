from django.db import models


class AuditEntry(models.Model):
    """One change to a master record: who made it, when, and each field's
    old and new value as people saw them on screen.

    Entries are written by `audit.recorder` and are never edited or deleted
    afterwards, so they can be trusted as the history of a record.
    """

    CREATE, UPDATE, DELETE = "create", "update", "delete"
    ACTIONS = [(CREATE, "Added"), (UPDATE, "Changed"), (DELETE, "Deleted")]

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    # The person, kept by id and by name: the name stays readable even if the
    # user's details change later. Blank user = MyERP itself (setup, imports).
    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    user_name = models.CharField(max_length=150, blank=True)
    # Blank for records that belong to the whole group (users, roles).
    company = models.ForeignKey(
        "core.Company", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    record_type = models.CharField(max_length=30)  # audit.recorder.TRACKED key
    record_id = models.PositiveBigIntegerField()
    record_name = models.CharField(max_length=200)
    action = models.CharField(max_length=10, choices=ACTIONS)
    # [{"field": "name", "label": "Name", "old": "Cash", "new": "Cash in hand"}]
    changes = models.JSONField(default=list)

    class Meta:
        ordering = ["-at", "-id"]
        indexes = [
            models.Index(fields=["record_type", "record_id"]),
            models.Index(fields=["company", "-at"]),
        ]
        verbose_name_plural = "audit entries"

    def __str__(self) -> str:
        return f"{self.get_action_display()} {self.record_type} {self.record_name}"

    def save(self, *args, **kwargs):
        if not self._state.adding and not getattr(self, "_recorder_amend", False):
            raise RuntimeError("Audit entries cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not getattr(self, "_recorder_amend", False):
            raise RuntimeError("Audit entries cannot be deleted.")
        return super().delete(*args, **kwargs)
