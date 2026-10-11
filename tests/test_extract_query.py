"""Pulling the query out of whatever the model wrapped it in."""

from mh.agent import extract_query

MULTILINE = """Here is the query you asked for:

```javascript
db.theaters.find(
  {"location.address.state": "MN"}
)
```
"""

CHAINED = 'The answer is db.theaters.find({}).sort({"theaterId": 1}).limit(5) and that is all.'


def test_a_fenced_multiline_query_comes_out_whole():
    assert extract_query(MULTILINE) == 'db.theaters.find(\n  {"location.address.state": "MN"}\n)'


def test_the_chain_after_a_filter_is_not_lost():
    assert extract_query(CHAINED) == 'db.theaters.find({}).sort({"theaterId": 1}).limit(5)'


def test_prose_before_the_query_is_dropped():
    assert extract_query('Sure! db.theaters.countDocuments({"theaterId": 1000})') == (
        'db.theaters.countDocuments({"theaterId": 1000})'
    )


def test_text_without_a_query_is_returned_as_is():
    assert extract_query("I cannot answer that.") == "I cannot answer that."


def test_a_brace_inside_a_string_does_not_close_the_query():
    raw = 'db.movies.find({"title": "The {Big} Lebowski"})'
    assert extract_query(raw) == raw
