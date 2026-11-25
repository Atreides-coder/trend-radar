export type Asset = {
  id: string;
  type: string;
  path: string;
  source: string;
  url?: string;
  width: number;
  height: number;
  duration?: number;
};

export type Box = { x: number; y: number; w: number; h: number };

export type Diagram = {
  kind: "none" | "compare" | "flow" | "grid";
  title: string;
  left_label: string;
  left_items: string[];
  right_label: string;
  right_items: string[];
  steps: string[];
};

export type Shot = {
  component: string;
  start: number;
  end: number;
  asset: Asset | null;
  highlight: Box | null;
  headline: string;
  sub: string;
  diagram: Diagram;
  quote: { text: string; attribution: string };
  data: { value: string; label: string };
};

export type Scene = {
  scene_id: number;
  start: number;
  end: number;
  purpose: string;
  shots: Shot[];
};

export type CaptionToken = { text: string; startMs: number; endMs: number };

export type CaptionPage = {
  scene_id: number;
  text: string;
  startMs: number;
  endMs: number;
  tokens: CaptionToken[];
  emphasis: string[];
};

export type VideoProps = {
  title: string;
  duration: number;
  audio: string;
  scenes: Scene[];
  captions: CaptionPage[];
  sources: string[];
};
