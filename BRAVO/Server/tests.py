import json
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from modules.HelperFunctions import PermissionDefinitions
from Server.APIs.Auth import UserRegister
from Server.APIs.Participants import QueryParticipantInformation
from Server.APIs.RCS08Sync import RCS08SyncHandler
from Server.Middlewares.ReadOnlyAccount import ReadOnlyAccountMiddleware
from modules import RCS08ManualSync


class ClosedRegistrationTests(SimpleTestCase):
    @override_settings(ALLOW_SELF_REGISTRATION=False)
    def test_registration_endpoint_is_disabled(self):
        request = APIRequestFactory().post(
            "/api/register",
            {
                "Email": "new@example.com",
                "Password": "not-a-real-password",
                "UserName": "New User",
                "Institute": "",
            },
            format="json",
        )

        response = UserRegister.as_view()(request)

        self.assertEqual(response.status_code, 403)


class ViewerPermissionTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = ReadOnlyAccountMiddleware(
            lambda request: JsonResponse({"ok": True})
        )
        self.viewer = SimpleNamespace(
            is_authenticated=True, configuration={"ReadOnly": True}
        )
        self.admin = SimpleNamespace(is_authenticated=True, configuration={})

    def post(self, path, payload, user=None):
        request = self.factory.post(
            path, data=json.dumps(payload), content_type="application/json"
        )
        request.user = user or self.viewer
        return self.middleware(request)

    def test_viewer_role_has_no_shared_data_write_permissions(self):
        self.assertEqual(
            PermissionDefinitions["Viewer"],
            {"AddEvent": False, "Edit": False, "Upload": False, "Delete": False},
        )

    def test_viewer_can_query_participants(self):
        response = self.post("/api/queryParticipants", {})
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_upload(self):
        response = self.post("/api/uploadData", {})
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_trigger_rcs08_sync(self):
        response = self.post("/api/syncRCS08", {"RequestType": "Start"})
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_create_update_or_delete_participants(self):
        for path in (
            "/api/createParticipantInformation",
            "/api/updateParticipantInformation",
            "/api/deleteParticipantInformation",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.post(path, {}).status_code, 403)

    def test_viewer_cannot_update_processing_configuration(self):
        response = self.post(
            "/api/queryAnalysisConfigurations",
            {"RequestType": "UpdateConfigurations", "Configurations": {}},
        )
        self.assertEqual(response.status_code, 403)

    def test_viewer_can_list_but_not_delete_source_files(self):
        allowed = self.post("/api/querySourceFiles", {"RequestType": "All"})
        denied = self.post("/api/querySourceFiles", {"RequestType": "Delete"})
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(denied.status_code, 403)

    def test_viewer_can_read_but_not_refresh_wearable_data(self):
        allowed = self.post(
            "/api/queryOuraRingData", {"RequestType": "RequestOverview"}
        )
        denied = self.post(
            "/api/queryOuraRingData", {"RequestType": "RefreshOuraRingData"}
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(denied.status_code, 403)

    def test_viewer_cannot_schedule_group_analysis_refresh(self):
        response = self.post(
            "/api/queryGroupAnalysis", {"RequestType": "RequestRefresh"}
        )
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_download_exports(self):
        request = self.factory.get("/api/downloadParticipantExport")
        request.user = self.viewer
        response = self.middleware(request)
        self.assertEqual(response.status_code, 403)

    def test_admin_is_not_restricted(self):
        response = self.post("/api/uploadData", {}, user=self.admin)
        self.assertEqual(response.status_code, 200)


class ParticipantLookupTests(SimpleTestCase):
    def test_stale_participant_identifier_returns_not_found(self):
        request = APIRequestFactory().post(
            "/api/queryParticipantInformation",
            {"ParticipantId": "stale-participant-id"},
            format="json",
        )
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_active=True,
            configuration={},
        )

        with mock.patch("Server.APIs.Participants.models.Participant.find", return_value=None):
            response = QueryParticipantInformation.as_view()(request)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.data["message"],
            "This participant is no longer in the database.",
        )


class ManualRCS08SyncAPITests(SimpleTestCase):
    def setUp(self):
        self.freshness_patch = mock.patch("Server.APIs.RCS08Sync.RCS08DataFreshness.for_institute",
                                         return_value={"redcap": {"available": False}})
        self.freshness = self.freshness_patch.start()
        self.addCleanup(self.freshness_patch.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.storage_patch = mock.patch.object(
            RCS08ManualSync, "STORAGE_PATH", Path(self.temporary.name)
        )
        self.storage_patch.start()
        institute = SimpleNamespace(has_permission=lambda user, permit: permit == "Upload")
        self.admin = SimpleNamespace(
            is_authenticated=True,
            is_active=True,
            uid="admin-user",
            institute=institute,
        )
        self.factory = APIRequestFactory()

    def tearDown(self):
        self.storage_patch.stop()
        self.temporary.cleanup()

    def post(self, request_type):
        request = self.factory.post(
            "/api/syncRCS08", {"RequestType": request_type}, format="json"
        )
        request.user = self.admin
        return RCS08SyncHandler.as_view()(request)

    def test_admin_can_queue_and_query_manual_sync(self):
        queued = self.post("Start")
        status = self.post("Status")
        self.assertEqual(queued.status_code, 202)
        self.assertEqual(queued.data["status"], "queued")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.data["request_id"], queued.data["request_id"])
        self.assertNotIn("requested_by", status.data)
        self.assertEqual(status.data["data_freshness"], {"redcap": {"available": False}})
        self.freshness.assert_called_once_with(self.admin.institute)

    def test_second_active_request_is_rejected(self):
        self.post("Start")
        duplicate = self.post("Start")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.data["status"], "queued")

    def test_status_permission_and_malformed_requests_never_load_freshness(self):
        self.assertEqual(self.post("invalid").status_code, 400)
        self.admin.institute = None
        self.assertEqual(self.post("Status").status_code, 403)
        self.admin.institute = SimpleNamespace(has_permission=lambda user, permit: False)
        self.assertEqual(self.post("Status").status_code, 403)
        self.freshness.assert_not_called()
