"""Batch-processing error presentation regressions."""

import pytest

from videocaptioner.ui.view import batch_process_interface


@pytest.fixture(autouse=True)
def use_qapp():
    """This unit only checks formatting and does not instantiate Qt widgets."""
    yield


def test_batch_error_status_exposes_actionable_reason():
    formatted = batch_process_interface._format_batch_error_status(
        "Bcut upstream throttled result polling with HTTP 412"
    )

    assert formatted.startswith("失败")
    assert "HTTP 412" in formatted
    assert len(formatted) <= 72


def test_batch_error_status_compacts_multiline_errors():
    formatted = batch_process_interface._format_batch_error_status(
        "JianYing signing service is throttled\nwith HTTP 429; retry later"
    )

    assert "\n" not in formatted
    assert "HTTP 429" in formatted
