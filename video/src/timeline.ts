// Every cut in the video, in frames, so the narration and the picture stay locked.
export const FPS = 30;

export const t = (seconds: number) => Math.round(seconds * FPS);

export const SCENES = {
  title: { from: t(0), to: t(7) },
  status: { from: t(7), to: t(12) },
  ledger: { from: t(12), to: t(31) },
  rights: { from: t(31), to: t(41) },
  ruler: { from: t(41), to: t(51) },
  close: { from: t(51), to: t(60) },
};

export const TOTAL_FRAMES = t(60);

// The narration is 56.2s long and starts half a second in.
export const VOICE_START = t(0.5);

// Beat boundaries inside the rights and ruler scenes, in seconds from the scene start.
export const RIGHTS_BEATS = [0, 2.6, 5.2, 7.8];
export const RULER_CUT = t(4.5);
