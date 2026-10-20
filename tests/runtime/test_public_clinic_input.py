"""The public CLI cannot silently select an installation-specific workbook folder."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock
import pytest
from django.core.management.base import CommandError

@pytest.fixture
def command(monkeypatch):
    server=ModuleType('Server');server.models=SimpleNamespace(Participant=SimpleNamespace(find=Mock()))
    optimizer=ModuleType('modules.StimOptimizer');optimizer.clinic_pain=SimpleNamespace(ingest_and_store=Mock())
    monkeypatch.setitem(sys.modules,'Server',server)
    monkeypatch.setitem(sys.modules,'modules.StimOptimizer',optimizer)
    path=Path(__file__).resolve().parents[2]/'BRAVO/Server/management/commands/ingest_clinic_sheets.py'
    spec=importlib.util.spec_from_file_location('public_clinic_command',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod.Command(),server.models.Participant.find,optimizer.clinic_pain.ingest_and_store

def test_cli_requires_explicit_folder(command):
    cmd,lookup,ingest=command
    parser=cmd.create_parser('manage.py','ingest_clinic_sheets')
    with pytest.raises(CommandError,match='--folder'):
        parser.parse_args(['--participant','synthetic'])
    lookup.assert_not_called();ingest.assert_not_called()

@pytest.mark.parametrize('folder',[None,'/nonexistent-synthetic-workbook-directory'])
def test_programmatic_missing_folder_fails_before_data_access(command,folder):
    cmd,lookup,ingest=command
    with pytest.raises(CommandError,match='existing workbook directory'):
        cmd.handle(participant='synthetic',folder=folder)
    lookup.assert_not_called();ingest.assert_not_called()

def test_parser_retains_explicit_private_folder(command,tmp_path):
    cmd,_,_=command
    opts=cmd.create_parser('manage.py','ingest_clinic_sheets').parse_args(['--participant','synthetic','--folder',str(tmp_path)])
    assert opts.participant=='synthetic' and opts.folder==str(tmp_path)
