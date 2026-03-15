import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import zxingcpp
from PIL import Image

from app.services.qr_service import QRService, QRValidationError


def utcnow():
    return datetime.now(timezone.utc)


def make_qr_code(
    *,
    type="one_time",
    is_revoked=False,
    used_at=None,
    valid_from=None,
    valid_until=None,
):
    """Build a minimal qr_code-like object for testing."""
    from types import SimpleNamespace
    from app.models.qr_code import QRCodeType
    return SimpleNamespace(
        code=uuid.uuid4(),
        type=QRCodeType(type),
        is_revoked=is_revoked,
        used_at=used_at,
        valid_from=valid_from or (utcnow() - timedelta(minutes=5)),
        valid_until=valid_until or (utcnow() + timedelta(minutes=25)),
    )


def test_validate_raises_on_revoked():
    qr = make_qr_code(is_revoked=True)
    with pytest.raises(QRValidationError, match="revoked"):
        QRService.validate(qr)


def test_validate_raises_on_expired_time_bounded():
    qr = make_qr_code(
        type="time_bounded",
        valid_from=utcnow() - timedelta(hours=2),
        valid_until=utcnow() - timedelta(hours=1),
    )
    with pytest.raises(QRValidationError, match="expired"):
        QRService.validate(qr)


def test_validate_raises_on_already_used_one_time():
    qr = make_qr_code(type="one_time", used_at=utcnow() - timedelta(minutes=1))
    with pytest.raises(QRValidationError, match="already used"):
        QRService.validate(qr)


def test_validate_passes_valid_one_time():
    qr = make_qr_code(type="one_time")
    QRService.validate(qr)  # should not raise


def test_validate_passes_valid_time_bounded():
    qr = make_qr_code(type="time_bounded")
    QRService.validate(qr)  # should not raise


def test_generate_png_returns_bytes():
    code = uuid.uuid4()
    result = QRService.generate_png(code)
    assert isinstance(result, bytes)
    assert result[:4] == b'\x89PNG'  # PNG magic bytes


def test_generate_png_encodes_uuid():
    """QR image encodes raw UUID string — decoded value must match the original UUID."""
    code = uuid.uuid4()
    png_bytes = QRService.generate_png(code)
    img = Image.open(io.BytesIO(png_bytes))
    results = zxingcpp.read_barcodes(img)
    assert len(results) == 1, "Expected exactly one QR code in the generated PNG"
    assert results[0].text == str(code), "Decoded QR content must match the UUID string"
