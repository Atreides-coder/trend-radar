export type Word = { text: string; start: number; end: number };
export type ShotT = { id: number; start: number; end: number; voice: string; words: Word[] };
export type BoxT = { x: number; y: number; w: number; h: number } | null;
export type CaptionT = { scene_id: number; text: string; startMs: number; endMs: number };

export type DirectedProps = {
  duration: number;
  shots: ShotT[];
  captions: CaptionT[];
  demo: { steps: number; task: string; files: string[]; email: string; todo: string };
  boxes: Record<string, BoxT>;
  sources: string[];
};

export type ShotProps = { s: ShotT; p: DirectedProps };
