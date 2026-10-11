# The 60-second video

The submission form asks for one minute with video **and** audio. Judges are in the
US, so the spoken lines are in English; the notes in parentheses are for you and are
not read out. Every command below was timed on the cluster: `status` 3.1s, `edits`
2.5s, `audit-ruler` about 5s. Nothing in this cut needs a background run.

Before you hit record:

* three terminal tabs prepared, font bumped two sizes;
* a browser tab on Atlas, `harness` → Browse Collections → `edits`;
* the recorded output of `bash demo/gate_proof.sh` waiting in the third tab;
* phone on silent, no music playing in the room (they check audio playback);
* read the English lines twice out loud so the sixty seconds fit. They come to about
  125 words, which is a comfortable minute at demo pace.

---

## 0:00 – 0:07 · The claim

On screen: the top of the README, headline visible.

> This harness rewrites its own rules. A gate decides whether that made it better.

(Русская пометка: не начинай с объяснений. Одно предложение — и сразу экран.)

## 0:07 – 0:14 · The starting point

On screen: terminal 1, then run

```
python -m mh.cli status
```

> It starts with no rules, three tools, seventy-one point nine percent.

(Русская пометка: пока выполняется, ничего не говори. Три секунды паузы — нормально.)

## 0:14 – 0:33 · Five proposals, five refusals

On screen: terminal 2, run

```
python -m mh.cli edits
```

Scroll slowly through the ledger as you speak.

> Five proposals, five refusals. One bought twelve points on the questions it could see
> and two on the questions it could not. That is overfitting, and the gate names it.

(Русская пометка: вот это ядро всей минуты. Не спеши, листай журнал так, чтобы были
видны слова `rejected_insignificant` и `rejected_regression` с причинами.)

## 0:33 – 0:44 · It cannot grant itself a tool

On screen: terminal 3, the recorded output of `bash demo/gate_proof.sh`
(it is deterministic; showing the captured run is honest and fits the minute).

> The harness cannot give itself a tool. It loses aggregation, falls to eighteen point
> eight percent, asks for the privilege back, and is refused.

(Русская пометка: вживую он идёт минутами, поэтому здесь записанный вывод.)

## 0:44 – 0:54 · It audits its own measuring instrument

On screen: terminal 1 again, run

```
python -m mh.cli audit-ruler
```

> It also audits the instrument it is measured with: the sandbox used to punish queries
> MongoDB accepts. It catches that in seconds, and fails loudly when the instrument
> breaks.

(Русская пометка: вот это то, чего нет ни у кого в зале. Держи на экране итоговые
строки `11 agreed, 0 diverged` и `5 refused, 0 admitted`.)

## 0:54 – 0:58 · Where it remembers, and the close

On screen: Atlas tab on `harness.edits`, then the repository URL.

> Everything it remembers lives in MongoDB, and any version rolls back with one command.
> github dot com slash dmitrypehovski slash mongo-harness.

---

## Word count check

The spoken lines are 125 words, which is 50 to 55 seconds at a calm demo pace. If you
overrun, cut the second half of the closing line first, then "and fails loudly when the
instrument breaks".

## The live demo, which is a different three minutes

The room demo is not the video. Suggested shape, in the same order, with room to
answer:

1. the claim, ten seconds;
2. `mh.cli status` and `mh.cli edits` live, one minute;
3. the trap in the table read aloud, the memorising edit and its two columns;
4. the rights experiment, with the recorded output;
5. `mh.cli audit-ruler` live, and `--inject regex` if there is time: the auditor
   catching the defect is a stronger thirty seconds than any claim about it;
6. Atlas open on `harness.edits`, so the memory is visible as data and not as a claim;
7. close on the rollback.

The question you should expect, and the answer: *did the harness improve itself, or did
you gate it?* The gate is part of the harness. What it cannot change is its own policy
for accepting changes, and that is the deliberate difference between self-improvement
and self-deception.

The second question, if a judge is sharp: *how do you know your measurements mean
anything?* That is `audit-ruler`. The honest part of the answer is that we did not know
for most of the day: we found the sandbox refusing valid queries, and the audit is what
that discovery turned into.
