from app.utils.sanitize import sanitize_filename


def test_sanitize_filename_strips_unix_path_traversal() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"


def test_sanitize_filename_strips_windows_style_path() -> None:
    assert sanitize_filename("C:\\Users\\evil\\payload.png") == "payload.png"


def test_sanitize_filename_replaces_unsafe_characters() -> None:
    assert sanitize_filename("my photo!@#.png") == "my_photo___.png"


def test_sanitize_filename_falls_back_when_nothing_safe_remains() -> None:
    assert sanitize_filename("") == "upload"
    assert sanitize_filename(None) == "upload"
    assert sanitize_filename("...") == "upload"


def test_sanitize_filename_preserves_a_normal_name() -> None:
    assert sanitize_filename("aerial-photo_01.jpg") == "aerial-photo_01.jpg"
