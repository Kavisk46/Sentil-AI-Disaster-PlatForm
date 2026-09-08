"""Tests for `LocalFileStorage`/`LocalObjectStorage` (Milestone F5 adds
`exists`/`delete` to the pre-existing `save`/`load` — see
`app/services/file_storage.py`)."""

import pytest

from app.services.file_storage import LocalFileStorage, LocalObjectStorage


def test_local_object_storage_is_the_same_class_as_local_file_storage() -> None:
    assert LocalObjectStorage is LocalFileStorage


def test_save_then_load_round_trips(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalFileStorage(base_dir=tmp_path)

    storage.save(storage_name="a.png", content=b"hello")

    assert storage.load(storage_name="a.png") == b"hello"


def test_load_missing_file_raises_file_not_found(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalFileStorage(base_dir=tmp_path)

    with pytest.raises(FileNotFoundError):
        storage.load(storage_name="missing.png")


def test_exists_is_false_before_save_and_true_after(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalFileStorage(base_dir=tmp_path)

    assert storage.exists(storage_name="a.png") is False

    storage.save(storage_name="a.png", content=b"hello")

    assert storage.exists(storage_name="a.png") is True


def test_delete_removes_the_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalFileStorage(base_dir=tmp_path)
    storage.save(storage_name="a.png", content=b"hello")

    storage.delete(storage_name="a.png")

    assert storage.exists(storage_name="a.png") is False


def test_delete_of_a_missing_file_is_a_no_op_not_an_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalFileStorage(base_dir=tmp_path)

    storage.delete(storage_name="never-existed.png")  # must not raise


def test_save_rejects_a_storage_name_that_is_not_a_single_path_segment(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalFileStorage(base_dir=tmp_path)

    with pytest.raises(ValueError, match="single path segment"):
        storage.save(storage_name="../escape.png", content=b"malicious")


def test_load_rejects_path_traversal_attempts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalFileStorage(base_dir=tmp_path)

    with pytest.raises(ValueError, match="single path segment"):
        storage.load(storage_name="../../etc/passwd")


def test_exists_rejects_path_traversal_attempts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalFileStorage(base_dir=tmp_path)

    with pytest.raises(ValueError, match="single path segment"):
        storage.exists(storage_name="../escape.png")


def test_delete_rejects_path_traversal_attempts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalFileStorage(base_dir=tmp_path)

    with pytest.raises(ValueError, match="single path segment"):
        storage.delete(storage_name="../escape.png")
