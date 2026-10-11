import { Composition } from "remotion";
import { Record } from "./Record";
import { FPS, TOTAL_FRAMES } from "./timeline";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="HarnessDemo"
      component={Record}
      defaultProps={{ voice: "voice.mp3" }}
      durationInFrames={TOTAL_FRAMES}
      fps={FPS}
      width={1920}
      height={1080}
    />
  );
};
