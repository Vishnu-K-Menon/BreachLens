from breachlens.ingest.tokens import Token, group_lines


def T(text, x0, top, size=10.0, conf=1.0):
    return Token(text, x0, top, x0 + 6 * len(text), top + size, conf)


def test_label_and_value_on_one_baseline_share_a_line():
    # 7.5 pt label and 10 pt value whose boxes overlap vertically (variant A forms)
    label = Token("SSN", 44, 85.0, 70, 92.5)
    value = Token("481-62-7217", 178, 83.0, 240, 93.0)
    lines = group_lines([value, label])
    assert len(lines) == 1
    assert lines[0].text == "SSN 481-62-7217"


def test_value_below_label_is_a_separate_line():
    lines = group_lines([T("LAST", 44, 85, 7.5), T("NAME", 65, 85, 7.5), T("FOWLER", 46, 97)])
    assert [ln.text for ln in lines] == ["LAST NAME", "FOWLER"]


def test_tokens_in_maps_character_spans_back_to_tokens():
    line = group_lines([T("a", 44, 85), T("Employee's", 52, 85), T("name", 93, 85)])[0]
    start = line.text.index("Employee's")
    assert [t.text for t in line.tokens_in(start, start + len("Employee's name"))] == [
        "Employee's",
        "name",
    ]
