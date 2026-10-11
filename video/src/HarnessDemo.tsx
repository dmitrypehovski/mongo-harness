import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import data from "./harness-data.json";
import { COLORS, MONO, SANS } from "./theme";
import { RIGHTS_BEATS, RULER_CUT, SCENES, TOTAL_FRAMES, VOICE_START } from "./timeline";

/* ---------- small pieces ---------- */

const pct = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;

const rise = (frame: number, fps: number, delay = 0) =>
  spring({ frame: frame - delay, fps, config: { damping: 200, mass: 0.6 } });

const Panel: React.FC<{
  title: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ title, children, style }) => (
  <div
    style={{
      background: COLORS.panel,
      border: `1px solid ${COLORS.panelEdge}`,
      borderRadius: 14,
      overflow: "hidden",
      fontFamily: MONO,
      ...style,
    }}
  >
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "12px 18px",
        borderBottom: `1px solid ${COLORS.panelEdge}`,
        background: "#0e1118",
      }}
    >
      {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
        <span key={c} style={{ width: 12, height: 12, borderRadius: 6, background: c }} />
      ))}
      <span style={{ color: COLORS.dim, fontSize: 20, marginLeft: 8 }}>{title}</span>
    </div>
    <div style={{ padding: "22px 26px" }}>{children}</div>
  </div>
);

const Line: React.FC<{
  children: React.ReactNode;
  delay?: number;
  color?: string;
  size?: number;
}> = ({ children, delay = 0, color = COLORS.text, size = 24 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const progress = rise(frame, fps, delay);
  return (
    <div
      style={{
        color,
        fontSize: size,
        lineHeight: 1.55,
        opacity: progress,
        transform: `translateY(${(1 - progress) * 10}px)`,
        whiteSpace: "pre-wrap",
      }}
    >
      {children}
    </div>
  );
};

const Badge: React.FC<{ text: string; tone: "red" | "green" | "amber" }> = ({ text, tone }) => {
  const color = tone === "red" ? COLORS.red : tone === "green" ? COLORS.green : COLORS.amber;
  return (
    <span
      style={{
        border: `1px solid ${color}`,
        color,
        borderRadius: 6,
        padding: "2px 10px",
        fontSize: 19,
        fontFamily: MONO,
        whiteSpace: "nowrap",
      }}
    >
      {text}
    </span>
  );
};

const SceneTitle: React.FC<{ heading: string; sub?: string }> = ({ heading, sub }) => (
  <div style={{ fontFamily: SANS }}>
    <div style={{ fontSize: 50, fontWeight: 600, color: COLORS.text, letterSpacing: -0.5 }}>
      {heading}
    </div>
    {sub ? <div style={{ fontSize: 26, color: COLORS.dim, marginTop: 10 }}>{sub}</div> : null}
  </div>
);

const Frame: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(1200px 700px at 20% 0%, #151a26 0%, ${COLORS.bg} 60%)`,
      padding: "72px 96px",
      color: COLORS.text,
      fontFamily: SANS,
    }}
  >
    {children}
  </AbsoluteFill>
);

/* ---------- scenes ---------- */

const TitleScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const title = rise(frame, fps, 0);
  return (
    <Frame>
      <div style={{ display: "flex", flexDirection: "column", height: "100%", justifyContent: "center" }}>
        <div
          style={{
            fontSize: 78,
            fontWeight: 700,
            letterSpacing: -1.5,
            opacity: title,
            transform: `translateY(${(1 - title) * 24}px)`,
          }}
        >
          The harness that earns its edits
        </div>
        <div
          style={{
            fontSize: 36,
            color: COLORS.accent,
            marginTop: 26,
            opacity: rise(frame, fps, 14),
          }}
        >
          A gate decides whether that made it better
        </div>
        <div
          style={{
            fontSize: 23,
            color: COLORS.faint,
            marginTop: 60,
            fontFamily: MONO,
            opacity: rise(frame, fps, 28),
          }}
        >
          57 plain-language questions · MongoDB Atlas · sample_mflix · all of it written on 11 October 2026
        </div>
      </div>
    </Frame>
  );
};

const StatusScene: React.FC = () => {
  const frame = useCurrentFrame();
  const enabled = data.current.tools.join(", ");
  return (
    <Frame>
      <SceneTitle heading="It starts with nothing of its own" sub="One document in MongoDB is the whole version." />
      <div style={{ marginTop: 44 }}>
        <Panel title="mh.cli status">
          <Line color={COLORS.dim}>$ python -m mh.cli status</Line>
          <div style={{ height: 14 }} />
          <Line delay={10}>version {data.current.version} (promoted by {data.current.promoted_by})</Line>
          <Line delay={18} color={COLORS.dim}>
            {`rules:  []            tools: [${enabled}]`}
          </Line>
          <div style={{ height: 14 }} />
          <Line delay={26} color={COLORS.amber}>
            last train run: {data.current.train}
          </Line>
          <Line delay={34} color={COLORS.dim}>
            last verification run: {data.current.holdout}
          </Line>
        </Panel>
      </div>
      <div style={{ marginTop: 40, fontSize: 26, color: COLORS.dim, opacity: rise(frame, 30, 30) }}>
        The gate has not accepted anything yet, so the starting version is still the current one.
      </div>
    </Frame>
  );
};

const LedgerScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rows = data.edits;

  return (
    <Frame>
      <SceneTitle
        heading="Five proposals, five refusals"
        sub="Each one measured on questions it cannot see, repeated, then compared with an exact paired test."
      />
      <div style={{ marginTop: 34, fontFamily: MONO }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1.55fr 0.75fr 0.85fr 1.05fr",
            color: COLORS.faint,
            fontSize: 19,
            paddingBottom: 12,
            borderBottom: `1px solid ${COLORS.panelEdge}`,
          }}
        >
          <span>proposal</span>
          <span>selection</span>
          <span>verification</span>
          <span>verdict</span>
        </div>
        {rows.map((row, index) => {
          const progress = rise(frame, fps, 16 + index * 24);
          const isTrap = row.strategy.includes("remember");
          const isWorse = row.strategy.includes("keeps getting wrong");
          return (
            <div
              key={row.strategy}
              style={{
                display: "grid",
                gridTemplateColumns: "1.55fr 0.75fr 0.85fr 1.05fr",
                alignItems: "center",
                gap: 8,
                padding: "15px 0",
                borderBottom: `1px solid #1a1f2b`,
                opacity: progress,
                transform: `translateX(${(1 - progress) * 26}px)`,
                background: isWorse
                  ? "rgba(255,93,93,0.07)"
                  : isTrap
                    ? "rgba(255,180,84,0.06)"
                    : "transparent",
              }}
            >
              <span style={{ fontSize: 22, color: COLORS.text }}>{row.strategy}</span>
              <span style={{ fontSize: 21, color: COLORS.dim }}>
                {pct(row.train_before)} → {pct(row.train_after)}
              </span>
              <span
                style={{
                  fontSize: 21,
                  color: isWorse ? COLORS.red : isTrap ? COLORS.amber : COLORS.dim,
                }}
              >
                {pct(row.holdout_before)} → {pct(row.holdout_after)}
              </span>
              <span style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <Badge text={row.decision.replace("rejected_", "")} tone={isWorse ? "red" : "amber"} />
                {row.p_value !== null && row.p_value !== undefined ? (
                  <span style={{ fontSize: 18, color: COLORS.faint }}>p={row.p_value.toFixed(2)}</span>
                ) : null}
              </span>
            </div>
          );
        })}
      </div>
      <div
        style={{
          marginTop: 26,
          fontSize: 24,
          color: COLORS.amber,
          opacity: rise(frame, fps, 180),
        }}
      >
        The best-looking idea gained 3.1 points where the search can see and 6.0 where it cannot.
        The gate still calls that indistinguishable from noise, and refuses it.
      </div>
    </Frame>
  );
};

const RightsScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const beats = [
    { at: RIGHTS_BEATS[0], text: "the aggregate tool is revoked", value: "selection 18.8% · verification 12.0%", tone: COLORS.red, extra: "47 questions refused before any model call" },
    { at: RIGHTS_BEATS[1], text: "proposal: give the tool back", value: "refused by the envelope", tone: COLORS.red, extra: "the version widens its own tool access: aggregate, count" },
    { at: RIGHTS_BEATS[2], text: "proposal: use $where instead", value: "refused by the envelope", tone: COLORS.red, extra: "server-side JavaScript is not a tool the harness may grant itself" },
    { at: RIGHTS_BEATS[3], text: "restored by a human, not by the harness", value: "selection 68.8% · verification 80.0%", tone: COLORS.green, extra: "" },
  ];
  return (
    <Frame>
      <SceneTitle heading="It cannot give itself a tool" sub="Not a sentence in a prompt. A refusal that no model decides." />
      <div style={{ marginTop: 40, fontFamily: MONO }}>
        {beats.map((beat, index) => {
          const progress = rise(frame, fps, beat.at * fps);
          return (
            <div
              key={beat.text}
              style={{
                opacity: progress,
                transform: `translateY(${(1 - progress) * 16}px)`,
                padding: "18px 0",
                borderBottom: `1px solid #1a1f2b`,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 20 }}>
                <span style={{ fontSize: 27, color: COLORS.text }}>{beat.text}</span>
                <span style={{ fontSize: 25, color: beat.tone }}>{beat.value}</span>
              </div>
              {beat.extra ? (
                <div style={{ fontSize: 20, color: COLORS.faint, marginTop: 8 }}>{beat.extra}</div>
              ) : null}
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 40, fontSize: 26, color: COLORS.accent, opacity: rise(frame, fps, 9 * fps) }}>
        The gate is not a sentence in the prompt. It is a branch in the code path, and no model
        can talk its way past it.
      </div>
    </Frame>
  );
};

const RulerScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const injected = frame >= RULER_CUT;
  const constructs = data.audit.injected
    .filter((line) => line.trim().startsWith("*"))
    .map((line) => line.trim().slice(1).split(":")[0].trim());

  return (
    <Frame>
      <SceneTitle
        heading="And it audits the instrument it is measured with"
        sub="A score is only a fact if the sandbox accepts what the database accepts."
      />
      <div style={{ marginTop: 36 }}>
        <Panel title={injected ? "mh.cli audit-ruler --inject regex" : "mh.cli audit-ruler"}>
          {!injected ? (
            <>
              <Line>11 equivalence probe(s): 11 agreed, 0 diverged</Line>
              <Line delay={8}>5 policy probe(s): 5 refused, 0 admitted</Line>
              <div style={{ height: 12 }} />
              <Line delay={16} color={COLORS.green}>
                The instrument agrees with the database on every probe. Measurements stand.
              </Line>
            </>
          ) : (
            <>
              <Line color={COLORS.red}>11 equivalence probe(s): 7 agreed, 4 diverged</Line>
              <Line delay={6} color={COLORS.red}>
                The instrument is lying. Fix this before trusting any measurement:
              </Line>
              <div style={{ height: 10 }} />
              {constructs.map((name, index) => (
                <Line key={name} delay={14 + index * 8} color={COLORS.red} size={21}>
                  {`  * ${name}`}
                </Line>
              ))}
            </>
          )}
        </Panel>
      </div>
      <div
        style={{
          marginTop: 34,
          fontSize: 25,
          color: injected ? COLORS.red : COLORS.dim,
          opacity: rise(frame, fps, injected ? RULER_CUT + 20 : 30),
        }}
      >
        {injected
          ? "That is the defect this project spent its afternoon in. The auditor now finds it in seconds, and the run exits non-zero."
          : "Sixteen probes, no model involved, and a fault-injection switch that proves the auditor can fail."}
      </div>
    </Frame>
  );
};

const CloseScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { counts } = data;
  const items = [
    ["runs", counts.runs],
    ["steps", counts.steps],
    ["lessons", counts.lessons],
    ["refused edits", counts.edits],
  ] as const;
  return (
    <Frame>
      <div style={{ display: "flex", flexDirection: "column", height: "100%", justifyContent: "center" }}>
        <div style={{ fontSize: 52, fontWeight: 600, opacity: rise(frame, fps, 0) }}>
          Everything it remembers lives in MongoDB
        </div>
        <div style={{ display: "flex", gap: 56, marginTop: 46, opacity: rise(frame, fps, 12) }}>
          {items.map(([label, value]) => (
            <div key={label}>
              <div style={{ fontFamily: MONO, fontSize: 46, color: COLORS.green }}>{value}</div>
              <div style={{ fontSize: 22, color: COLORS.dim, marginTop: 6 }}>{label}</div>
            </div>
          ))}
        </div>
        <div
          style={{
            marginTop: 66,
            fontFamily: MONO,
            fontSize: 34,
            color: COLORS.accent,
            opacity: rise(frame, fps, 26),
          }}
        >
          github.com/dmitrypehovski/mongo-harness
        </div>
        <div style={{ marginTop: 18, fontSize: 24, color: COLORS.faint, opacity: rise(frame, fps, 34) }}>
          Any version rolls back with one command, with the reason recorded.
        </div>
      </div>
    </Frame>
  );
};

/* ---------- the video ---------- */

export const HarnessDemo: React.FC = () => {
  const frame = useCurrentFrame();
  const duration = (scene: { from: number; to: number }) => scene.to - scene.from;
  const progress = interpolate(frame, [0, TOTAL_FRAMES], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill>
      <Sequence from={VOICE_START} durationInFrames={TOTAL_FRAMES - VOICE_START}>
        <Audio src={staticFile("voice.mp3")} />
      </Sequence>
      <Sequence from={SCENES.title.from} durationInFrames={duration(SCENES.title)}>
        <TitleScene />
      </Sequence>
      <Sequence from={SCENES.status.from} durationInFrames={duration(SCENES.status)}>
        <StatusScene />
      </Sequence>
      <Sequence from={SCENES.ledger.from} durationInFrames={duration(SCENES.ledger)}>
        <LedgerScene />
      </Sequence>
      <Sequence from={SCENES.rights.from} durationInFrames={duration(SCENES.rights)}>
        <RightsScene />
      </Sequence>
      <Sequence from={SCENES.ruler.from} durationInFrames={duration(SCENES.ruler)}>
        <RulerScene />
      </Sequence>
      <Sequence from={SCENES.close.from} durationInFrames={duration(SCENES.close)}>
        <CloseScene />
      </Sequence>

      <div
        style={{
          position: "absolute",
          left: 0,
          bottom: 0,
          height: 5,
          width: `${progress * 100}%`,
          background: COLORS.green,
        }}
      />
      <div
        style={{
          position: "absolute",
          right: 40,
          bottom: 22,
          fontFamily: MONO,
          fontSize: 18,
          color: COLORS.faint,
        }}
      >
        mongo-harness · sandbox cluster0 · 2026-10-11
      </div>
    </AbsoluteFill>
  );
};
