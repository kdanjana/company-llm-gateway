"""POST /api/v1/chat - the gateway endpoint used by the departments' apps (API key login).

The logic lives in services.py; this view only checks the body and picks normal vs streaming output.
"""
from django.http import StreamingHttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .auth import ApiKeyAuthentication, HasApiKey
from .serializers import ChatRequestSerializer


class ChatView(APIView):
    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [HasApiKey]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Model check, masking and budget check. Raises GatewayError -> {"error": ...} response.
        chat_request = services.prepare(request.auth, data)

        if data["stream"]:
            # Started here (not inside the response) so a failure before the first word
            # still returns a proper HTTP error code instead of an error event.
            stream = services.open_stream(chat_request)
            response = StreamingHttpResponse(services.stream_events(chat_request, stream), content_type="text/event-stream")
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"  # tells nginx-style proxies not to hold the pieces back
            return response

        return Response(services.run_chat(chat_request))
