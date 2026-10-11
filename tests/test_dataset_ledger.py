"""A run has to say which question set it measured."""

from mh import store, tasks


def test_the_query_for_runs_names_the_active_question_set():
    query = store.dataset_query({"suite": "train"})
    assert query["suite"] == "train"
    assert query["dataset.key"] == tasks.pack_key()


def test_the_name_of_the_shipped_suite_is_the_shipped_name():
    assert tasks.pack_name() == "sample_mflix"


def test_swapping_the_question_set_changes_the_key():
    before = tasks.pack_key()
    try:
        tasks.use_pack(
            [
                {
                    "id": "z01",
                    "family": "count",
                    "split": "train",
                    "collection": "theaters",
                    "question": "How many?",
                    "reference": "db.theaters.countDocuments({})",
                }
            ]
        )
        assert tasks.pack_key() != before
        assert tasks.pack_name() == "generated"
        assert store.dataset_query({})["dataset.key"] == tasks.pack_key()
    finally:
        tasks.reset_pack()
    assert tasks.pack_key() == before
