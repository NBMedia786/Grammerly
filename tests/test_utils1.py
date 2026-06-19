import utils1


def test_param_order_is_five_writing_categories():
    assert utils1.PARAM_ORDER == [
        "Tense/Narrative", "Hooks", "Grammar", "Spelling", "Punctuation", "Facts",
    ]


def test_normalize_keeps_corrected_text_verbatim():
    payload = {
        "corrected_text": "Line one.\n\n\nLine two.",  # triple newline preserved
        "summary": "  Two typos fixed.  ",
        "per_parameter": {
            "Grammar": {
                "score": 7,
                "areas_of_improvement": [
                    {"quote": "he go", "issue": "agreement",
                     "edit_suggestion": "he goes", "why": "subject-verb"},
                ],
            }
        },
    }
    out = utils1.normalize_review_payload(payload)
    # corrected_text must NOT be whitespace-collapsed or bullet-stripped
    assert out["corrected_text"] == "Line one.\n\n\nLine two."
    # legacy alias keys are mapped into the canonical AOI schema
    aoi = out["per_parameter"]["Grammar"]["areas_of_improvement"][0]
    assert aoi == {
        "quote_verbatim": "he go",
        "issue": "agreement",
        "fix": "he goes",
        "why_this_helps": "subject-verb",
    }
    # viral keys are not introduced
    assert "viral_quotient" not in out
    assert "drop_off_risks" not in out
