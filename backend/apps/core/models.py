from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class Sequence(models.Model):
    """Gap-free document numbering (SUB/00001, INV/2026/00001).

    Numbers are taken under a row lock, so two concurrent billing runs can never
    hand out the same number. Never use MAX()+1.
    """

    code = models.CharField(max_length=40, unique=True)
    prefix = models.CharField(max_length=20)
    padding = models.PositiveSmallIntegerField(default=5)
    next_number = models.PositiveIntegerField(default=1)

    def __str__(self) -> str:
        return f"{self.code} → {self.prefix}{self.next_number}"

    @classmethod
    def next(cls, code: str, prefix: str, padding: int = 5) -> str:
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(
                code=code, defaults={"prefix": prefix, "padding": padding}
            )
            number = seq.next_number
            seq.next_number = number + 1
            seq.save(update_fields=["next_number"])
        return f"{seq.prefix}{number:0{seq.padding}d}"


class Activity(models.Model):
    """Audit trail: who did what to which record, shown as timelines in the UI."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    entity = models.CharField(max_length=40)  # "subscription", "invoice", ...
    entity_id = models.PositiveBigIntegerField()
    verb = models.CharField(max_length=40)  # "created", "confirmed", "paid", ...
    message = models.CharField(max_length=300)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["entity", "entity_id", "-created_at"])]

    def __str__(self) -> str:
        return self.message


class OutboundEmail(models.Model):
    """Every email the platform sends, kept for audit and for the admin Outbox."""

    to = models.CharField(max_length=500)
    subject = models.CharField(max_length=300)
    body = models.TextField()
    html = models.TextField(blank=True)
    attachments = models.JSONField(default=list, blank=True)  # file names only
    category = models.CharField(max_length=40, blank=True, db_index=True)
    status = models.CharField(max_length=20, default="sent")
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.subject} → {self.to}"


def log_activity(entity: str, entity_id: int, verb: str, message: str, actor=None, **data):
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    return Activity.objects.create(
        entity=entity, entity_id=entity_id, verb=verb, message=message, actor=actor, data=data
    )
