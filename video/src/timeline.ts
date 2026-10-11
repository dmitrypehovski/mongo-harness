// Every cut in the video, in frames, so the narration and the picture stay locked.
//
// The cuts are placed against the narration, sentence by sentence: the product is shown
// when the voice describes asking a question, the ledger when it describes the gate
// measuring two versions, the envelope when it says the agent cannot give itself a tool.
export const FPS = 30;

export const t = (seconds: number) => Math.round(seconds * FPS);

export const SCENES = {
  title: { from: t(0), to: t(8) },
  product: { from: t(8), to: t(16) },
  ledger: { from: t(16), to: t(32) },
  rights: { from: t(32), to: t(42) },
  ruler: { from: t(42), to: t(52) },
  close: { from: t(52), to: t(60) },
};

export const TOTAL_FRAMES = t(60);

// The narration starts half a second in. Its length is what the cuts are built around.
export const VOICE_START = t(0.5);

// Beat boundaries inside the rights scene, in seconds from the scene start.
export const RIGHTS_BEATS = [0, 2.4, 4.8, 6.8];

// Inside the ledger scene: the headline lands when the voice says it, not before.
export const LEDGER_HEADLINE = t(7.0);
export const LEDGER_ROWS = t(6.8);

// Inside the ruler scene: the defect injection, when the voice reaches the audit.
export const RULER_CUT = t(5.2);
