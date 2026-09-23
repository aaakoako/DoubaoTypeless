import json
import sqlite3
from pathlib import Path
import pytest
from doubao_typeless.storage.upgrade import prepare_upgrade


def test_upgrade_retains_wal_draft_settings_images_and_is_idempotent(tmp_path):
    settings = b'{"port":8769,"theme":"blue"}'
    (tmp_path/'settings.json').write_bytes(settings)
    for name in ('recovery','secrets','send-actions'):
        directory=tmp_path/name;directory.mkdir();(directory/'state.bin').write_bytes(b'preserve-state')
    assets=tmp_path/'assets'; assets.mkdir(); (assets/'a.bin').write_bytes(b'image')
    with sqlite3.connect(tmp_path/'v3.sqlite') as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE draft (text TEXT)')
        db.execute('INSERT INTO draft VALUES (?)', ('尚未插入的内容',)); db.commit()
        backup=prepare_upgrade(tmp_path, version='0.5.0')
        with sqlite3.connect(backup/'v3.sqlite') as copied:
            assert copied.execute('SELECT text FROM draft').fetchone()[0]=='尚未插入的内容'
    assert (backup/'settings.json').read_bytes()==settings
    for name in ('recovery','secrets','send-actions'):
        assert (backup/name/'state.bin').read_bytes()==b'preserve-state'
    assert (backup/'assets/a.bin').read_bytes()==b'image'
    (assets/'a.bin').unlink()
    assert (backup/'assets/a.bin').read_bytes()==b'image'
    assert prepare_upgrade(tmp_path,version='0.5.0') is None
    assert len(list((tmp_path/'upgrade-backups').iterdir()))==1
    assert json.loads((backup/'backup-complete.json').read_text())['to']=='0.5.0'


def test_future_schema_and_backup_failure_leave_version_marker_untouched(tmp_path, monkeypatch):
    marker=tmp_path/'workspace-version.json'
    marker.write_text('{"schema":2,"version":"0.6.0"}')
    original=marker.read_bytes()
    with pytest.raises(RuntimeError): prepare_upgrade(tmp_path,version='0.5.0')
    assert marker.read_bytes()==original
    marker.write_text('{"schema":1,"version":"0.4.9"}')
    original=marker.read_bytes()
    def fail(*a, **k): raise OSError('full disk')
    monkeypatch.setattr('doubao_typeless.storage.upgrade.shutil.copy2',fail)
    with pytest.raises(OSError): prepare_upgrade(tmp_path,version='0.5.0')
    assert marker.read_bytes()==original
    assert not list((tmp_path/'upgrade-backups').glob('*/backup-complete.json'))


def test_release_storage_does_not_depend_on_executable_location(tmp_path, monkeypatch):
    from doubao_typeless import build_info, runtime
    from doubao_typeless.ui.single_instance import pipe_name
    from doubao_typeless.ui.v3_startup import run_name
    monkeypatch.delenv('DT_V3_DATA_DIR',raising=False)
    monkeypatch.delenv('DT_V3_PIPE',raising=False)
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    monkeypatch.setattr(build_info,'release_layout',lambda:True)
    assert runtime.v3_data_dir()==tmp_path/'DoubaoTypeless/workspace-v3'
    assert pipe_name()=='DoubaoTypelessV3'
    assert run_name()=='DoubaoTypelessV3'
