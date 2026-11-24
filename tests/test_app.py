import pytest
from types import SimpleNamespace

from app import main
from app.ocr import normalize_date


def test_normalize_date_iso():
    assert str(normalize_date("2026-11-21")) == "2026-11-21"


def test_normalize_date_indian_format():
    assert str(normalize_date("21 Nov 2026")) == "2026-11-21"


def test_normalize_date_rejects_unknown():
    assert normalize_date("not a date") is None


def test_delete_chit_deletes_owned_chit_and_redirects(monkeypatch):
    user = SimpleNamespace(id="owner-id")
    chit = SimpleNamespace(id="chit-id")

    class FakeDatabase:
        deleted = None
        committed = False

        def delete(self, value):
            self.deleted = value

        def commit(self):
            self.committed = True

    database = FakeDatabase()
    ownership_check = {}

    monkeypatch.setattr(main, "require_user", lambda request, db: user)

    def get_owned_chit(db, chit_id, actual_user):
        ownership_check.update(chit_id=chit_id, user=actual_user)
        return chit

    monkeypatch.setattr(main, "get_owned_chit", get_owned_chit)

    response = main.delete_chit(None, "chit-id", database)

    assert ownership_check == {"chit_id": "chit-id", "user": user}
    assert database.deleted is chit
    assert database.committed
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
