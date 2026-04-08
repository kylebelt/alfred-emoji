import Cocoa

let canvas: CGFloat = 64
let fontSize: CGFloat = 56
let font = NSFont(name: "Apple Color Emoji", size: fontSize)!
let attrs: [NSAttributedString.Key: Any] = [.font: font]

while let line = readLine() {
    let parts = line.split(separator: "\t", maxSplits: 1)
    guard parts.count == 2 else { continue }
    let str = NSAttributedString(string: String(parts[0]), attributes: attrs)
    let s = str.size()
    let img = NSImage(size: NSSize(width: canvas, height: canvas))
    img.lockFocus()
    str.draw(at: NSPoint(x: (canvas - s.width) / 2, y: (canvas - s.height) / 2))
    img.unlockFocus()
    guard
        let t = img.tiffRepresentation,
        let r = NSBitmapImageRep(data: t),
        let p = r.representation(using: .png, properties: [:])
    else { continue }
    try? p.write(to: URL(fileURLWithPath: String(parts[1])))
}
