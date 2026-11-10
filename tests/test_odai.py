from worker.odai import FileOdaiSource
from worker.prompts import PROMPTS, build_first_image_prompt


def test_odai_are_short_sentences_with_unique_ids():
    items = FileOdaiSource().items
    assert len(items) >= 30
    assert len({o.odai_id for o in items}) == len(items) and len({o.text for o in items}) == len(items)
    for o in items:
        assert "いる" in o.text, o.text                        # 「〜している〇〇」の形
        assert o.subject and o.action and o.text == o.action + o.subject
        assert o.category in {"動物", "キャラクター", "もの"} and o.difficulty in (1, 2, 3)


def test_no_real_people_or_violence_in_odai():
    banned = ("人", "男", "女", "子供", "戦", "殺", "血", "銃")
    for o in FileOdaiSource().items:
        assert not any(w in o.text for w in banned), o.text


def test_prompts_use_whole_sentence_and_ask_for_sentence_answer():
    p = build_first_image_prompt("走っているいぬ")
    assert "走っているいぬ" in p and "文字は入れない" in p
    assert "している" in PROMPTS.conclude and "名詞を1語" not in PROMPTS.conclude
