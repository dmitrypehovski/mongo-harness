# The one-minute video

The submission video is **generated, not screen-recorded**, so that a reviewer can
re-render it and get the same result, and so that no number in it can drift from the
ledger. It is built with [Remotion](https://github.com/remotion-dev/remotion): React
components rendered to MP4 by a headless browser.

## Where every figure comes from

`src/harness-data.json` is extracted from the live Atlas ledger by the script in
`../scripts/export_video_data.py`. Nothing in the video is typed by hand:

* the current version, its tool list and its measured rates come from `harness.versions`
  and `harness.runs`;
* the five proposals, their before/after rates, the p-values and the verdict labels come
  from `harness.edits`, including the `evidence` sub-document the gate wrote;
* the sixteen audit verdicts come from running `mh.ruler.audit` against the cluster,
  in both the clean and the fault-injected state, during the export.

The narration was synthesised from the same script that the ledger describes. It is a
synthetic voice, not a recorded one: the rules ask for a demo video with working audio,
and a synthetic track cannot fail to record in a noisy room.

## Re-rendering it

```bash
npm install
npm run render      # writes out/harness-demo.mp4
npm run still       # one frame, for checking a layout
```

The timeline is in `src/timeline.ts`: every cut is expressed in seconds and converted to
frames in one place, so the picture stays locked to the narration.

## What the video shows, in order

| seconds | scene | source of the numbers |
|---|---|---|
| 0–7 | the claim: a harness that rewrites its own rules, and a gate | — |
| 7–12 | the starting version: no rules, three tools, 71.9% | `harness.versions`, `harness.runs` |
| 12–31 | five proposals, five refusals, with rates and p-values | `harness.edits` |
| 31–41 | the tool taken away, asked for, refused, and restored by a human | `demo/gate_proof.sh` output |
| 41–51 | the instrument audit, then the same audit with the defect injected | `mh.ruler` |
| 51–60 | where it remembers, and the repository | `harness.*` counts |
