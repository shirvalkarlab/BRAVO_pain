from types import SimpleNamespace
from unittest.mock import Mock
from django.test import SimpleTestCase
from Server.models.Participant import Participant


class ParticipantBirthdateTests(SimpleTestCase):
    def test_presentation_omits_birthdate_without_changing_stored_value(self):
        participant = SimpleNamespace(uid='synthetic-id',name='TEST01',date_of_birth=946684800,
            sex='Unknown',mrn='TEST01',diagnosis='Unknown',last_update=0,tags=Mock())
        participant.tags.all.return_value=[]
        result=Participant.get_info(participant)
        self.assertEqual(result['DOB'],0)
        self.assertEqual(participant.date_of_birth,946684800)
        self.assertEqual(result['Name'],'TEST01')
