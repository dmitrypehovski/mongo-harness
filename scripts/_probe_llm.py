"""Temporary probe: what does the model actually answer when asked for a JSON list?"""

import json
import urllib.request

from mh import llm, scaffold, scorer

db = scorer.connect().get_database("sample_mflix")
shape = scaffold.describe_shape(db, "theaters")

print("=== простой запрос к модели:")
simple = llm.chat([{"role": "user", "content": "Say the word ok."}], max_tokens=20)
print(repr(simple))

payload = {
    "model": llm.default_model(),
    "messages": [{"role": "user", "content": scaffold.PROMPT.format(want=3, shape=shape)}],
    "temperature": 0.4,
    "max_tokens": 1500,
}
request = urllib.request.Request(
    llm.API_URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Authorization": f"Bearer {llm.api_key()}", "Content-Type": "application/json"},
)
raw = json.loads(urllib.request.urlopen(request, timeout=120).read())
choice = raw["choices"][0]
print()
print("=== finish_reason:", choice.get("finish_reason"))
print("=== usage:", raw.get("usage"))
print("=== message keys:", sorted(choice["message"].keys()))
print("=== content:", repr((choice["message"].get("content") or "")[:300]))
if choice["message"].get("reasoning"):
    print("=== reasoning:", repr(choice["message"]["reasoning"][:300]))
