"""Authenticated API for queuing and monitoring a manual RCS08 data sync."""

import rest_framework.parsers as RestParsers
import rest_framework.views as RestViews
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from modules import RCS08ManualSync, RCS08DataFreshness


class RCS08SyncHandler(RestViews.APIView):
    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        institute = request.user.institute
        if not institute or not institute.has_permission(request.user, "Upload"):
            return Response(status=403, data={"message": "Permission denied."})

        request_type = request.data.get("RequestType")
        if request_type == "Start":
            try:
                state = RCS08ManualSync.queue_request(str(request.user.uid))
            except RCS08ManualSync.ManualSyncAlreadyActive as exc:
                return Response(
                    status=409,
                    data={"message": str(exc), **exc.state},
                )
            return Response(status=202, data=state)

        if request_type == "Status":
            return Response(status=200, data={**RCS08ManualSync.get_state(),
                "data_freshness": RCS08DataFreshness.for_institute(institute)})

        return Response(status=400, data={"message": "Malformed input."})
