from agent_core.knowledge import _chunks


def test_chunking_keeps_content_and_bounds_chunk_size():
    source = "mot " * 500
    chunks = _chunks(source)
    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 800 for chunk in chunks)
    assert chunks[0].startswith("mot")
