import pytest
from unittest.mock import MagicMock
from scripts.auto_extractor import SyllabusDrivenExtractor

class MockOllamaRuntimeManager:
    def __init__(self):
        self.generate_json = MagicMock()

def test_chunking_logic():
    mgr = MockOllamaRuntimeManager()
    extractor = SyllabusDrivenExtractor(mgr)
    
    # Text with 3 paragraphs, each > 2000 chars, total > 4000.
    p1 = "A" * 2500
    p2 = "B" * 2500
    p3 = "C" * 1000
    
    text = f"{p1}\n\n{p2}\n\n{p3}"
    
    chunks = extractor._chunk_text(text, max_chars=4000)
    
    # chunk 1: p1 (2500 chars) -> next is p2, 2500+2500 > 4000, so split.
    # chunk 2: p2 (2500 chars) -> next is p3, 2500+1000 = 3500 < 4000, so join p2 and p3.
    
    assert len(chunks) == 2
    assert chunks[0] == p1
    assert chunks[1] == f"{p2}\n\n{p3}"

def test_extract_virtual_highlights():
    mgr = MockOllamaRuntimeManager()
    
    # Mock to return a valid highlights response
    mgr.generate_json.return_value = {
        "highlights": [
            {
                "heading": "Test Concept",
                "text": "This is a key concept.",
                "color": "yellow"
            }
        ]
    }
    
    extractor = SyllabusDrivenExtractor(mgr)
    
    syllabus = "Learn about key concepts."
    notes = "This is a key concept. It is very important."
    
    result = extractor.extract_virtual_highlights(syllabus, notes)
    
    assert mgr.generate_json.call_count == 1
    assert len(result) == 1
    assert result[0]["heading"] == "Test Concept"
    assert result[0]["text"] == "This is a key concept."
    assert result[0]["color"] == "yellow"
    
def test_extract_virtual_highlights_invalid_json():
    mgr = MockOllamaRuntimeManager()
    
    # Mock to return an invalid or empty response
    mgr.generate_json.return_value = None
    
    extractor = SyllabusDrivenExtractor(mgr)
    
    syllabus = "Learn about key concepts."
    notes = "This is a key concept. It is very important."
    
    result = extractor.extract_virtual_highlights(syllabus, notes)
    
    assert mgr.generate_json.call_count == 1
    assert len(result) == 0

def test_extract_virtual_highlights_malformed_list():
    mgr = MockOllamaRuntimeManager()
    
    # Mock to return an invalid dict response (missing keys in items)
    mgr.generate_json.return_value = {
        "highlights": [
            {"wrong_key": "wrong"}
        ]
    }
    
    extractor = SyllabusDrivenExtractor(mgr)
    
    syllabus = "Learn about key concepts."
    notes = "This is a key concept. It is very important."
    
    result = extractor.extract_virtual_highlights(syllabus, notes)
    
    assert mgr.generate_json.call_count == 1
    assert len(result) == 0
