from io import BytesIO

import pytest
from botocore.exceptions import ClientError

import persistence


def test_neon_urls_use_psycopg_driver():
    assert persistence._normalize_database_url(
        "postgresql://user:pass@host/db?sslmode=require"
    ) == "postgresql+psycopg://user:pass@host/db?sslmode=require"
    assert persistence._normalize_database_url(
        "postgres://user:pass@host/db"
    ) == "postgresql+psycopg://user:pass@host/db"


class FakePaginator:
    def __init__(self, client):
        self.client = client

    def paginate(self, *, Bucket: str, Prefix: str):
        matching = [
            key for key in self.client.objects
            if key.startswith(Prefix)
        ]
        return [{"Contents": [{"Key": key} for key in matching]}]


class FakeR2Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes):
        self.objects[Key] = Body

    def get_object(self, *, Bucket: str, Key: str):
        if Key not in self.objects:
            raise self._not_found()
        return {"Body": BytesIO(self.objects[Key])}

    def head_object(self, *, Bucket: str, Key: str):
        if Key not in self.objects:
            raise self._not_found()

    def get_paginator(self, operation: str):
        assert operation == "list_objects_v2"
        return FakePaginator(self)

    def delete_objects(self, *, Bucket: str, Delete: dict):
        for item in Delete["Objects"]:
            self.objects.pop(item["Key"], None)

    @staticmethod
    def _not_found() -> ClientError:
        return ClientError(
            {"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
            "GetObject",
        )


def test_local_blob_lifecycle_and_path_validation():
    assignment_id = "test-storage-roundtrip"
    relative_path = f"{assignment_id}/crops/test.png"
    persistence.write_blob(relative_path, b"png bytes")

    assert persistence.blob_exists(relative_path)
    assert persistence.read_blob(relative_path) == b"png bytes"
    persistence.delete_blobs(assignment_id)
    assert not persistence.blob_exists(relative_path)
    with pytest.raises(ValueError, match="Invalid storage path"):
        persistence.read_blob("../outside")


def test_r2_blob_lifecycle(monkeypatch):
    client = FakeR2Client()
    monkeypatch.setattr(persistence, "STORAGE_BACKEND", "r2")
    monkeypatch.setattr(persistence, "_r2_client", client)
    monkeypatch.setattr(persistence, "_r2_bucket", "test-bucket")
    relative_path = "test-r2-assignment/sources/test.pdf"

    persistence.write_blob(relative_path, b"pdf bytes")
    assert persistence.blob_exists(relative_path)
    assert persistence.read_blob(relative_path) == b"pdf bytes"
    with pytest.raises(FileNotFoundError):
        persistence.read_blob("test-r2-assignment/sources/missing.pdf")
    persistence.delete_blobs("test-r2-assignment")
    assert not persistence.blob_exists(relative_path)
