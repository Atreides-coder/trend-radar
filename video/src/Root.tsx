import { CalculateMetadataFunction, Composition } from "remotion";
import { TrendVideo } from "./TrendVideo";
import { VideoProps } from "./types";
import { AgentPermissions } from "./v2/AgentPermissions";
import { DirectedProps } from "./v2/types";

const FPS = 30;

const calculateMetadata: CalculateMetadataFunction<VideoProps> = ({ props }) => {
  return { durationInFrames: Math.max(1, Math.ceil(props.duration * FPS)) };
};

// 没有传 props 时的占位内容，只用于在 Studio 里看版式
const defaultProps: VideoProps = {
  title: "Trend Radar",
  duration: 4,
  audio: "",
  sources: [],
  captions: [],
  scenes: [
    {
      scene_id: 1,
      start: 0,
      end: 4,
      purpose: "hook",
      shots: [
        {
          component: "HookScene",
          start: 0,
          end: 4,
          asset: null,
          highlight: null,
          headline: "Trend Radar",
          sub: "Video Template",
          diagram: { kind: "none", title: "", left_label: "", left_items: [], right_label: "", right_items: [], steps: [] },
          quote: { text: "", attribution: "" },
          data: { value: "", label: "" },
        },
      ],
    },
  ],
};

const directedMetadata: CalculateMetadataFunction<DirectedProps> = ({ props }) => {
  return { durationInFrames: Math.max(1, Math.ceil(props.duration * FPS)) };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
    <Composition
      id="AgentPermissions"
      component={AgentPermissions}
      durationInFrames={120}
      fps={FPS}
      width={1080}
      height={1920}
      defaultProps={{ duration: 4, shots: [], captions: [], demo: { steps: 0, task: "", files: [], email: "", todo: "" }, boxes: {}, sources: [] }}
      calculateMetadata={directedMetadata}
    />
    <Composition
      id="TrendVideo"
      component={TrendVideo}
      durationInFrames={120}
      fps={FPS}
      width={1080}
      height={1920}
      defaultProps={defaultProps}
      calculateMetadata={calculateMetadata}
    />
    </>
  );
};
