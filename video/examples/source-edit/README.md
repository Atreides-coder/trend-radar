# 网页实证剪辑

这是一次 53.3 秒竖屏视频的手工分镜。Opening.tsx 对应前 300 帧，Body.tsx 接后续 1299 帧，统一采用 30 fps。可阅读和修改原页取景、镜头移动、划线和逐词字幕的实现。

原案例使用项目生成的 captions.json，复制到本目录并命名为 pages.json。配音取自同一项目的 audio/voice.wav。渲染时需自行准备有使用权的网页图片。将其放在本目录 public 下，名称见两个入口中的 staticFile 调用和 Pic、Sheet 组件。各截图的构图及笔迹按原案例尺寸定位，换图后应相应调整坐标。原始素材和配音保存在制作者本机。

从仓库根目录运行：

```bash
npm ci --prefix video
cd video
npx remotion render examples/source-edit/Opening.tsx OriginalPage opening.mp4 --public-dir=examples/source-edit/public
npx remotion render examples/source-edit/Body.tsx FullBody body.mp4 --public-dir=examples/source-edit/public
```

在本地以 10 秒为切点拼接两段画面，并复用同一条完整音轨。普通选题可以直接通过 Video Studio 的通用模板出片。
