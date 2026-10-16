import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count > 1 else {
    exit(0)
}

let imagePath = CommandLine.arguments[1]
let outputJson = CommandLine.arguments.contains("--json")

guard let image = NSImage(contentsOfFile: imagePath),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    exit(0)
}

let request = VNRecognizeTextRequest { (request, error) in
    guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
    var results: [String] = []
    
    for observation in observations {
        if let topCandidate = observation.topCandidates(1).first {
            let text = topCandidate.string.replacingOccurrences(of: "\"", with: "\\\"")
            if outputJson {
                let box = observation.boundingBox
                // 将 Vision 坐标系 (原点在左下角) 转换为屏幕图像的标准坐标系 (原点在左上角)
                let topDownY = 1.0 - (box.origin.y + box.size.height / 2.0)
                let midX = box.origin.x + box.size.width / 2.0
                results.append("{\"text\":\"\(text)\",\"x\":\(midX),\"y\":\(topDownY)}")
            } else {
                results.append(topCandidate.string)
            }
        }
    }
    
    if outputJson {
        print("[\n" + results.joined(separator: ",\n") + "\n]")
    } else {
        print(results.joined(separator: "\n"))
    }
}

request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try? handler.perform([request])
