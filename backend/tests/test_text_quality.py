from app.text_quality import repair_mojibake, repair_text_tree


def test_repairs_common_utf8_mojibake_without_touching_normal_text():
    assert repair_mojibake("Rock Nâ Roll") == "Rock N’ Roll"
    assert repair_mojibake("GoiÃ¡s") == "Goiás"
    assert repair_mojibake("Ø§ÙÙÙÙØ¯Ø³") == "المهندس"
    assert repair_mojibake("Do you say âThank Youâ") == "Do you say “Thank You"
    assert repair_mojibake("后端工程师") == "后端工程师"


def test_repairs_nested_public_job_payloads():
    payload = repair_text_tree(
        {"title": "GoiÃ¡s", "skills": [{"name": "AnÃ¡lise"}]}
    )
    assert payload == {"title": "Goiás", "skills": [{"name": "Análise"}]}
