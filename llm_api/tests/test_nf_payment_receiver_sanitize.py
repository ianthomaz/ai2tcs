"""payment_receiver must not be the NFS-e tomador / Bike Anjo."""
from app.nfextract.parser import _sanitize_payment_receiver_not_tomador, apply_nf_extract_postprocess


def test_clears_bike_anjo_as_receiver():
    base = {
        "supplier_code": "65998990000144",
        "service_recipient_code": "19515100000189",
        "payment_receiver_name": "ASSOCIACAO BIKE ANJO",
        "payment_receiver_document": "19515100000189",
        "nf_number": "5",
    }
    warnings: list[str] = []
    _sanitize_payment_receiver_not_tomador(base, warnings)
    assert base["payment_receiver_name"] is None
    assert base["payment_receiver_document"] is None
    assert warnings


def test_keeps_supplier_as_receiver():
    base = {
        "supplier_code": "65998990000144",
        "service_recipient_code": "19515100000189",
        "payment_receiver_name": "ITCS WEBPLACE LTDA",
        "payment_receiver_document": "65998990000144",
    }
    warnings: list[str] = []
    _sanitize_payment_receiver_not_tomador(base, warnings)
    assert base["payment_receiver_document"] == "65998990000144"
    assert not warnings
