from rest_framework import serializers

from .models import Activity, OutboundEmail


class ActivitySerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.name", read_only=True, default=None)

    class Meta:
        model = Activity
        fields = ["id", "entity", "entity_id", "verb", "message", "actor_name", "created_at"]


class OutboundEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutboundEmail
        fields = [
            "id",
            "to",
            "subject",
            "body",
            "html",
            "attachments",
            "category",
            "status",
            "error",
            "created_at",
        ]
