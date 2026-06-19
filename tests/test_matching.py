import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import matching


def test_colors_are_writing_categories():
    assert set(matching.PARAM_COLORS.keys()) == {
        "Grammar", "Spelling", "Punctuation", "Tense/Narrative", "Hooks"}


def test_short_heading_like_quote_still_locates():
    # a single capitalized word that the old heading filter would drop
    text = "Introduction\nThey was late."
    rng = matching.locate_quote(text, "Introduction")
    assert rng is not None and text[rng[0]:rng[1]] == "Introduction"


def test_build_spans_maps_grammar_quote():
    text = "They was late to the meeting."
    data = {"per_parameter": {"Grammar": {"areas_of_improvement": [
        {"quote_verbatim": "They was late", "issue": "x", "fix": "They were late", "why_this_helps": "y"}]}}}
    spans_map, ranges = matching.build_spans_by_param(text, data)
    assert spans_map["Grammar"], "expected one Grammar span"
    s, e, color, aid = spans_map["Grammar"][0]
    assert text[s:e].startswith("They was late")
    assert color == "#ff6b6b"
