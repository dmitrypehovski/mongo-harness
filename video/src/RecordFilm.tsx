import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import "@fontsource/archivo/500.css";
import "@fontsource/archivo/700.css";
import "@fontsource/courier-prime/400.css";
import "@fontsource/courier-prime/700.css";
import data from "./harness-data.json";
import takes from "./terminal-takes.json";
import { COLORS, FONTS, KICKER, MEASURE, MEASURE_DIM, STATEMENT } from "./record-tokens";
import { APP_STATES, ENVELOPE_BEATS, LOOP_STAGES, SCENES, TERMINAL_CUT, TOTAL_FRAMES, VOICE_START } from "./timeline";

/* ---------------------------------------------------------------- primitives */

const pct = (value: number | null | undefined) =>
  value === null || value === undefined ? "--" : `${(value * 100).toFixed(1)}%`;

const useReveal = (delayFrames = 0, distance = 10) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame - delayFrames, [0, 13], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: (v) => 1 - Math.pow(1 - v, 3),
  });
  return { opacity: progress, transform: `translateY(${(1 - progress) * distance}px)` };
};

const Reveal: React.FC<{
  delay?: number;
  distance?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ delay = 0, distance = 10, children, style }) => (
  <div style={{ ...useReveal(delay, distance), ...style }}>{children}</div>
);

const Rule: React.FC<{ delay?: number; width?: number | string }> = ({ delay = 0, width = "100%" }) => {
  const frame = useCurrentFrame();
  const grow = interpolate(frame - delay, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        height: 1,
        width,
        background: COLORS.ruleBright,
        transform: `scaleX(${grow})`,
        transformOrigin: "left center",
      }}
    />
  );
};

