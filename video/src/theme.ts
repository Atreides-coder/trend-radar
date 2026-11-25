// 极简、中性深色。只有一个强调色，用得很省：字幕里的重点词、高亮框、图解里"新"的那一边。
export const theme = {
  bg: "#0c0c0b",
  surface: "#181817",
  surfaceHi: "#222220",
  border: "#30302d",
  text: "#f5f4ef",
  muted: "#a3a29b",
  faint: "#6e6d68",
  accent: "#f5b83d",
  font: '"PingFang SC", "Helvetica Neue", "Hiragino Sans GB", sans-serif',
};

// 1080 × 1920 竖屏的版面
export const layout = {
  side: 60,          // 左右安全边距
  labelTop: 150,     // 画面顶部短标签的位置
  stageTop: 290,     // 主画面区域
  stageHeight: 1010,
  captionCenter: 1475, // 字幕的垂直中心；底部留给平台自己的界面
};

export const EASE_OUT = [0.16, 1, 0.3, 1] as const;
