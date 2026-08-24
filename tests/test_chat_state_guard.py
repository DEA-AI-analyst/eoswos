import copy

from chat_state_guard import protect_evaluation_state


def test_chat_side_mutation_is_replaced_with_original_snapshot() -> None:
    snapshot = {
        "company": "현대건설",
        "m_grade": "M3",
        "final_score": 0.734598552,
    }
    mutated = copy.deepcopy(snapshot)
    mutated.update({"m_grade": "M5", "final_score": 999})

    protected, changed = protect_evaluation_state(snapshot, mutated)

    assert changed is True
    assert protected == snapshot
    assert protected is not snapshot


def test_unchanged_state_is_returned_as_an_isolated_copy() -> None:
    snapshot = {"m_grade": "M3"}
    protected, changed = protect_evaluation_state(snapshot, copy.deepcopy(snapshot))
    assert changed is False
    assert protected == snapshot
    assert protected is not snapshot
