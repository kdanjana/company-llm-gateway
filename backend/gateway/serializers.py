"""Checks the request body of POST /api/v1/chat before anything else happens (no model call for bad input)."""
from django.conf import settings
from rest_framework import serializers


class MessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(max_length=200_000, trim_whitespace=False)


class ChatRequestSerializer(serializers.Serializer):
    model = serializers.CharField(max_length=200)
    messages = MessageSerializer(many=True, allow_empty=False)
    system = serializers.CharField(required=False, allow_blank=True, max_length=50_000, trim_whitespace=False)
    max_tokens = serializers.IntegerField(min_value=1, max_value=settings.GATEWAY_MAX_TOKENS, default=1024)
    stream = serializers.BooleanField(default=False, help_text="Send the answer piece by piece (Server-Sent Events).")
    cache = serializers.BooleanField(default=True, help_text="Allow a saved answer for an identical request.")

    def validate_messages(self, messages):
        # Same rules Bedrock enforces, checked here so bad requests fail fast and cost nothing.
        if len(messages) > 100:
            raise serializers.ValidationError("At most 100 messages per request.")
        if messages[0]["role"] != "user" or messages[-1]["role"] != "user":
            raise serializers.ValidationError("The first and the last message must have role 'user'.")
        for previous, current in zip(messages, messages[1:]):
            if previous["role"] == current["role"]:
                raise serializers.ValidationError("Roles must alternate between 'user' and 'assistant'.")
        return messages
