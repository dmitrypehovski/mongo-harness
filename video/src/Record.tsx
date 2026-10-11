import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import "@fontsource/archivo/500.css";
import "@fontsource/archivo/700.css";
import "@fontsource/courier-prime/400.css";
import "@fontsource/courier-prime/700.css";
import data from "./harness-data.json";
import { COLORS, FONTS, KICKER, MEASURE, MEASURE_DIM, STATEMENT } from "./record-tokens";
import {
  LEDGER_HEADLINE,
  LEDGER_ROWS,
  RIGHTS_BEATS,
  RULER_CUT,
  SCENES,
  TOTAL_FRAMES,
  VOICE_START,
} from "./timeline";

/* ---------------------------------------------------------------- primitives */

const pct = (value: number | null | undefined) =>
  value === null || value === undefined ? "--" : `${(value * 100).toFixed(1)}%`;

/** Fade and a short rise. The sheet is paper: it does not bounce. */
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

/**
 * The signature: the gate's word, stamped. It lands with a small overshoot, the way a
 * stamp does, and it is the only place in the film where vermilion appears.
 */
const Stamp: React.FC<{ word: string; delay?: number; colour?: string; size?: number }> = ({
  word,
  delay = 0,
  colour = COLORS.stamp,
  size = 20,
}) => {
  const frame = useCurrentFrame();
  const land = interpolate(frame - delay, [0, 5, 9], [1.5, 0.96, 1], {
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

const Mark: React.FC<{ delay?: number }> = ({ delay = 0 }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame - delay, [0, 6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <span
      style={{
        opacity,
        border: `2px solid ${COLORS.pass}`,
        borderRadius: 2,
        padding: "3px 9px 2px",
        fontFamily: FONTS.record,
        fontWeight: 700,
        fontSize: 20,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        color: COLORS.pass,
      }}
    >
      restored
    </span>
  );
};

/** The form strip at the top of every sheet: a record has a header. */
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

const Frame: React.FC<{
  record: string;
  right: string;
  children: React.ReactNode;
}> = ({ record, right, children }) => (
  <AbsoluteFill style={{ background: COLORS.paper }}>
    <div style={{ padding: "58px 96px 64px", height: "100%", boxSizing: "border-box" }}>
      <Header record={record} right={right} />
      <div style={{ marginTop: 34, display: "flex", flexDirection: "column", height: "calc(100% - 86px)" }}>
        {children}
      </div>
    </div>
  </AbsoluteFill>
);

const Headline: React.FC<{ children: React.ReactNode; delay?: number; size?: number }> = ({
  children,
  delay = 6,
  size,
}) => (
  <Reveal delay={delay}>
    <div style={{ ...STATEMENT, fontSize: size ?? STATEMENT.fontSize }}>{children}</div>
  </Reveal>
);

/* -------------------------------------------------------------- 1 · the record */

const TitleScene: React.FC = () => (
  <Frame record="Record of self-edits" right="11 October 2026 · atlas sandbox · cluster0">
    <div style={{ marginTop: "auto" }} />
    <Reveal delay={4} distance={6}>
      <div style={{ ...KICKER }}>Harness engineering · statement one</div>
    </Reveal>
    <div style={{ height: 26 }} />
    <Reveal delay={8}>
      <div
        style={{
          fontFamily: FONTS.display,
          fontWeight: 700,
          fontSize: 96,
          lineHeight: 1.0,
          letterSpacing: "-0.035em",
          color: COLORS.ink,
        }}
      >
        The harness that
        <br />
        earns its edits
      </div>
    </Reveal>
    <div style={{ height: 40, width: 780 }}>
      <Rule delay={18} />
    </div>
    <Reveal delay={24}>
      <div
        style={{
          fontFamily: FONTS.display,
          fontWeight: 500,
          fontSize: 29,
          lineHeight: 1.44,
          color: COLORS.measure,
          maxWidth: 1000,
        }}
      >
        An agent answers questions about a MongoDB database in plain language. It also
        proposes changes to its own rules. A gate measures both versions and decides
        whether any of those changes made it better. It refused all five.
      </div>
    </Reveal>
    <div style={{ marginTop: "auto" }} />
    <Reveal delay={36}>
      <div style={{ ...MEASURE_DIM, fontSize: 19 }}>
        57 questions · sample_mflix · one document per version · every refusal keeps its reason
      </div>
    </Reveal>
  </Frame>
);

/* ------------------------------------------------------------- 2 · the product */

const ProductScene: React.FC = () => {
  const frame = useCurrentFrame();
  const rise = interpolate(frame, [0, 26], [14, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: (v) => 1 - Math.pow(1 - v, 3),
  });
  const opacity = interpolate(frame, [0, 20], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <Frame record="Record of self-edits · 02" right="the same ledger, read in a browser">
      <Headline delay={4} size={44}>
        Ask it something, or overrule it.
      </Headline>
      <div style={{ height: 26 }} />
      <div style={{ display: "flex", gap: 40, alignItems: "flex-start", flex: 1 }}>
        <div
          style={{
            width: 1010,
            flexShrink: 0,
            border: `1px solid ${COLORS.rule}`,
            padding: 10,
            background: COLORS.paperDeep,
            opacity,
            transform: `translateY(${rise}px)`,
          }}
        >
          <Img src={staticFile("app-surface.png")} style={{ width: "100%", display: "block" }} />
        </div>
        <div style={{ paddingTop: 6 }}>
          <Reveal delay={20}>
            <div style={{ ...MEASURE, fontSize: 21 }}>
              It writes one query,
              <br />
              runs it against the live collection,
              <br />
              and compares the rows with a
              <br />
              reference answer.
            </div>
          </Reveal>
          <div style={{ height: 26 }} />
          <Reveal delay={34}>
            <div style={{ ...MEASURE_DIM, fontSize: 20, lineHeight: 1.6 }}>
              The gate's last refusal is on the
              <br />
              same page, with the arithmetic
              <br />
              behind it, and a person can
              <br />
              overrule it. That decision is
              <br />
              written to MongoDB too.
            </div>
          </Reveal>
        </div>
      </div>
      <div style={{ marginTop: "auto" }}>
        <Reveal delay={48}>
          <div style={{ ...MEASURE_DIM, fontSize: 19 }}>
            asked live while recording: rows back in 1.8 s · 57 questions in the suite ·
            one decision by a person already in the ledger
          </div>
        </Reveal>
      </div>
    </Frame>
  );
};

/* -------------------------------------------------------------- 3 · the ledger */

const LedgerScene: React.FC = () => {
  const rows = data.edits;
  return (
    <Frame record="Record of self-edits · 03" right="five proposals, five decisions">
      <Reveal delay={4}>
        <div style={{ ...STATEMENT, fontSize: 40, color: COLORS.measure }}>
          Two versions, measured on cases it can see
          <br />
          and cases it cannot.
        </div>
      </Reveal>
      <div style={{ height: 24 }}>
        <Rule delay={10} />
      </div>
      <div style={{ height: 20 }} />
      <Reveal delay={LEDGER_HEADLINE}>
        <div style={{ ...STATEMENT, fontSize: 46 }}>Five proposals. Five refusals.</div>
      </Reveal>
      <div style={{ height: 18 }} />
      <Reveal delay={LEDGER_HEADLINE + 6}>
        <div
          style={{
            ...MEASURE_DIM,
            fontSize: 16,
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            display: "grid",
            gridTemplateColumns: "1fr 250px 250px",
            gap: 18,
            paddingBottom: 10,
          }}
        >
          <span>proposal</span>
          <span style={{ textAlign: "right" }}>cases it can see</span>
          <span style={{ textAlign: "right" }}>cases it cannot</span>
        </div>
      </Reveal>
      {rows.map((row, index) => {
        const worse = row.decision === "rejected_regression";
        return (
          <Reveal key={row.strategy} delay={LEDGER_ROWS + index * 34}>
            <div
              style={{
                borderTop: `1px solid ${COLORS.rule}`,
                display: "grid",
                gridTemplateColumns: "1fr 250px 250px",
                gap: 18,
                alignItems: "center",
                padding: "13px 0 11px",
              }}
            >
              <span
                style={{
                  fontFamily: FONTS.display,
                  fontWeight: 500,
                  fontSize: 25,
                  color: COLORS.ink,
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                }}
              >
                <Stamp
                  word={row.decision.replace("rejected_", "")}
                  delay={LEDGER_ROWS + index * 34 + 12}
                  colour={worse ? COLORS.stamp : COLORS.stamp}
                  size={15}
                />
                {row.strategy}
              </span>
              <span style={{ ...MEASURE, textAlign: "right", fontSize: 21 }}>
                <span style={{ color: COLORS.measure }}>{pct(row.train_before)} </span>
                {pct(row.train_after)}
              </span>
              <span
                style={{
                  ...MEASURE,
                  textAlign: "right",
                  fontSize: 21,
                  color: worse ? COLORS.stamp : COLORS.ink,
                }}
              >
                <span style={{ color: COLORS.measure }}>{pct(row.holdout_before)} </span>
                {pct(row.holdout_after)}
                {row.p_value !== null && row.p_value !== undefined ? (
                  <span style={{ color: COLORS.measure }}> p={row.p_value.toFixed(2)}</span>
                ) : null}
              </span>
            </div>
          </Reveal>
        );
      })}
      <div style={{ marginTop: "auto" }} />
      <Reveal delay={LEDGER_ROWS + 156}>
        <div
          style={{
            fontFamily: FONTS.display,
            fontWeight: 500,
            fontSize: 26,
            color: COLORS.ink,
            maxWidth: 1500,
            lineHeight: 1.42,
          }}
        >
          The best-looking proposal gained 3.1 points where it could see and 6.0 where it
          could not. The gate called that noise and refused it.
        </div>
      </Reveal>
      <Reveal delay={LEDGER_ROWS + 196}>
        <div style={{ marginTop: 22, borderLeft: `2px solid ${COLORS.stamp}`, paddingLeft: 20 }}>
          <div style={{ ...MEASURE_DIM, fontSize: 15, letterSpacing: "0.16em", textTransform: "uppercase" }}>
            the gate, in the ledger
          </div>
          <div style={{ ...MEASURE_DIM, fontSize: 20, marginTop: 8 }}>{rows[rows.length - 1].reason}</div>
        </div>
      </Reveal>
    </Frame>
  );
};

/* ------------------------------------------------------------ 4 · the envelope */

const RightsScene: React.FC = () => {
  const beats = [
    {
      what: "the aggregate tool is revoked",
      extra: "47 questions refused before any model call",
      result: "18.8% sees · 12.0% cannot",
      kind: "bad" as const,
    },
    {
      what: "proposal: give the tool back",
      extra: "the version widens its own tool access",
      result: "refused",
      kind: "stamp" as const,
    },
    {
      what: "proposal: use $where instead",
      extra: "server-side JavaScript is not a tool it may grant itself",
      result: "refused",
      kind: "stamp" as const,
    },
    {
      what: "restored by a human, not by the harness",
      extra: "",
      result: "68.8% sees · 80.0% cannot",
      kind: "pass" as const,
    },
  ];
  return (
    <Frame record="Record of self-edits · 04" right="the envelope of permissions">
      <Headline delay={4} size={46}>
        It cannot give itself a tool.
      </Headline>
      <div style={{ height: 24 }}>
        <Rule delay={10} />
      </div>
      {beats.map((beat, index) => {
        const delay = Math.round(RIGHTS_BEATS[index] * 30) + 14;
        return (
          <Reveal key={beat.what} delay={delay}>
            <div
              style={{
                borderTop: `1px solid ${COLORS.rule}`,
                display: "grid",
                gridTemplateColumns: "1fr 460px",
                gap: 24,
                alignItems: "baseline",
                padding: "15px 0",
              }}
            >
              <span
                style={{ fontFamily: FONTS.display, fontWeight: 500, fontSize: 25, color: COLORS.ink }}
              >
                {beat.what}
                {beat.extra ? (
                  <span style={{ display: "block", fontFamily: FONTS.record, fontSize: 18, color: COLORS.measure, marginTop: 5 }}>
                    {beat.extra}
                  </span>
                ) : null}
              </span>
              <span style={{ textAlign: "right" }}>
                {beat.kind === "stamp" ? (
                  <Stamp word={beat.result} delay={delay + 10} size={19} />
                ) : beat.kind === "pass" ? (
                  <span style={{ display: "inline-flex", alignItems: "baseline", gap: 14 }}>
                    <Mark delay={delay + 10} />
                    <span style={{ ...MEASURE, fontSize: 21, color: COLORS.ink }}>{beat.result}</span>
                  </span>
                ) : (
                  <span style={{ ...MEASURE, fontSize: 21, color: COLORS.stamp }}>{beat.result}</span>
                )}
              </span>
            </div>
          </Reveal>
        );
      })}
      <div style={{ marginTop: "auto" }} />
      <Reveal delay={Math.round(RIGHTS_BEATS[3] * 30) + 26}>
        <div style={{ fontFamily: FONTS.display, fontWeight: 500, fontSize: 26, color: COLORS.ink, maxWidth: 1450 }}>
          The gate is not a sentence in the prompt. It is a branch in the code path, and no
          model can talk its way past it.
        </div>
      </Reveal>
    </Frame>
  );
};

/* ---------------------------------------------------------- 5 · the instrument */

const RulerScene: React.FC = () => {
  const frame = useCurrentFrame();
  const injected = frame >= RULER_CUT;
  const constructs = data.audit.injected
    .filter((line) => line.trim().startsWith("*"))
    .map((line) => line.trim().slice(1).split(":")[0].trim());

  return (
    <Frame record="Record of self-edits · 05" right="the instrument is checked too">
      <Headline delay={4} size={46}>
        And it audits the ruler it is measured with.
      </Headline>
      <div style={{ height: 24, width: 1150 }}>
        <Rule delay={10} />
      </div>
      <div style={{ height: 26 }} />
      {!injected ? (
        <>
          <Reveal delay={16}>
            <div style={{ ...MEASURE_DIM, color: COLORS.measure }}>$ python -m mh.cli audit-ruler</div>
          </Reveal>
          <div style={{ height: 14 }} />
          <Reveal delay={22}>
            <div style={{ ...MEASURE, fontSize: 21, color: COLORS.pass }}>
              11 equivalence probes: 11 agreed, 0 diverged
              <br />
              5 policy probes: 5 refused, 0 admitted
            </div>
          </Reveal>
        </>
      ) : (
        <>
          <Reveal delay={0} distance={0}>
            <div style={{ ...MEASURE_DIM, color: COLORS.measure }}>
              $ python -m mh.cli audit-ruler --inject regex
            </div>
          </Reveal>
          <div style={{ height: 14 }} />
          <Reveal delay={3} distance={0}>
            <div style={{ ...MEASURE, fontSize: 21, color: COLORS.stamp }}>
              11 equivalence probes: 7 agreed, 4 diverged
              <br />
              The instrument is lying. Fix this before trusting any measurement.
            </div>
          </Reveal>
          <div style={{ height: 18 }} />
          <span>
            <Stamp word="diverged" delay={RULER_CUT + 12} size={19} />
          </span>
          <div style={{ height: 16 }} />
          {constructs.slice(0, 3).map((name, index) => (
            <Reveal key={name} delay={RULER_CUT + 20 + index * 5} distance={6}>
              <div style={{ ...MEASURE_DIM, color: COLORS.stamp, fontSize: 20 }}>{name}</div>
            </Reveal>
          ))}
        </>
      )}
      <div style={{ marginTop: "auto" }} />
      <Reveal delay={injected ? RULER_CUT + 30 : 44}>
        <div style={{ fontFamily: FONTS.display, fontWeight: 500, fontSize: 25, color: COLORS.ink, maxWidth: 1500 }}>
          Sixteen probes, no model involved, and a switch that proves the auditor can fail.
        </div>
      </Reveal>
    </Frame>
  );
};

/* ----------------------------------------------------------------- 6 · the close */

const CloseScene: React.FC = () => {
  const { counts } = data;
  return (
    <Frame record="Record of self-edits · 06" right="this is the short version. The ledger is longer.">
      <div style={{ marginTop: "auto" }} />
      <Headline delay={4} size={46}>
        Everything it remembers lives in MongoDB.
      </Headline>
      <div style={{ height: 26, width: 1200 }}>
        <Rule delay={12} />
      </div>
      <div style={{ height: 24 }} />
      <Reveal delay={18}>
        <div style={{ ...MEASURE_DIM, fontSize: 21 }}>
          {counts.runs} runs · {counts.steps} steps · {counts.lessons} lessons · {counts.edits} refused
          edits · one document per version
        </div>
      </Reveal>
      <div style={{ height: 26 }} />
      <Reveal delay={26}>
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
          The gate and the audit are separate modules. Nothing in them knows about this
          agent, so any harness can put them around its own.
        </div>
      </Reveal>
      <div style={{ height: 30 }} />
      <Reveal delay={36}>
        <div style={{ ...MEASURE, fontSize: 32, color: COLORS.ink }}>
          github.com/dmitrypehovski/mongo-harness
        </div>
      </Reveal>
      <div style={{ marginTop: "auto" }} />
      <Reveal delay={44}>
        <div style={{ ...MEASURE_DIM, fontSize: 18 }}>
          built during the event · MongoDB Atlas sandbox · sample_mflix
        </div>
      </Reveal>
    </Frame>
  );
};

/* --------------------------------------------------------------------- the film */

export const Record: React.FC<{ voice?: string }> = ({ voice = "voice.mp3" }) => {
  const span = (scene: { from: number; to: number }) => scene.to - scene.from;
  return (
    <AbsoluteFill style={{ background: COLORS.paper }}>
      <Sequence from={VOICE_START} durationInFrames={TOTAL_FRAMES - VOICE_START}>
        <Audio src={staticFile(voice)} />
      </Sequence>
      <Sequence from={SCENES.title.from} durationInFrames={span(SCENES.title)}>
        <TitleScene />
      </Sequence>
      <Sequence from={SCENES.product.from} durationInFrames={span(SCENES.product)}>
        <ProductScene />
      </Sequence>
      <Sequence from={SCENES.ledger.from} durationInFrames={span(SCENES.ledger)}>
        <LedgerScene />
      </Sequence>
      <Sequence from={SCENES.rights.from} durationInFrames={span(SCENES.rights)}>
        <RightsScene />
      </Sequence>
      <Sequence from={SCENES.ruler.from} durationInFrames={span(SCENES.ruler)}>
        <RulerScene />
      </Sequence>
      <Sequence from={SCENES.close.from} durationInFrames={span(SCENES.close)}>
        <CloseScene />
      </Sequence>
    </AbsoluteFill>
  );
};
