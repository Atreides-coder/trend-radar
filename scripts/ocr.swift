// 用 macOS 自带的 Vision 做 OCR：输出每一行文字和它在图片里的位置（0~1，原点在左上角）。
// 用法：swift scripts/ocr.swift <image>   →  JSON 数组 [{"text","x","y","w","h"}]
import AppKit
import Foundation
import Vision

guard CommandLine.arguments.count > 1,
      let image = NSImage(contentsOfFile: CommandLine.arguments[1]),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("cannot read image\n".data(using: .utf8)!)
    exit(1)
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.usesLanguageCorrection = true
try VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
var lines: [[String: Any]] = []
for obs in request.results ?? [] {
    guard let top = obs.topCandidates(1).first else { continue }
    let b = obs.boundingBox   // Vision 的原点在左下角
    lines.append(["text": top.string, "x": b.minX, "y": 1 - b.maxY, "w": b.width, "h": b.height])
}
lines.sort { ($0["y"] as! CGFloat) < ($1["y"] as! CGFloat) }
let data = try JSONSerialization.data(withJSONObject: lines, options: [])
print(String(data: data, encoding: .utf8)!)
