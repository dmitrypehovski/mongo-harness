
"""Questions and their references have to agree about the shape of the answer."""

from mh import scaffold


def candidate(question: str, reference: str) -> scaffold.Candidate:
    return scaffold.Candidate(question=question, reference=reference, collection="theaters")


class Parsed:
    """The bits of a parsed query the shape check looks at."""

    def __init__(self, method: str = "find"):
        self.method = method


def test_a_grouped_field_the_question_never_names_is_refused():
    subject = candidate(
        "How many theatres are in each state?",
        'db.theaters.aggregate([{"$group": {"_id": "$location.address.state", "theaterCount": {"$sum": 1}}}])',
    )
    reason = scaffold._shape_mismatch(subject, Parsed("aggregate"))
    assert "never names" in reason


def test_a_grouped_field_the_question_names_is_accepted():
    subject = candidate(
        "How many theatres are in each state? Show a theaterCount for each.",
        'db.theaters.aggregate([{"$group": {"_id": "$state", "theaterCount": {"$sum": 1}}}])',
    )
    assert scaffold._shape_mismatch(subject, Parsed("aggregate")) == ""


def test_a_question_asking_for_fields_needs_a_projection():
    subject = candidate(
        "List each theater's ID and city, ordered by theater ID.",
        'db.theaters.find({"location.address.state": "MN"}).sort({"theaterId": 1})',
    )
    reason = scaffold._shape_mismatch(subject, Parsed("find"))
    assert "whole documents" in reason


def test_the_same_question_with_a_projection_is_accepted():
    subject = candidate(
        "List each theater's ID and city, ordered by theater ID.",
        'db.theaters.find({"location.address.state": "MN"}, {"theaterId": 1, "location.address.city": 1}).sort({"theaterId": 1})',
    )
    assert scaffold._shape_mismatch(subject, Parsed("find")) == ""


def test_a_grouped_question_is_told_the_keys_of_each_row():
    subject = candidate(
        "How many theatres does each state have?",
        'db.theaters.aggregate([{"$group": {"_id": "$location.address.state", "theaterCount": {"$sum": 1}}}, {"$sort": {"theaterCount": -1}}])',
    )
    scaffold.clarify(subject)
    assert subject.question.endswith("Return each row with the keys `_id`, `theaterCount`.")
    assert subject.clarified == "named the keys of each row"


def test_a_question_naming_fields_is_told_the_answer_is_whole_documents():
    subject = candidate(
        "List each theater's ID and city.",
        'db.theaters.find({"location.address.state": "MN"})',
    )
    scaffold.clarify(subject)
    assert subject.question.endswith("Return whole documents, without limiting the fields.")
    assert subject.clarified == "said the answer is whole documents"


def test_a_clarified_question_is_no_longer_refused_for_shape():
    subject = candidate(
        "How many theatres does each state have?",
        'db.theaters.aggregate([{"$group": {"_id": "$state", "theaterCount": {"$sum": 1}}}])',
    )
    assert scaffold._shape_mismatch(subject, Parsed("aggregate")) != ""
    scaffold.clarify(subject)
    assert scaffold._shape_mismatch(subject, Parsed("aggregate")) == ""


def test_a_plain_count_question_is_left_alone():
    subject = candidate(
        "How many theaters are there in Minnesota?",
        'db.theaters.countDocuments({"location.address.state": "MN"})',
    )
    assert scaffold._shape_mismatch(subject, Parsed("countDocuments")) == ""
    scaffold.clarify(subject)
    assert subject.question == "How many theaters are there in Minnesota?"
    assert subject.clarified == ""
