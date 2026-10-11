// Every cut in the video, in frames, so the narration and the picture stay locked.
//
// The cuts are placed against the narration, sentence by sentence: the product is shown
// when the voice describes asking a question, the ledger when it describes the gate
// measuring two versions, the envelope when it says the agent cannot give itself a tool.
export const FPS = 30;

export const t = (seconds: number) => Math.round(seconds * FPS);

export const SCENES = {
  title: { from: t(0), to: t(3) },
  loop: { from: t(3), to: t(21) },
  terminal: { from: t(21), to: t(31) },
  app: { from: t(31), to: t(44) },
  envelope: { from: t(44), to: t(51) },
  close: { from: t(51), to: t(60) },
};

export const TOTAL_FRAMES = t(60);

// The narration starts half a second in. Its length is what the cuts are built around.
export const VOICE_START = t(0.5);

// Beats inside the scenes, in seconds from the scene start.
export const LOOP_STAGES = [0, 3.0, 5.4, 8.0, 11.0, 14.4];
export const TERMINAL_CUT = t(5.6);
export const APP_STATES = [0, 4.4, 8.4];
export const ENVELOPE_BEATS = [0, 1.9, 3.6, 5.2];
