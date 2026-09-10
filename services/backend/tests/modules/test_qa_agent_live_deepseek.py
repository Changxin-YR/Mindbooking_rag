import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.qa_agent_live_deepseek import (
    _extract_pending_action,
    classify_http_response,
    tool_names_from_events,
)


def test_classify_http_response_requires_generated_text() -> None:
    assert classify_http_response(200, generated=False) == "REQUEST_FAILED"
    assert classify_http_response(200, generated=True) == "PASS"
    assert classify_http_response(401, generated=False) == "CREDENTIAL_INVALID"
    assert classify_http_response(429, generated=False) == "RATE_LIMITED"


def test_tool_names_from_events_keeps_model_selected_tools() -> None:
    events = [
        {"type": "tool/call", "data": {"name": "review.list_pending"}},
        {"type": "tool/result", "data": {"name": "review.list_pending"}},
        {"type": "assistant/message", "data": {}},
    ]
    assert tool_names_from_events(events) == ["review.list_pending"]


def test_extract_pending_action_parses_harness_python_repr() -> None:
    events = [
        {
            "type": "tool/result",
            "data": {
                "message": repr(
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": '{"pending_action":{"id":"ACT-1"}}',
                            }
                        ]
                    }
                )
            },
        }
    ]
    assert _extract_pending_action(events) == {"id": "ACT-1"}


def test_extract_pending_action_parses_mcp_error_prefix() -> None:
    events = [
        {
            "type": "tool/result",
            "data": {"message": 'Error: MCP error -32004: {"pending_action":{"id":"ACT-2"}}'},
        }
    ]
    assert _extract_pending_action(events) == {"id": "ACT-2"}
