import AppKit
import Foundation

func fail(_ message: String) -> Never {
    let data = try! JSONSerialization.data(withJSONObject: ["error":message])
    print(String(data:data,encoding:.utf8)!); exit(1)
}
let args=CommandLine.arguments
let board=NSPasteboard.general
if args.count == 3 && args[1] == "capture" {
    guard let image=NSImage(pasteboard:board), let tiff=image.tiffRepresentation,
          let bitmap=NSBitmapImageRep(data:tiff), let png=bitmap.representation(using:.png,properties:[:]) else { fail("Panoda görsel bulunamadı.") }
    if png.count > 20*1024*1024 { fail("Görsel en fazla 20 MB olabilir.") }
    do {try png.write(to:URL(fileURLWithPath:args[2]),options:.atomic); print("{\"ok\":true}")}
    catch {fail("Panodaki görsel kaydedilemedi.")}
} else if args.count == 5 && args[1] == "attach" {
    guard let image=NSImage(contentsOfFile:args[3]), let tiff=image.tiffRepresentation else {fail("Görsel okunamadı.")}
    // Preserve the user's clipboard; don't replace a new copy made during the operation.
    let saved=(board.pasteboardItems ?? []).map { item -> NSPasteboardItem in
        let copy=NSPasteboardItem(); for type in item.types {if let data=item.data(forType:type){copy.setData(data,forType:type)}};return copy
    }
    board.clearContents();board.setData(tiff,forType:.tiff)
    let written=board.changeCount
    let proc=Process();proc.executableURL=URL(fileURLWithPath:args[4]);proc.arguments=["keys",args[2],"ctrl+v"]
    let pipe=Pipe();proc.standardOutput=pipe;proc.standardError=pipe
    do {try proc.run();proc.waitUntilExit()} catch {
        if board.changeCount == written {board.clearContents();board.writeObjects(saved)}
        fail("Görsel terminale aktarılamadı.")
    }
    // hc keys returns after delivery; allow the TUI's native paste handler to read the clipboard.
    Thread.sleep(forTimeInterval:0.45)
    if board.changeCount == written {board.clearContents();board.writeObjects(saved)}
    if proc.terminationStatus != 0 {fail("Terminal görsel yapıştırmayı kabul etmedi.")}
    print("{\"ok\":true}")
} else {fail("Geçersiz görsel komutu.")}
