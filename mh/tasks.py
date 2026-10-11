"""The ground-truth task suite.

Each task is a question in plain language plus a **reference query** whose result
set defines the correct answer. The harness is scored on results, never on query
text, so any query that returns the right rows passes.

Every reference query is written to be deterministic: sorts carry tie breakers so
the top-k boundary cannot flip between runs.

The suite is split into ``train`` (edits are selected on it) and ``holdout``
(edits are verified on it). The split is fixed by hand so both halves cover every
task family; it is never recomputed, so a promoted version cannot cheat by
redrawing the boundary.
"""

from __future__ import annotations

TASKS: list[dict] = [
    # ---------- family: find + filters ----------
    {
        "id": "a01",
        "family": "find",
        "split": "train",
        "collection": "movies",
        "question": "How many movies have an IMDb rating above 9 and more than 100,000 votes?",
        "reference": 'db.movies.countDocuments({"imdb.rating": {"$gt": 9}, "imdb.votes": {"$gt": 100000}})',
    },
    {
        "id": "a02",
        "family": "find",
        "split": "train",
        "collection": "movies",
        "question": "How many movies list Documentary among their genres?",
        "reference": 'db.movies.countDocuments({"genres": "Documentary"})',
    },
    {
        "id": "a03",
        "family": "find",
        "split": "holdout",
        "collection": "movies",
        "question": "How many movies list both Action and Comedy among their genres?",
        "reference": 'db.movies.countDocuments({"genres": {"$all": ["Action", "Comedy"]}})',
    },
    {
        "id": "a04",
        "family": "find",
        "split": "train",
        "collection": "movies",
        "question": "How many movies were released before the year 1920?",
        "reference": 'db.movies.countDocuments({"year": {"$lt": 1920}})',
    },
    {
        "id": "a05",
        "family": "find",
        "split": "holdout",
        "collection": "movies",
        "question": "How many movies have no tomatoes field at all?",
        "reference": 'db.movies.countDocuments({"tomatoes": {"$exists": false}})',
    },
    {
        "id": "a06",
        "family": "find",
        "split": "train",
        "collection": "movies",
        "question": "How many movies list exactly one person in the cast?",
        "reference": 'db.movies.countDocuments({"cast": {"$size": 1}})',
    },
    {
        "id": "a07",
        "family": "find",
        "split": "train",
        "collection": "movies",
        "question": "How many movies are rated G and were released after 1970?",
        "reference": 'db.movies.countDocuments({"rated": "G", "year": {"$gt": 1970}})',
    },
    {
        "id": "a08",
        "family": "find",
        "split": "holdout",
        "collection": "movies",
        "question": "How many movie titles contain the word war, ignoring case?",
        "reference": 'db.movies.countDocuments({"title": {"$regex": "war", "$options": "i"}})',
    },
    {
        "id": "a09",
        "family": "find",
        "split": "train",
        "collection": "movies",
        "question": "How many movies list both English and French among their languages?",
        "reference": 'db.movies.countDocuments({"languages": {"$all": ["English", "French"]}})',
    },
    {
        "id": "a10",
        "family": "find",
        "split": "holdout",
        "collection": "movies",
        "question": "How many movies have more than 50 award wins?",
        "reference": 'db.movies.countDocuments({"awards.wins": {"$gt": 50}})',
    },
    {
        "id": "a11",
        "family": "find",
        "split": "train",
        "collection": "movies",
        "question": "How many movies have a runtime under 20 minutes?",
        "reference": 'db.movies.countDocuments({"runtime": {"$lt": 20}})',
    },
    {
        "id": "a12",
        "family": "find",
        "split": "holdout",
        "collection": "movies",
        "question": "How many movies list both USA and Canada among their countries?",
        "reference": 'db.movies.countDocuments({"countries": {"$all": ["USA", "Canada"]}})',
    },
    # ---------- family: projection, sort, limit ----------
    {
        "id": "b01",
        "family": "sort",
        "split": "train",
        "collection": "movies",
        "question": (
            "Return the 5 highest IMDb rated movies among those with more than 500,000 votes; "
            "show only the title and the IMDb rating, best first."
        ),
        "reference": (
            'db.movies.find({"imdb.votes": {"$gt": 500000}}, {"title": 1, "imdb.rating": 1})'
            '.sort({"imdb.rating": -1, "imdb.votes": -1, "_id": 1}).limit(5)'
        ),
    },
    {
        "id": "b02",
        "family": "sort",
        "split": "holdout",
        "collection": "movies",
        "question": "List the 10 oldest movies with their title and year, oldest first, ties broken by title.",
        "reference": 'db.movies.find({}, {"title": 1, "year": 1}).sort({"year": 1, "title": 1}).limit(10)',
    },
    {
        "id": "b03",
        "family": "sort",
        "split": "train",
        "collection": "movies",
        "question": "List the 8 longest movies with their title and runtime, longest first, ties broken by title.",
        "reference": 'db.movies.find({}, {"title": 1, "runtime": 1}).sort({"runtime": -1, "title": 1}).limit(8)',
    },
    {
        "id": "b04",
        "family": "sort",
        "split": "train",
        "collection": "movies",
        "question": "Return the titles of 12 movies whose title starts with the letter A, in alphabetical order.",
        "reference": 'db.movies.find({"title": {"$regex": "^A"}}, {"title": 1}).sort({"title": 1}).limit(12)',
    },
    {
        "id": "b05",
        "family": "sort",
        "split": "holdout",
        "collection": "movies",
        "question": "Return the 10 movies with the most IMDb votes, showing the title and the number of votes.",
        "reference": (
            'db.movies.find({"imdb.votes": {"$gt": 0}}, {"title": 1, "imdb.votes": 1})'
            '.sort({"imdb.votes": -1, "_id": 1}).limit(10)'
        ),
    },
    {
        "id": "b06",
        "family": "sort",
        "split": "train",
        "collection": "movies",
        "question": "Return the 5 most recently released movies with their title and release date, newest first.",
        "reference": 'db.movies.find({}, {"title": 1, "released": 1}).sort({"released": -1, "_id": 1}).limit(5)',
    },
    {
        "id": "b07",
        "family": "sort",
        "split": "holdout",
        "collection": "movies",
        "question": (
            "Return the 10 movies with the largest number of viewer reviews in tomatoes, "
            "showing the title and tomatoes.viewer.numReviews, largest first."
        ),
        "reference": (
            'db.movies.find({}, {"title": 1, "tomatoes.viewer.numReviews": 1})'
            '.sort({"tomatoes.viewer.numReviews": -1, "_id": 1}).limit(10)'
        ),
    },
    {
        "id": "b08",
        "family": "sort",
        "split": "train",
        "collection": "movies",
        "question": "Return 10 titles of movies from 1994 with an IMDb rating above 8, sorted alphabetically.",
        "reference": (
            'db.movies.find({"year": 1994, "imdb.rating": {"$gt": 8}}, {"title": 1})'
            '.sort({"title": 1}).limit(10)'
        ),
    },
    {
        "id": "b09",
        "family": "sort",
        "split": "holdout",
        "collection": "movies",
        "question": (
            "Return the 6 longest movies released in 2014 with title and runtime, "
            "longest first, ties broken by title."
        ),
        "reference": (
            'db.movies.find({"year": 2014, "runtime": {"$gt": 0}}, {"title": 1, "runtime": 1})'
            '.sort({"runtime": -1, "title": 1}).limit(6)'
        ),
    },
    {
        "id": "b10",
        "family": "sort",
        "split": "train",
        "collection": "movies",
        "question": "Return the titles of 20 movies released in 1999, in alphabetical order.",
        "reference": 'db.movies.find({"year": 1999}, {"title": 1}).sort({"title": 1}).limit(20)',
    },
    # ---------- family: aggregation ----------
    {
        "id": "c01",
        "family": "aggregate",
        "split": "train",
        "collection": "movies",
        "question": "What is the average IMDb rating of all movies released after 2000? Return one number.",
        "reference": (
            'db.movies.aggregate([{"$match": {"year": {"$gt": 2000}}}, '
            '{"$group": {"_id": null, "avgRating": {"$avg": "$imdb.rating"}}}])'
        ),
    },
    {
        "id": "c02",
        "family": "aggregate",
        "split": "holdout",
        "collection": "movies",
        "question": "How many movies were released in each year from 1990 to 1994? List the years in order.",
        "reference": (
            'db.movies.aggregate([{"$match": {"year": {"$gte": 1990, "$lte": 1994}}}, '
            '{"$group": {"_id": "$year", "movies": {"$sum": 1}}}, {"$sort": {"_id": 1}}])'
        ),
    },
    {
        "id": "c03",
        "family": "aggregate",
        "split": "train",
        "collection": "movies",
        "question": (
            "How many movies are there for each content rating? Return the 10 largest groups, "
            "biggest first, ties broken by rating name."
        ),
        "reference": (
            'db.movies.aggregate([{"$group": {"_id": "$rated", "movies": {"$sum": 1}}}, '
            '{"$sort": {"movies": -1, "_id": 1}}, {"$limit": 10}])'
        ),
    },
    {
        "id": "c04",
        "family": "aggregate",
        "split": "train",
        "collection": "movies",
        "question": (
            "For each genre, how many movies are there? Return the 10 biggest genres, "
            "most movies first, ties broken by genre name."
        ),
        "reference": (
            'db.movies.aggregate([{"$unwind": "$genres"}, '
            '{"$group": {"_id": "$genres", "movies": {"$sum": 1}}}, '
            '{"$sort": {"movies": -1, "_id": 1}}, {"$limit": 10}])'
        ),
    },
    {
        "id": "c05",
        "family": "aggregate",
        "split": "holdout",
        "collection": "movies",
        "question": (
            "What is the average runtime for each genre? Return the 10 genres with the most movies, "
            "most movies first, ties broken by genre name."
        ),
        "reference": (
            'db.movies.aggregate([{"$unwind": "$genres"}, '
            '{"$group": {"_id": "$genres", "avgRuntime": {"$avg": "$runtime"}, "movies": {"$sum": 1}}}, '
            '{"$sort": {"movies": -1, "_id": 1}}, {"$limit": 10}])'
        ),
    },
    {
        "id": "c06",
        "family": "aggregate",
        "split": "train",
        "collection": "movies",
        "question": "What is the total number of award wins across all movies released before 1950? Return one number.",
        "reference": (
            'db.movies.aggregate([{"$match": {"year": {"$lt": 1950}}}, '
            '{"$group": {"_id": null, "wins": {"$sum": "$awards.wins"}}}])'
        ),
    },
    {
        "id": "c07",
        "family": "aggregate",
        "split": "holdout",
        "collection": "movies",
        "question": (
            "For each director, how many movies did they direct? Return the 10 directors with the most "
            "movies, most movies first, ties broken by director name."
        ),
        "reference": (
            'db.movies.aggregate([{"$unwind": "$directors"}, '
            '{"$group": {"_id": "$directors", "movies": {"$sum": 1}}}, '
            '{"$sort": {"movies": -1, "_id": 1}}, {"$limit": 10}])'
        ),
    },
    {
        "id": "c08",
        "family": "aggregate",
        "split": "train",
        "collection": "movies",
        "question": (
            "What is the highest IMDb rating within each content rating category? "
            "Return 8 categories, highest rating first, ties broken by category name."
        ),
        "reference": (
            'db.movies.aggregate([{"$group": {"_id": "$rated", "best": {"$max": "$imdb.rating"}}}, '
            '{"$sort": {"best": -1, "_id": 1}}, {"$limit": 8}])'
        ),
    },
    {
        "id": "c09",
        "family": "aggregate",
        "split": "holdout",
        "collection": "movies",
        "question": "How many movies have three or more genres? Return one number.",
        "reference": (
            'db.movies.aggregate([{"$match": {"$expr": {"$gte": [{"$size": {"$ifNull": ["$genres", []]}}, 3]}}}, '
            '{"$count": "movies"}])'
        ),
    },
    {
        "id": "c10",
        "family": "aggregate",
        "split": "train",
        "collection": "movies",
        "question": "How many movies have no tomatoes critic rating field? Return one number.",
        "reference": (
            'db.movies.aggregate([{"$match": {"tomatoes.critic.rating": {"$exists": false}}}, '
            '{"$count": "movies"}])'
        ),
    },
    {
        "id": "c11",
        "family": "aggregate",
        "split": "holdout",
        "collection": "movies",
        "question": (
            "For each country, how many movies are there? Return the 10 countries with the most movies, "
            "most movies first, ties broken by country name."
        ),
        "reference": (
            'db.movies.aggregate([{"$unwind": "$countries"}, '
            '{"$group": {"_id": "$countries", "movies": {"$sum": 1}}}, '
            '{"$sort": {"movies": -1, "_id": 1}}, {"$limit": 10}])'
        ),
    },
    {
        "id": "c12",
        "family": "aggregate",
        "split": "train",
        "collection": "movies",
        "question": "What is the total number of award nominations for movies rated R? Return one number.",
        "reference": (
            'db.movies.aggregate([{"$match": {"rated": "R"}}, '
            '{"$group": {"_id": null, "nominations": {"$sum": "$awards.nominations"}}}])'
        ),
    },
    {
        "id": "c13",
        "family": "aggregate",
        "split": "holdout",
        "collection": "movies",
        "question": (
            "For each year from 2000 to 2010 inclusive, what is the average runtime? "
            "Return the rows in year order."
        ),
        "reference": (
            'db.movies.aggregate([{"$match": {"year": {"$gte": 2000, "$lte": 2010}}}, '
            '{"$group": {"_id": "$year", "avgRuntime": {"$avg": "$runtime"}}}, {"$sort": {"_id": 1}}])'
        ),
    },
    {
        "id": "c14",
        "family": "aggregate",
        "split": "train",
        "collection": "movies",
        "question": "How many movies list exactly three genres? Return one number.",
        "reference": 'db.movies.countDocuments({"genres": {"$size": 3}})',
    },
    # ---------- family: joining collections ----------
    {
        "id": "d01",
        "family": "lookup",
        "split": "train",
        "collection": "movies",
        "question": (
            "Which 10 movies have the most comments? Return the movie title and the number of comments, "
            "most comments first, ties broken by title."
        ),
        "reference": (
            'db.movies.aggregate([{"$lookup": {"from": "comments", "localField": "_id", '
            '"foreignField": "movie_id", "as": "c"}}, {"$project": {"title": 1, "n": {"$size": "$c"}}}, '
            '{"$sort": {"n": -1, "title": 1}}, {"$limit": 10}])'
        ),
    },
    {
        "id": "d02",
        "family": "lookup",
        "split": "holdout",
        "collection": "movies",
        "question": "How many movies have at least one comment? Return one number.",
        "reference": (
            'db.movies.aggregate([{"$lookup": {"from": "comments", "localField": "_id", '
            '"foreignField": "movie_id", "as": "c"}}, {"$match": {"c": {"$ne": []}}}, {"$count": "movies"}])'
        ),
    },
    {
        "id": "d03",
        "family": "lookup",
        "split": "train",
        "collection": "comments",
        "question": "How many comments were written for movies released before 1950? Return one number.",
        "reference": (
            'db.comments.aggregate([{"$lookup": {"from": "movies", "localField": "movie_id", '
            '"foreignField": "_id", "as": "m"}}, {"$match": {"m": {"$elemMatch": {"year": {"$lt": 1950}}}}}, '
            '{"$count": "comments"}])'
        ),
    },
    {
        "id": "d04",
        "family": "lookup",
        "split": "holdout",
        "collection": "comments",
        "question": (
            "Which 10 people wrote the most comments? Return the name and the number of comments, "
            "most comments first, ties broken by name."
        ),
        "reference": (
            'db.comments.aggregate([{"$group": {"_id": "$name", "n": {"$sum": 1}}}, '
            '{"$sort": {"n": -1, "_id": 1}}, {"$limit": 10}])'
        ),
    },
    {
        "id": "d05",
        "family": "lookup",
        "split": "train",
        "collection": "movies",
        "question": (
            "How many comments do the movies of each content rating have in total? Return one row per "
            "rating, with the number of comments, ordered alphabetically by rating."
        ),
        "reference": (
            'db.movies.aggregate([{"$lookup": {"from": "comments", "localField": "_id", '
            '"foreignField": "movie_id", "as": "c"}}, {"$group": {"_id": "$rated", "n": {"$sum": {"$size": "$c"}}}}, '
            '{"$sort": {"_id": 1}}])'
        ),
    },
    {
        "id": "d06",
        "family": "lookup",
        "split": "holdout",
        "collection": "comments",
        "question": "How many different movies have comments? Return one number.",
        "reference": 'db.comments.aggregate([{"$group": {"_id": "$movie_id"}}, {"$count": "movies"}])',
    },
    {
        "id": "d07",
        "family": "lookup",
        "split": "train",
        "collection": "movies",
        "question": (
            "What is the average number of comments per movie among movies with an IMDb rating above 8? "
            "Return one number."
        ),
        "reference": (
            'db.movies.aggregate([{"$match": {"imdb.rating": {"$gt": 8}}}, '
            '{"$lookup": {"from": "comments", "localField": "_id", "foreignField": "movie_id", "as": "c"}}, '
            '{"$group": {"_id": null, "avgComments": {"$avg": {"$size": "$c"}}}}])'
        ),
    },
    {
        "id": "d08",
        "family": "lookup",
        "split": "holdout",
        "collection": "movies",
        "question": (
            "Which 5 movies released after 2010 have the most comments? Return the title and the number "
            "of comments, most comments first, ties broken by title."
        ),
        "reference": (
            'db.movies.aggregate([{"$match": {"year": {"$gt": 2010}}}, '
            '{"$lookup": {"from": "comments", "localField": "_id", "foreignField": "movie_id", "as": "c"}}, '
            '{"$project": {"title": 1, "n": {"$size": "$c"}}}, {"$sort": {"n": -1, "title": 1}}, {"$limit": 5}])'
        ),
    },
    # ---------- family: theaters and geography ----------
    {
        "id": "e01",
        "family": "geo",
        "split": "train",
        "collection": "theaters",
        "question": "How many theaters are in the state of California? Return one number.",
        "reference": 'db.theaters.countDocuments({"location.address.state": "CA"})',
    },
    {
        "id": "e02",
        "family": "geo",
        "split": "holdout",
        "collection": "theaters",
        "question": (
            "Return the 5 theaters in Chicago with their theater id, street and city, "
            "in ascending order of theater id."
        ),
        "reference": (
            'db.theaters.find({"location.address.city": "Chicago"}, {"theaterId": 1, '
            '"location.address.street1": 1, "location.address.city": 1}).sort({"theaterId": 1}).limit(5)'
        ),
    },
    {
        "id": "e03",
        "family": "geo",
        "split": "train",
        "collection": "theaters",
        "question": "How many theaters are there in total? Return one number.",
        "reference": 'db.theaters.countDocuments({})',
    },
    {
        "id": "e04",
        "family": "geo",
        "split": "holdout",
        "collection": "theaters",
        "question": (
            "Which cities have more than 8 theaters? Return the city and the number of theaters, "
            "in alphabetical order of city."
        ),
        "reference": (
            'db.theaters.aggregate([{"$group": {"_id": "$location.address.city", "n": {"$sum": 1}}}, '
            '{"$match": {"n": {"$gt": 8}}}, {"$sort": {"_id": 1}}])'
        ),
    },
    {
        "id": "e05",
        "family": "geo",
        "split": "train",
        "collection": "theaters",
        "question": (
            "How many theaters lie inside the box that covers Texas, with longitude between -106.65 and "
            "-93.5 and latitude between 25.84 and 36.5? Return one number."
        ),
        "reference": (
            'db.theaters.countDocuments({"location.geo.coordinates": '
            '{"$geoWithin": {"$box": [[-106.65, 25.84], [-93.5, 36.5]]}}})'
        ),
    },
    # ---------- family: types and traps ----------
    {
        "id": "f01",
        "family": "traps",
        "split": "train",
        "collection": "comments",
        "question": "How many comments were posted during the year 2015? Return one number.",
        "reference": (
            'db.comments.countDocuments({"date": {"$gte": {"$date": "2015-01-01T00:00:00Z"}, '
            '"$lt": {"$date": "2016-01-01T00:00:00Z"}}})'
        ),
    },
    {
        "id": "f02",
        "family": "traps",
        "split": "holdout",
        "collection": "movies",
        "question": "How many movies have an IMDb rating exactly equal to 7? Return one number.",
        "reference": 'db.movies.countDocuments({"imdb.rating": 7})',
    },
    {
        "id": "f03",
        "family": "traps",
        "split": "train",
        "collection": "movies",
        "question": "How many movies have more than 20 people in the cast? Return one number.",
        "reference": (
            'db.movies.countDocuments({"$expr": {"$gt": [{"$size": {"$ifNull": ["$cast", []]}}, 20]}})'
        ),
    },
    {
        "id": "f04",
        "family": "traps",
        "split": "holdout",
        "collection": "comments",
        "question": "How many comments mention the word great in their text, ignoring case? Return one number.",
        "reference": 'db.comments.countDocuments({"text": {"$regex": "great", "$options": "i"}})',
    },
    {
        "id": "f05",
        "family": "traps",
        "split": "train",
        "collection": "comments",
        "question": "How many comments were written by people whose email ends with @fakegmail.com? Return one number.",
        "reference": 'db.comments.countDocuments({"email": {"$regex": "@fakegmail[.]com$"}})',
    },
    {
        "id": "f06",
        "family": "traps",
        "split": "holdout",
        "collection": "movies",
        "question": "How many movies have a tomatoes fresh count exactly equal to zero? Return one number.",
        "reference": 'db.movies.countDocuments({"tomatoes.fresh": 0})',
    },
    {
        "id": "f07",
        "family": "traps",
        "split": "train",
        "collection": "movies",
        "question": "How many movies were released in 1995 with an IMDb rating of at least 8.5? Return one number.",
        "reference": 'db.movies.countDocuments({"year": 1995, "imdb.rating": {"$gte": 8.5}})',
    },
    {
        "id": "f08",
        "family": "traps",
        "split": "holdout",
        "collection": "movies",
        "question": "How many movies have a runtime of exactly 90 minutes and an IMDb rating above 7? Return one number.",
        "reference": 'db.movies.countDocuments({"runtime": 90, "imdb.rating": {"$gt": 7}})',
    },
]


def by_split(split: str) -> list[dict]:
    """Return every task assigned to a split (``train`` or ``holdout``)."""
    if split not in ("train", "holdout"):
        raise ValueError("split must be 'train' or 'holdout'")
    return [task for task in TASKS if task["split"] == split]


def by_id(task_id: str) -> dict | None:
    """Return one task by id."""
    for task in TASKS:
        if task["id"] == task_id:
            return task
    return None


def summary() -> dict:
    """Counts used in reports: totals per split and per family."""
    splits: dict[str, int] = {}
    families: dict[str, int] = {}
    for task in TASKS:
        splits[task["split"]] = splits.get(task["split"], 0) + 1
        families[task["family"]] = families.get(task["family"], 0) + 1
    return {"total": len(TASKS), "splits": splits, "families": families}
