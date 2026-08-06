from __future__ import annotations

from app.content_build_graph import _segment_id
from app.content_segment import ContentSegment


def test_segment_id_supports_typed_and_legacy_segments():
    assert _segment_id(ContentSegment(segment_id="typed-1")) == "typed-1"
    assert _segment_id({"segment_id": "legacy-1"}) == "legacy-1"


def test_segment_id_does_not_call_dict_get_on_typed_empty_segment():
    assert _segment_id(ContentSegment(segment_id="")) == ""
