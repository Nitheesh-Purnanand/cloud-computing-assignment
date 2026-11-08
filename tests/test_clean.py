import json

from clean import clean, reject_reason

GOOD = '{"intent": "alarm_set", "date": "tomorrow", "time": "six am", "place": null}'


def test_valid_reply_is_kept():
    assert reject_reason("wake me at six am tomorrow", GOOD)[0] is None


def test_each_reject_reason():
    text = "wake me at six am tomorrow"
    assert reject_reason(text, "Sure! here is the JSON")[0] == "a"
    assert reject_reason(text, '{"intent": "alarm_set", "date": null}')[0] == "b"
    assert reject_reason(text, '{"intent": "music_play", "date": null, "time": null, "place": null}')[0] == "c"
    assert reject_reason(text, '{"intent": "alarm_set", "date": "friday", "time": null, "place": null}')[0] == "d"
    assert reject_reason(text, '{"intent": "alarm_set", "date": 7, "time": null, "place": null}')[0] == "d"


def test_duplicates_keep_smallest_id_and_counts_add_up():
    recs = [
        {"id": "C0003", "text": "wake me at six am tomorrow", "teacher_raw": GOOD},
        {"id": "C0001", "text": "Wake me at six am  tomorrow", "teacher_raw": GOOD},
        {"id": "C0002", "text": "x", "teacher_raw": "nope"},
    ]
    kept, c = clean(recs)
    assert [r["id"] for r in kept] == ["C0001"]
    assert c["duplicates"] == 1 and c["a"] == 1
    assert c["input"] == c["a"] + c["b"] + c["c"] + c["d"] + c["duplicates"] + c["kept"]
    assert json.loads(kept[0]["target"])["intent"] == "alarm_set"
