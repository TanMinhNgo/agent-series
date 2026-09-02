from agent_core.ai.response_blocks import parse_response


def test_parse_response_extracts_safe_interactive_block() -> None:
    parsed = parse_response(
        "# Sin\n\n```agent-block\n"
        '{"type":"trig-circle","config":{"angle":45}}\n```'
    )

    assert parsed.markdown == "# Sin"
    assert parsed.blocks == [{"type": "trig-circle", "config": {"angle": 45}}]


def test_parse_response_keeps_invalid_block_as_markdown() -> None:
    source = "```agent-block\n{\"type\":\"script\",\"config\":{}}\n```"
    parsed = parse_response(source)

    assert parsed.markdown == source
    assert parsed.blocks == []
