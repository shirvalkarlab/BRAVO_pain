from types import SimpleNamespace
from unittest.mock import patch, Mock
from django.test import SimpleTestCase, RequestFactory
from rest_framework.exceptions import PermissionDenied
from Server.authentication import BRAVOAPIAuthentication, ReadOnlyBasicAuthentication


class ViewerAuthenticationTests(SimpleTestCase):
    def setUp(self):
        self.factory=RequestFactory()
        self.viewer=SimpleNamespace(is_authenticated=True,configuration={'ReadOnly':True})
        self.admin=SimpleNamespace(is_authenticated=True,configuration={})

    def test_api_key_cannot_bypass_viewer_source_download_denial(self):
        request=self.factory.get('/api/querySourceFiles',HTTP_X_SECURE_API_KEY='synthetic-key')
        with patch('Server.authentication.models.PlatformUser.find',return_value=self.viewer):
            with self.assertRaises(PermissionDenied):BRAVOAPIAuthentication().authenticate(request)

    def test_api_key_viewer_can_still_read_data(self):
        request=self.factory.post('/api/queryParticipants',data='{}',content_type='application/json',HTTP_X_SECURE_API_KEY='synthetic-key')
        with patch('Server.authentication.models.PlatformUser.find',return_value=self.viewer):
            self.assertIs(BRAVOAPIAuthentication().authenticate(request)[0],self.viewer)

    def test_desktop_token_cannot_bypass_viewer_upload_denial(self):
        request=self.factory.post('/api/uploadData',HTTP_X_SECURE_AUTH_TOKEN='synthetic-token')
        with patch('Server.authentication.models.AuthenticationTokens.objects.filter') as query:
            query.return_value.first.return_value=SimpleNamespace(user=self.viewer)
            with self.assertRaises(PermissionDenied):BRAVOAPIAuthentication().authenticate(request)

    def test_basic_auth_cannot_bypass_viewer_sync_denial(self):
        request=self.factory.post('/api/syncRCS08',data='{"RequestType":"Start"}',content_type='application/json')
        with patch('rest_framework.authentication.BasicAuthentication.authenticate',return_value=(self.viewer,None)):
            with self.assertRaises(PermissionDenied):ReadOnlyBasicAuthentication().authenticate(request)

    def test_admin_authentication_is_not_downgraded(self):
        request=self.factory.get('/api/querySourceFiles',HTTP_X_SECURE_API_KEY='synthetic-key')
        with patch('Server.authentication.models.PlatformUser.find',return_value=self.admin):
            self.assertIs(BRAVOAPIAuthentication().authenticate(request)[0],self.admin)