/** The signature: the gate's word, stamped, landing the way a stamp does. */
const Stamp: React.FC<{ word: string; delay?: number; colour?: string; size?: number }> = ({
  word,
  delay = 0,
  colour = COLORS.stamp,
  size = 20,
}) => {
  const frame = useCurrentFrame();
  const land = interpolate(frame - delay, [0, 5, 9], [1.45, 0.96, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = interpolate(frame - delay, [0, 4], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <span
      style={{
        display: "inline-block",
        opacity,
        transform: `rotate(-3.2deg) scale(${land})`,
        border: `2px solid ${colour}`,
        borderRadius: 2,
        padding: "3px 9px 2px",
        fontFamily: FONTS.record,
        fontWeight: 700,
        fontSize: size,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        color: colour,
        whiteSpace: "nowrap",
      }}
    >
      {word}
    </span>
  );
};

const Header: React.FC<{ record: string; right: string }> = ({ record, right }) => (
  <div
    style={{
      display: "flex",
      justifyContent: "space-between",
      gap: 24,
      fontFamily: FONTS.record,
      fontSize: 17,
      letterSpacing: "0.16em",
      textTransform: "uppercase",
      color: COLORS.measure,
      paddingBottom: 14,
      borderBottom: `1px solid ${COLORS.rule}`,
    }}
  >
    <span>{record}</span>
    <span>{right}</span>
  </div>
);

const Frame: React.FC<{ record: string; right: string; children: React.ReactNode }> = ({
  record,
  right,
  children,
}) => (
  <AbsoluteFill style={{ background: COLORS.paper }}>
    <div style={{ padding: "54px 92px 58px", height: "100%", boxSizing: "border-box" }}>
      <Header record={record} right={right} />
      <div style={{ marginTop: 30, display: "flex", flexDirection: "column", height: "calc(100% - 82px)" }}>
        {children}
      </div>
    </div>
  </AbsoluteFill>
);

/* --------------------------------------------------------- 1 · what this is */

const TitleScene: React.FC = () => (
  <Frame record="Record of self-edits" right="11 October 2026 · atlas sandbox">
    <div style={{ marginTop: "auto" }} />
    <Reveal delay={2}>
      <div
        style={{
          fontFamily: FONTS.display,
          fontWeight: 700,
          fontSize: 104,
          lineHeight: 1.0,
          letterSpacing: "-0.04em",
          color: COLORS.ink,
        }}
      >
        The harness that earns its edits
      </div>
    </Reveal>
    <div style={{ height: 30, width: 900 }}>
      <Rule delay={14} />
    </div>
    <Reveal delay={20}>
      <div style={{ fontFamily: FONTS.display, fontWeight: 500, fontSize: 30, color: COLORS.measure }}>
        inside, in sixty seconds · and you can try it
      </div>
    </Reveal>
    <div style={{ marginTop: "auto" }} />
  </Frame>
);

/* ------------------------------------------------------------ 2 · the loop */

const LoopScene: React.FC = () => {
  const worse = data.edits.find((edit) => edit.decision === "rejected_regression") || data.edits[0];
  const stages = [
    {
      n: "01",
      what: "The agent proposes a change to its own rules",
      artefact: `"${worse.strategy}"`,
      mono: true,
    },
    {
      n: "02",
      what: "The gate measures the version it has now",
      artefact: `${data.current.train} can see · ${data.current.holdout} cannot`,
    },
    {
      n: "03",
      what: "And the version it is offered",
      artefact: `${pct(worse.train_after)} can see · ${pct(worse.holdout_after)} cannot`,
    },
    {
      n: "04",
      what: "It pairs the cases and tests the difference",
      artefact: `${worse.gained ?? 2} gained · ${worse.lost ?? 18} lost · p = ${worse.p_value ?? 0.04}`,
    },
    {
      n: "05",
      what: "Then it writes the verdict, and its reason, into MongoDB",
      artefact: "",
    },
  ];
  return (
    <Frame record="Record of self-edits · 02" right="how it works inside">
      <div style={{ ...KICKER }}>the loop, on one real proposal</div>
      <div style={{ height: 22 }} />
      {stages.map((stage, index) => (
        <Reveal key={stage.n} delay={Math.round(LOOP_STAGES[index] * 30)}>
          <div
            style={{
              borderTop: `1px solid ${COLORS.rule}`,
              display: "grid",
              gridTemplateColumns: "58px 1fr 620px",
              gap: 18,
              alignItems: "baseline",
              padding: "13px 0",
            }}
          >
            <span style={{ ...MEASURE_DIM, color: COLORS.measure, fontSize: 19 }}>{stage.n}</span>
            <span style={{ fontFamily: FONTS.display, fontWeight: 500, fontSize: 25, color: COLORS.ink }}>
              {stage.what}
            </span>
            <span
              style={{
                ...MEASURE,
                fontSize: 20,
                textAlign: "right",
                color: index === 2 ? COLORS.stamp : COLORS.ink,
              }}
            >
              {stage.artefact}
            </span>
          </div>
        </Reveal>
      ))}
      <Reveal delay={Math.round(LOOP_STAGES[5] * 30)}>
        <div
          style={{
            borderTop: `1px solid ${COLORS.rule}`,
            display: "grid",
            gridTemplateColumns: "58px 1fr auto",
            gap: 18,
            alignItems: "center",
            padding: "16px 0",
          }}
        >
          <span style={{ ...MEASURE_DIM, color: COLORS.measure, fontSize: 19 }}>→</span>
          <span style={{ ...MEASURE_DIM, fontSize: 20 }}>{worse.reason}</span>
          <Stamp word={worse.decision.replace("rejected_", "")} delay={Math.round(LOOP_STAGES[5] * 30) + 10} size={19} />
        </div>
      </Reveal>
      <div style={{ marginTop: "auto" }} />
      <Reveal delay={Math.round(LOOP_STAGES[5] * 30) + 40}>
        <div style={{ fontFamily: FONTS.display, fontWeight: 500, fontSize: 31, color: COLORS.ink }}>
          Five proposals. Five refusals. Nothing about this agent is judged on its own word.
        </div>
      </Reveal>
    </Frame>
  );
};

/* -------------------------------------------------------- 3 · the real output */

const TerminalPanel: React.FC<{ lines: string[]; start?: number; perLine?: number; caret?: boolean }> = ({
  lines,
  start = 0,
  perLine = 3,
  caret = true,
}) => {
  const frame = useCurrentFrame();
  const shown = Math.max(0, Math.floor((frame - start) / perLine));
  const opacity = interpolate(frame - start, [0, 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ opacity }}>
      {lines.slice(0, shown).map((line, index) => (
        <div
          key={`${index}-${line.slice(0, 12)}`}
          style={{
            ...MEASURE,
            fontSize: 19,
            lineHeight: 1.5,
            whiteSpace: "pre",
            color: index === shown - 1 && caret ? COLORS.ink : line.includes("FAIL") ? COLORS.stamp : COLORS.ink,
          }}
        >
          {line}
          {index === shown - 1 && caret ? <span style={{ opacity: 0.7 }}>▌</span> : null}
        </div>
      ))}
    </div>
  );
};

const TerminalScene: React.FC = () => {
  const editsLines = takes.edits.lines.map((line: string) => line.replace(/^ {2}/, ""));
  const start = editsLines.findIndex((line: string) => line.includes("rejected_regression"));
  const block = editsLines.slice(start, start + 5).map((line: string) =>
    line.length > 150 ? `${line.slice(0, 147)}…` : line
  );
  const fails = takes.audit_injected.lines.filter((line: string) => line.includes("FAIL"));
  const summary = (take: { lines: string[] }) => {
    const line = take.lines.find((candidate: string) => candidate.trim().startsWith('{"defects"'));
    return line ? JSON.parse(line.trim()) : { defects: 0, probes: 0 };
  };
  const clean = summary(takes.audit_clean as { lines: string[] });
  const injected = summary(takes.audit_injected as { lines: string[] });

  return (
    <Frame record="Record of self-edits · 03" right="the real output, not a mock-up">
      <div style={{ ...KICKER }}>$ python -m mh.cli edits</div>
      <div style={{ height: 18 }} />
      <Reveal delay={4}>
        <div style={{ ...MEASURE_DIM, color: COLORS.measure, fontSize: 19 }}>
          the last refusal, verbatim from the ledger
        </div>
      </Reveal>
      <div style={{ height: 14 }} />
      <TerminalPanel lines={block} start={8} perLine={6} />

      <div style={{ height: 26 }} />
      <Reveal delay={TERMINAL_CUT}>
        <div style={{ ...KICKER }}>$ python -m mh.cli audit-ruler --inject regex</div>
      </Reveal>
      <div style={{ height: 16 }} />
      <TerminalPanel lines={fails.map((line: string) => (line.length > 132 ? `${line.slice(0, 129)}…` : line))} start={TERMINAL_CUT + 12} perLine={9} />

      <div style={{ marginTop: "auto" }} />
      <Reveal delay={TERMINAL_CUT + 90}>
        <div style={{ fontFamily: FONTS.display, fontWeight: 500, fontSize: 28, color: COLORS.ink, maxWidth: 1500 }}>
          The tool's own summary. Healthy sandbox: {clean.probes - clean.defects} of {clean.probes} probes
          agree, {clean.defects} defects. One defect injected: {injected.defects} of {injected.probes} probes
          diverge, and every one of them is a query the database would have accepted. The ruler was
          lying, and the check said so.
        </div>
      </Reveal>
    </Frame>
  );
};

/* ------------------------------------------------------------- 4 · the product */

const AppScene: React.FC = () => {
  const states = [
    { file: "app-empty.png", caption: "The product, running against the live cluster." },
    { file: "app-typed.png", caption: "Ask a question in plain language." },
    {
      file: "app-answered.png",
      caption: "It writes the query, runs it, and says whether the rows match the reference answer.",
    },
  ];
  const frame = useCurrentFrame();
  const active = states.reduce((best, _state, index) => (frame >= APP_STATES[index] * 30 ? index : best), 0);
  const local = frame - Math.round(APP_STATES[active] * 30);
  const fade = interpolate(local, [0, 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const zoom = interpolate(local, [0, 120], [1.012, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <Frame record="Record of self-edits · 04" right="try it: dmitrypehovski.github.io/mongo-harness">
      <div style={{ ...KICKER }}>the live product, three real moments</div>
      <div style={{ height: 20 }} />
      <div style={{ position: "relative", border: `1px solid ${COLORS.rule}`, background: COLORS.paperDeep, padding: 8 }}>
        <div style={{ position: "relative", height: 640, overflow: "hidden" }}>
          {states.map((state, index) => (
            <Img
              key={state.file}
              src={staticFile(state.file)}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                opacity: index === active ? fade : 0,
                transform: `scale(${index === active ? zoom : 1})`,
                transformOrigin: "top left",
                display: "block",
              }}
            />
          ))}
        </div>
      </div>
      <div style={{ height: 18 }} />
      <Reveal delay={6} distance={4}>
        <div style={{ fontFamily: FONTS.display, fontWeight: 500, fontSize: 26, color: COLORS.ink }}>
          {states[active].caption}
        </div>
      </Reveal>
      <div style={{ marginTop: "auto" }} />
      <Reveal delay={Math.round(APP_STATES[2] * 30) + 40}>
        <div style={{ ...MEASURE, fontSize: 26, color: COLORS.ink }}>
          ask it yourself: dmitrypehovski.github.io/mongo-harness
        </div>
      </Reveal>
    </Frame>
  );
};

/* ------------------------------------------------------------ 5 · the envelope */

const EnvelopeScene: React.FC = () => {
  const beats = [
    { what: "the aggregate tool is revoked", result: "18.8% · 12.0%", kind: "bad" as const },
    { what: "proposal: give the tool back", result: "refused", kind: "stamp" as const },
    { what: "proposal: use $where instead", result: "refused", kind: "stamp" as const },
    { what: "restored by a human, not by the harness", result: "68.8% · 80.0%", kind: "pass" as const },
  ];
  return (
    <Frame record="Record of self-edits · 05" right="the envelope of permissions">
      <Reveal delay={2}>
        <div style={{ ...STATEMENT, fontSize: 44 }}>It cannot give itself a tool.</div>
      </Reveal>
      <div style={{ height: 20 }}>
        <Rule delay={8} />
      </div>
      {beats.map((beat, index) => {
        const delay = Math.round(ENVELOPE_BEATS[index] * 30) + 8;
        return (
          <Reveal key={beat.what} delay={delay}>
            <div
              style={{
                borderTop: `1px solid ${COLORS.rule}`,
                display: "grid",
                gridTemplateColumns: "1fr 420px",
                gap: 20,
                alignItems: "baseline",
                padding: "14px 0",
              }}
            >
              <span style={{ fontFamily: FONTS.display, fontWeight: 500, fontSize: 25, color: COLORS.ink }}>
                {beat.what}
              </span>
              <span style={{ textAlign: "right" }}>
                {beat.kind === "stamp" ? (
                  <Stamp word={beat.result} delay={delay + 8} size={19} />
                ) : (
                  <span
                    style={{
                      ...MEASURE,
                      fontSize: 21,
                      color: beat.kind === "pass" ? COLORS.pass : COLORS.stamp,
                    }}
                  >
                    {beat.result}
                  </span>
                )}
              </span>
            </div>
          </Reveal>
        );
      })}
      <div style={{ marginTop: "auto" }} />
      <Reveal delay={Math.round(ENVELOPE_BEATS[3] * 30) + 20}>
        <div style={{ fontFamily: FONTS.display, fontWeight: 500, fontSize: 26, color: COLORS.ink, maxWidth: 1450 }}>
          The gate is not a sentence in the prompt. It is a branch in the code path.
        </div>
      </Reveal>
    </Frame>
  );
};

/* --------------------------------------------------------------- 6 · the close */

const CloseScene: React.FC = () => {
  const { counts } = data;
  return (
    <Frame record="Record of self-edits · 06" right="the short version. The ledger is longer.">
      <div style={{ marginTop: "auto" }} />
      <Reveal delay={2}>
        <div style={{ ...STATEMENT, fontSize: 44 }}>Everything it remembers lives in MongoDB.</div>
      </Reveal>
      <div style={{ height: 22, width: 1200 }}>
        <Rule delay={10} />
      </div>
      <div style={{ height: 20 }} />
      <Reveal delay={14}>
        <div style={{ ...MEASURE_DIM, fontSize: 21 }}>
          {counts.runs} runs · {counts.steps} steps · {counts.lessons} lessons · {counts.edits} refused edits
        </div>
      </Reveal>
      <div style={{ height: 24 }} />
      <Reveal delay={22}>
        <div
          style={{
            fontFamily: FONTS.display,
            fontWeight: 500,
            fontSize: 27,
            color: COLORS.ink,
            maxWidth: 1500,
            lineHeight: 1.42,
          }}
        >
          The gate and the audit are separate modules. Nothing in them knows about this agent,
          so any harness can put them around its own.
        </div>
      </Reveal>
      <div style={{ height: 28 }} />
      <Reveal delay={32}>
        <div style={{ ...MEASURE, fontSize: 27, color: COLORS.ink }}>
          try it: dmitrypehovski.github.io/mongo-harness
        </div>
      </Reveal>
      <Reveal delay={38}>
        <div style={{ ...MEASURE, fontSize: 27, color: COLORS.ink, marginTop: 8 }}>
          github.com/dmitrypehovski/mongo-harness
        </div>
      </Reveal>
      <div style={{ marginTop: "auto" }} />
      <Reveal delay={46}>
        <div style={{ ...MEASURE_DIM, fontSize: 18 }}>
          built during the event · MongoDB Atlas sandbox · sample_mflix
        </div>
      </Reveal>
    </Frame>
  );
};

/* ------------------------------------------------------------------- the film */

export const RecordFilm: React.FC<{ voice?: string }> = ({ voice = "voice.mp3" }) => {
  const span = (scene: { from: number; to: number }) => scene.to - scene.from;
  return (
    <AbsoluteFill style={{ background: COLORS.paper }}>
      <Sequence from={VOICE_START} durationInFrames={TOTAL_FRAMES - VOICE_START}>
        <Audio src={staticFile(voice)} />
      </Sequence>
      <Sequence from={SCENES.title.from} durationInFrames={span(SCENES.title)}>
        <TitleScene />
      </Sequence>
      <Sequence from={SCENES.loop.from} durationInFrames={span(SCENES.loop)}>
        <LoopScene />
      </Sequence>
      <Sequence from={SCENES.terminal.from} durationInFrames={span(SCENES.terminal)}>
        <TerminalScene />
      </Sequence>
      <Sequence from={SCENES.app.from} durationInFrames={span(SCENES.app)}>
        <AppScene />
      </Sequence>
      <Sequence from={SCENES.envelope.from} durationInFrames={span(SCENES.envelope)}>
        <EnvelopeScene />
      </Sequence>
      <Sequence from={SCENES.close.from} durationInFrames={span(SCENES.close)}>
        <CloseScene />
      </Sequence>
    </AbsoluteFill>
  );
};
