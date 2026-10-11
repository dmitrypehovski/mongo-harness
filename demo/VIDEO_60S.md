# The 60-second video

The submission form asks for one minute with video **and** audio. Judges are in the
US, so the spoken lines are in English; the notes in parentheses are for you and are
not read out. Every command below was timed on the cluster: `status` 3.1s, `edits`
2.5s. Nothing in this cut needs a background run.

Before you hit record:

* three terminal tabs prepared, font bumped two sizes;
* a browser tab on Atlas, `harness` → Browse Collections → `edits`;
* phone on silent, no music playing in the room (they check audio playback);
* read the English lines twice out loud so the sixty seconds fit. They come to about
  150 words, which is a comfortable minute at demo pace.

---

## 0:00 – 0:07 · The claim

On screen: the top of the README, headline visible.

> This harness rewrites its own rules. A gate decides whether that made it better.

(Русская пометка: не начинай с объяснений. Одно предложение — и сразу экран.)

## 0:07 – 0:16 · The starting point

On screen: terminal 1, then run

```
python -m mh.cli status
```

> It starts with no rules, three tools, and answers seventy-one point nine percent of
> the questions it can see.

(Русская пометка: пока выполняется, ничего не говори. Три секунды паузы — нормально.)

## 0:16 – 0:36 · Five proposals, five refusals

On screen: terminal 2, run

```
python -m mh.cli edits
```

Scroll slowly through the ledger as you speak.

> Five generations of proposals. All five refused. One of them bought twelve points on
> the questions it could see, and two on the questions it could not. That is
> overfitting, and the gate names it. Another made the harness worse: seventy-eight
> percent down to sixty-two, with a p-value of zero point zero four.

(Русская пометка: вот это ядро всей минуты. Не спеши, листай журнал так, чтобы были
видны слова `rejected_insignificant` и `rejected_regression` с причинами.)

## 0:36 – 0:50 · It cannot grant itself a tool

On screen: terminal 3, the recorded output of `bash demo/gate_proof.sh`
(it is deterministic; showing the captured run is honest and fits the minute).

> The harness cannot give itself a tool. Here it loses aggregation: eighteen point
> eight percent. It asks for the right back and is refused. It tries a banned operator
> instead. Refused again. Restored by hand: sixty-eight point eight.

(Русская пометка: если хочешь показать живостью — запусти `gate_proof.sh` до записи и
держи его вывод в третьей вкладке. Вживую он идёт минутами и в минуту не влезет.)

## 0:50 – 0:58 · Where it remembers

On screen: Atlas tab, `harness.edits`, then the terminal running

```
python /root/hack/check_vector.py
```

> Everything it remembers lives in MongoDB. Runs, steps, lessons found by vector
> search, and every refused edit with its reason.

## 0:58 – 1:00 · The close

On screen: the repository URL.

> One command rolls any version back. github dot com slash dmitrypehovski slash
> mongo-harness.

---

## Word count check

The spoken lines are 148 words. At a calm demo pace that is 55 to 58 seconds, which
leaves a couple of seconds of breathing room. If you run over, cut the p-value
sentence first, then the "restored by hand" clause.

## The live demo, which is a different three minutes

The room demo is not the video. Suggested shape, in the same order, with room to
answer:

1. the claim, ten seconds;
2. `mh.cli status` and `mh.cli edits` live, one minute;
3. the trap in the table read aloud, the memorising edit and its two columns;
4. the rights experiment, with the recorded output;
5. Atlas open on `harness.edits`, so the memory is visible as data and not as a claim;
6. close on the rollback.

The question you should expect, and the answer: *did the harness improve itself, or did
you gate it?* The gate is part of the harness. What it cannot change is its own policy
for accepting changes, and that is the deliberate difference between self-improvement
and self-deception.
