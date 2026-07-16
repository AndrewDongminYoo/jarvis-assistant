import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402


@pytest.mark.parametrize(
    ("cert_exists", "key_exists", "expected_tls"),
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (True, True, True),
    ],
)
def test_ssl_file_args_require_complete_pair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cert_exists: bool,
    key_exists: bool,
    expected_tls: bool,
) -> None:
    # Given
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    if cert_exists:
        cert.touch()
    if key_exists:
        key.touch()
    monkeypatch.setattr(server, "SSL_CERT", cert)
    monkeypatch.setattr(server, "SSL_KEY", key)

    # When
    actual = server._ssl_file_args()

    # Then
    expected = (str(cert), str(key)) if expected_tls else (None, None)
    assert actual == expected  # nosec B101
