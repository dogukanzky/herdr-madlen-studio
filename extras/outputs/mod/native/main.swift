import AppKit
import WebKit
import ImageIO
import UniformTypeIdentifiers

struct OutputFile: Codable, Equatable {
    var path: String
    var name: String
    var kind: String
    var directory: Bool
    var size: Int64
    var source: String?
    var search_text: String?
    var w: Double?
    var h: Double?
    var url: URL { URL(fileURLWithPath: path) }
    var category: String { directory ? "folder" : kind }
    var typeLabel: String {
        switch category {
        case "image": return "Görsel"
        case "html": return "Web sayfası"
        case "markdown": return "Markdown"
        case "json": return "JSON"
        case "zip": return "ZIP arşivi"
        case "folder": return "Klasör"
        default: return url.pathExtension.isEmpty ? "Dosya" : url.pathExtension.uppercased()
        }
    }
    var detail: String {
        if category == "image", let w = w, let h = h { return "\(Int(w)) × \(Int(h))" }
        if directory { return "Klasör" }
        return ByteCountFormatter.string(fromByteCount: size, countStyle: .file)
    }
}

struct ScanResult: Decodable {
    var items: [OutputFile]
    var message_count: Int?
    var error: String?
}

struct LaunchRequest: Decodable {
    var terminal: String
    var app_home: String
    var fixture: String?
}

func folded(_ text: String) -> String {
    text.lowercased(with: Locale(identifier: "tr_TR"))
        .folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "tr_TR"))
}

func matches(_ file: OutputFile, query: String) -> Bool {
    let corpus = folded("\(file.name) \(file.path) \(file.typeLabel) \(file.search_text ?? "")")
    return folded(query).split(whereSeparator: { $0.isWhitespace }).allSatisfy { corpus.contains($0) }
}

enum OpenRoute: String {
    case image, html, markdown, json, previewApp, chrome, finderReveal, finderFolder, system
}

enum FileClickAction {
    case select, open, openExternal
}

func fileClickAction(count: Int, command: Bool) -> FileClickAction {
    if command { return .openExternal }
    return count >= 2 ? .open : .select
}

func route(_ file: OutputFile, external: Bool) -> OpenRoute {
    switch file.category {
    case "image": return external ? .previewApp : .image
    case "html": return external ? .chrome : .html
    case "markdown": return external ? .system : .markdown
    case "json": return external ? .system : .json
    case "zip": return .finderReveal
    case "folder": return .finderFolder
    default: return .system
    }
}

func thumbnail(_ url: URL, maxSize: Int = 420) -> NSImage? {
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let cg = CGImageSourceCreateThumbnailAtIndex(source, 0, [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceThumbnailMaxPixelSize: maxSize,
            kCGImageSourceCreateThumbnailWithTransform: true
          ] as CFDictionary) else { return NSImage(contentsOf: url) }
    return NSImage(cgImage: cg, size: NSSize(width: cg.width, height: cg.height))
}

func copyFiles(_ files: [OutputFile], to board: NSPasteboard) -> Bool {
    guard !files.isEmpty else { return false }
    var writers: [NSPasteboardItem] = []
    let paths = files.map(\.path).joined(separator: "\n")
    for file in files where file.category == "image" {
        let item = NSPasteboardItem()
        if file.category == "image" {
            item.setString(file.url.absoluteString, forType: .fileURL)
            if let image = NSImage(contentsOf: file.url), let tiff = image.tiffRepresentation {
                item.setData(tiff, forType: .tiff)
                if let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
                    item.setData(png, forType: .png)
                }
            }
        }
        if writers.isEmpty { item.setString(paths, forType: .string) }
        writers.append(item)
    }
    if writers.isEmpty {
        let item = NSPasteboardItem(); item.setString(paths, forType: .string); writers.append(item)
    }
    board.clearContents()
    return board.writeObjects(writers)
}

func scanData(_ appHome: String, payload: [String: Any]) throws -> Data {
    let process = Process(), out = Pipe(), err = Pipe()
    var payload = payload; payload["app_home"] = appHome
    let argument = String(data: try JSONSerialization.data(withJSONObject: payload), encoding: .utf8)!
    process.executableURL = URL(fileURLWithPath: Bundle.main.object(forInfoDictionaryKey: "PythonExecutable") as? String ?? "/usr/bin/python3")
    process.arguments = ["\(appHome)/mods/outputs-browser/scan.py", argument]
    var env = ProcessInfo.processInfo.environment
    env["PATH"] = "\(NSHomeDirectory())/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + (env["PATH"] ?? "")
    process.environment = env; process.standardOutput = out; process.standardError = err
    try process.run()
    let data = out.fileHandleForReading.readDataToEndOfFile()
    let stderr = err.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
    if process.terminationStatus != 0 { throw NSError(domain: "Scan", code: 1, userInfo: [NSLocalizedDescriptionKey: String(data: stderr, encoding: .utf8) ?? "Dosyalar okunamadı."]) }
    return data
}

final class RootView: NSView {
    var arrange: (() -> Void)?
    override func layout() { super.layout(); arrange?() }
}

final class DocumentAssets: NSObject, WKURLSchemeHandler {
    let root: URL
    init(root: URL) { self.root = root.resolvingSymlinksInPath() }
    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let request = task.request.url else { return }
        let local = URL(fileURLWithPath: request.path).standardizedFileURL.resolvingSymlinksInPath()
        guard local.path.hasPrefix(root.path + "/"), let data = try? Data(contentsOf: local) else {
            task.didFailWithError(NSError(domain: "Assets", code: 404)); return
        }
        let mime = UTType(filenameExtension: local.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
        task.didReceive(URLResponse(url: request, mimeType: mime, expectedContentLength: data.count, textEncodingName: nil))
        task.didReceive(data); task.didFinish()
    }
    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}
}

final class OutputWindow: NSWindow {
    weak var owner: BrowserController?
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if event.modifierFlags.contains(.command), let key = event.charactersIgnoringModifiers?.lowercased() {
            if key == "f" { owner?.focusSearch(); return true }
            if key == "r" { owner?.reload(); return true }
            if key == "g", owner?.documentKind != nil { owner?.findInDocument(step: event.modifierFlags.contains(.shift) ? -1 : 1); return true }
        }
        // Search keeps ordinary text editing shortcuts.
        if firstResponder is NSTextView { return super.performKeyEquivalent(with: event) }
        if event.modifierFlags.contains(.command), let key = event.charactersIgnoringModifiers?.lowercased() {
            if key == "c" { owner?.copySelection(); return true }
            if key == "a" { owner?.selectAll(); return true }
            if key == "v" { owner?.addFromClipboard(); return true }
        }
        return super.performKeyEquivalent(with: event)
    }
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53, owner?.previewing != nil { owner?.back(); return }
        if owner?.previewing?.category == "image" {
            if event.keyCode == 123 { owner?.stepImage(-1); return }
            if event.keyCode == 124 { owner?.stepImage(1); return }
        }
        super.keyDown(with: event)
    }
}

final class FileCanvas: NSView, NSDraggingSource {
    weak var owner: BrowserController?
    var files: [OutputFile] = []
    var selected = Set<String>()
    var listMode = false
    var images: [String: NSImage] = [:]
    var anchor: Int?
    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }
    var columns: Int { listMode ? 1 : max(1, Int((bounds.width - 28) / 170)) }
    var cellWidth: CGFloat { listMode ? bounds.width : (bounds.width - 28) / CGFloat(columns) }
    var rowHeight: CGFloat { listMode ? 46 : 172 }

    func rect(_ index: Int) -> NSRect {
        if listMode { return NSRect(x: 10, y: 32 + CGFloat(index) * rowHeight, width: bounds.width - 20, height: rowHeight - 2) }
        return NSRect(x: 14 + CGFloat(index % columns) * cellWidth + 3,
                      y: 14 + CGFloat(index / columns) * rowHeight, width: cellWidth - 6, height: rowHeight - 8)
    }
    func checkRect(_ r: NSRect) -> NSRect {
        listMode ? NSRect(x: r.minX + 8, y: r.midY - 8, width: 16, height: 16)
                 : NSRect(x: r.maxX - 25, y: r.minY + 8, width: 16, height: 16)
    }
    func relayout(width: CGFloat, minHeight: CGFloat) {
        frame.size.width = width
        let rows = Int(ceil(Double(files.count) / Double(columns)))
        frame.size.height = max(minHeight, CGFloat(rows) * rowHeight + (listMode ? 52 : 28))
        removeAllToolTips()
        for i in files.indices { addToolTip(rect(i), owner: "\(files[i].name)\n\(files[i].path)" as NSString, userData: nil) }
        needsDisplay = true
    }
    func imageFor(_ file: OutputFile) -> NSImage {
        if let image = images[file.path] { return image }
        let image = file.category == "image" ? thumbnail(file.url) ?? NSWorkspace.shared.icon(forFile: file.path)
                                            : NSWorkspace.shared.icon(forFile: file.path)
        images[file.path] = image
        return image
    }
    func text(_ value: String, in rect: NSRect, font: NSFont, color: NSColor, center: Bool = false, lines: Bool = false) {
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = center ? .center : .left
        paragraph.lineBreakMode = lines ? .byTruncatingMiddle : .byTruncatingTail
        (value as NSString).draw(in: rect, withAttributes: [.font: font, .foregroundColor: color, .paragraphStyle: paragraph])
    }
    func fit(_ image: NSImage, in box: NSRect) {
        let k = min(box.width / max(1, image.size.width), box.height / max(1, image.size.height))
        let size = NSSize(width: image.size.width * k, height: image.size.height * k)
        image.draw(in: NSRect(x: box.midX - size.width / 2, y: box.midY - size.height / 2, width: size.width, height: size.height),
                   from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
    }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.controlBackgroundColor.setFill(); dirtyRect.fill()
        if listMode {
            text("Ad", in: NSRect(x: 89, y: 9, width: 180, height: 18), font: .systemFont(ofSize: 11.5, weight: .medium), color: .secondaryLabelColor)
            text("Tür", in: NSRect(x: bounds.width - 230, y: 9, width: 100, height: 18), font: .systemFont(ofSize: 11.5, weight: .medium), color: .secondaryLabelColor)
            text("Boyut", in: NSRect(x: bounds.width - 116, y: 9, width: 100, height: 18), font: .systemFont(ofSize: 11.5, weight: .medium), color: .secondaryLabelColor)
        }
        for i in files.indices {
            let r = rect(i)
            if !r.intersects(dirtyRect) { continue }
            let file = files[i], active = selected.contains(file.path)
            if active {
                NSColor.controlAccentColor.withAlphaComponent(0.14).setFill()
                NSBezierPath(roundedRect: r, xRadius: 8, yRadius: 8).fill()
                NSColor.controlAccentColor.withAlphaComponent(0.5).setStroke()
                NSBezierPath(roundedRect: r.insetBy(dx: 0.5, dy: 0.5), xRadius: 8, yRadius: 8).stroke()
            } else if listMode && i % 2 == 1 {
                NSColor.alternatingContentBackgroundColors.last?.setFill()
                NSBezierPath(roundedRect: r, xRadius: 5, yRadius: 5).fill()
            }
            let box = listMode ? NSRect(x: r.minX + 36, y: r.midY - 15, width: 30, height: 30)
                               : NSRect(x: r.minX + 17, y: r.minY + 24, width: r.width - 34, height: 94)
            fit(imageFor(file), in: box)
            if listMode {
                text(file.name, in: NSRect(x: r.minX + 79, y: r.midY - 8, width: max(50, r.width - 320), height: 20), font: .systemFont(ofSize: 13), color: .labelColor)
                text(file.typeLabel, in: NSRect(x: r.maxX - 220, y: r.midY - 8, width: 110, height: 20), font: .systemFont(ofSize: 12), color: .secondaryLabelColor)
                text(file.detail, in: NSRect(x: r.maxX - 106, y: r.midY - 8, width: 100, height: 20), font: .systemFont(ofSize: 12), color: .secondaryLabelColor)
            } else {
                text(file.name, in: NSRect(x: r.minX + 7, y: r.minY + 122, width: r.width - 14, height: 18), font: .systemFont(ofSize: 12.5), color: .labelColor, center: true)
                text(file.detail, in: NSRect(x: r.minX + 7, y: r.minY + 143, width: r.width - 14, height: 16), font: .systemFont(ofSize: 11), color: .secondaryLabelColor, center: true)
            }
            let cr = checkRect(r)
            (active ? NSColor.controlAccentColor : NSColor.tertiaryLabelColor.withAlphaComponent(0.4)).setStroke()
            NSBezierPath(ovalIn: cr).stroke()
            if active {
                NSColor.controlAccentColor.setFill(); NSBezierPath(ovalIn: cr).fill()
                text("✓", in: cr.offsetBy(dx: 2, dy: -1), font: .boldSystemFont(ofSize: 12), color: .white)
            }
        }
        if files.isEmpty {
            text(owner?.loading == true ? "Konuşmanın son 50 mesajı okunuyor…" : "Eşleşen dosya yok",
                 in: NSRect(x: 20, y: 70, width: max(100, bounds.width - 40), height: 30), font: .systemFont(ofSize: 15), color: .secondaryLabelColor, center: true)
        }
    }
    func changed() { needsDisplay = true; owner?.selectionChanged() }
    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        let point = convert(event.locationInWindow, from: nil)
        guard let index = files.indices.first(where: { rect($0).contains(point) }) else { selected.removeAll(); changed(); return }
        let file = files[index]
        if checkRect(rect(index)).contains(point) {
            if selected.contains(file.path) { selected.remove(file.path) } else { selected.insert(file.path) }
            anchor = index; changed(); return
        }
        if event.modifierFlags.contains(.shift) {
            let start = min(files.count - 1, max(0, anchor ?? index))
            for i in min(start, index)...max(start, index) { selected.insert(files[i].path) }
            changed(); return
        }
        if !selected.contains(file.path) { selected = [file.path] }
        anchor = index; changed()
        while let next = window?.nextEvent(matching: [.leftMouseDragged, .leftMouseUp]) {
            if next.type == .leftMouseDragged {
                let current = convert(next.locationInWindow, from: nil)
                if hypot(current.x - point.x, current.y - point.y) < 4 { continue }
                let chosen = files.enumerated().filter { selected.contains($0.element.path) }
                let dragging = chosen.map { pair -> NSDraggingItem in
                    let item = NSDraggingItem(pasteboardWriter: pair.element.url as NSURL)
                    let origin = rect(pair.offset)
                    item.setDraggingFrame(NSRect(x: origin.minX, y: origin.minY, width: 64, height: 64), contents: imageFor(pair.element))
                    return item
                }
                let session = beginDraggingSession(with: dragging, event: next, source: self)
                session.draggingFormation = .stack
                session.animatesToStartingPositionsOnCancelOrFail = true
                return
            }
            if next.type == .leftMouseUp {
                switch fileClickAction(count: event.clickCount, command: event.modifierFlags.contains(.command)) {
                case .select:
                    selected = [file.path]; changed()
                case .open:
                    owner?.activate(file, external: false)
                case .openExternal:
                    owner?.activate(file, external: true)
                }
                return
            }
        }
    }
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 49 || event.keyCode == 36 {
            if let file = files.first(where: { selected.contains($0.path) }) { owner?.activate(file, external: false) }
        } else { super.keyDown(with: event) }
    }
    func draggingSession(_ session: NSDraggingSession, sourceOperationMaskFor context: NSDraggingContext) -> NSDragOperation { .copy }
    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation { .copy }
    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        let urls = sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL] ?? []
        if urls.isEmpty { return false }
        owner?.addPaths(urls.map(\.path).joined(separator: "\n")); return true
    }
}

final class BrowserController: NSWindowController, NSToolbarDelegate, NSSearchFieldDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
    let request: LaunchRequest
    let root = RootView()
    let sidebar = NSView()
    let scroll = NSScrollView()
    let canvas = FileCanvas()
    let footer = NSTextField(labelWithString: "")
    let hint = NSTextField(labelWithString: "Çift tık: aç  ·  ⌘tık: dışarıda aç")
    let search = NSSearchField(frame: NSRect(x: 0, y: 0, width: 280, height: 28))
    let findNavigation = NSSegmentedControl(labels: ["↑", "↓"], trackingMode: .momentary, target: nil, action: nil)
    let findCount = NSTextField(labelWithString: "0/0")
    var documentKind: String?
    var documentIndex = 0
    var savedGridQuery = ""
    let mode = NSSegmentedControl(labels: ["", ""], trackingMode: .selectOne, target: nil, action: nil)
    let zoom = NSSegmentedControl(labels: ["−", "Sığdır", "+"], trackingMode: .momentary, target: nil, action: nil)
    let backButton = NSButton(image: NSImage(systemSymbolName: "chevron.left", accessibilityDescription: "Dosyalara dön")!, target: nil, action: nil)
    var buttons: [(String, NSButton)] = []
    var all: [OutputFile] = []
    var category = "all"
    var loading = false
    var previewing: OutputFile?
    var preview: NSView?
    var web: WKWebView?
    var imageScroll: NSScrollView?
    var messageCount = 50
    var sidebarWidth: CGFloat { 174 }
    var visible: [OutputFile] { all.filter { (category == "all" || $0.category == category || (category == "file" && !["image", "html", "markdown", "json", "zip", "folder"].contains($0.category))) && matches($0, query: documentKind == nil ? search.stringValue : savedGridQuery) } }

    init(_ request: LaunchRequest) {
        self.request = request
        let window = OutputWindow(contentRect: NSRect(x: 0, y: 0, width: 1120, height: 760), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        super.init(window: window)
        window.owner = self; window.delegate = self
        window.title = "Çıktılar"; window.subtitle = "Son 50 mesaj · \(request.terminal)"
        window.minSize = NSSize(width: 740, height: 480)
        window.setFrameAutosaveName("HerdrOutputBrowser")
        if !window.setFrameUsingName("HerdrOutputBrowser") { window.center() }
        root.wantsLayer = true; root.layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor
        window.contentView = root
        root.addSubview(sidebar); root.addSubview(scroll); root.addSubview(footer); root.addSubview(hint)
        canvas.owner = self
        canvas.registerForDraggedTypes([.fileURL])
        scroll.hasVerticalScroller = true; scroll.autohidesScrollers = true; scroll.drawsBackground = true
        scroll.backgroundColor = .controlBackgroundColor; scroll.documentView = canvas
        footer.font = .systemFont(ofSize: 11.5); footer.textColor = .secondaryLabelColor
        hint.font = .systemFont(ofSize: 11); hint.textColor = .tertiaryLabelColor
        search.placeholderString = "Ara"; search.toolTip = "Dosya adı, yol ve konuşmadaki bağlamında ara"
        search.delegate = self; search.sendsSearchStringImmediately = true
        findNavigation.target = self; findNavigation.action = #selector(navigateFind)
        findCount.font = .monospacedDigitSystemFont(ofSize: 11.5, weight: .regular); findCount.textColor = .secondaryLabelColor
        mode.setImage(NSImage(systemSymbolName: "square.grid.2x2", accessibilityDescription: "Izgara"), forSegment: 0)
        mode.setImage(NSImage(systemSymbolName: "list.bullet", accessibilityDescription: "Liste"), forSegment: 1)
        mode.target = self; mode.action = #selector(changeViewMode); mode.selectedSegment = UserDefaults.standard.integer(forKey: "mode")
        canvas.listMode = mode.selectedSegment == 1
        zoom.target = self; zoom.action = #selector(changeZoom); zoom.isEnabled = false
        backButton.target = self; backButton.action = #selector(goBack); backButton.bezelStyle = .texturedRounded; backButton.isEnabled = false
        let toolbar = NSToolbar(identifier: "OutputsToolbar"); toolbar.delegate = self; toolbar.displayMode = .iconOnly
        window.toolbar = toolbar; window.toolbarStyle = .unifiedCompact
        buildSidebar()
        root.arrange = { [weak self] in self?.arrange() }
        arrange()
        reload()
    }
    required init?(coder: NSCoder) { fatalError() }

    func buildSidebar() {
        let groups = [("all", "Tüm çıktılar", "tray.full"), ("image", "Görseller", "photo"), ("html", "Web sayfaları", "globe"),
                      ("markdown", "Markdown", "doc.richtext"), ("json", "JSON", "curlybraces"),
                      ("zip", "Arşivler", "doc.zipper"), ("folder", "Klasörler", "folder"), ("file", "Diğer dosyalar", "doc")]
        for (index, group) in groups.enumerated() {
            let button = NSButton(title: group.1, target: self, action: #selector(filterChanged(_:)))
            button.tag = index; button.image = NSImage(systemSymbolName: group.2, accessibilityDescription: group.1)
            button.imagePosition = .imageLeading; button.alignment = .left; button.isBordered = false
            button.font = .systemFont(ofSize: 13); button.wantsLayer = true; button.layer?.cornerRadius = 6
            sidebar.addSubview(button); buttons.append((group.0, button))
        }
    }
    func arrange() {
        let bounds = root.bounds
        sidebar.frame = NSRect(x: 0, y: 28, width: sidebarWidth, height: max(0, bounds.height - 28))
        for (index, pair) in buttons.enumerated() {
            pair.1.frame = NSRect(x: 12, y: sidebar.bounds.height - 48 - CGFloat(index) * 35, width: sidebarWidth - 24, height: 30)
            pair.1.layer?.backgroundColor = (category == pair.0 ? NSColor.selectedContentBackgroundColor.withAlphaComponent(0.16) : NSColor.clear).cgColor
        }
        scroll.frame = NSRect(x: sidebarWidth, y: 28, width: max(0, bounds.width - sidebarWidth), height: max(0, bounds.height - 28))
        canvas.relayout(width: scroll.contentSize.width, minHeight: scroll.contentSize.height)
        footer.frame = NSRect(x: 14, y: 6, width: max(200, bounds.width / 2), height: 17)
        hint.frame = NSRect(x: max(260, bounds.width - 340), y: 6, width: 326, height: 17)
        hint.isHidden = bounds.width < 850 || previewing != nil
        preview?.frame = NSRect(x: 0, y: 28, width: bounds.width, height: max(0, bounds.height - 28))
    }
    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [NSToolbarItem.Identifier("back"), NSToolbarItem.Identifier("mode"), NSToolbarItem.Identifier("zoom"), .flexibleSpace,
         NSToolbarItem.Identifier("add"), NSToolbarItem.Identifier("copy"), NSToolbarItem.Identifier("finder"), NSToolbarItem.Identifier("refresh"), NSToolbarItem.Identifier("search")]
    }
    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] { toolbarDefaultItemIdentifiers(toolbar) + [NSToolbarItem.Identifier("documentFind")] }
    func toolbar(_ toolbar: NSToolbar, itemForItemIdentifier id: NSToolbarItem.Identifier, willBeInsertedIntoToolbar flag: Bool) -> NSToolbarItem? {
        let item = NSToolbarItem(itemIdentifier: id)
        switch id.rawValue {
        case "back": item.view = backButton; item.label = "Geri"
        case "mode": item.view = mode; item.label = "Görünüm"
        case "zoom": item.view = zoom; item.label = "Yakınlaştır"
        case "search": item.view = search; item.label = "Ara"
        case "documentFind":
            let stack = NSStackView(views: [findNavigation, findCount]); stack.orientation = .horizontal; stack.spacing = 8
            item.view = stack; item.label = "Belgede ara"
        default:
            let specs = ["add": ("plus", "Dosya veya klasör ekle", #selector(addAction)),
                         "copy": ("doc.on.doc", "Kopyala (⌘C)", #selector(copyAction)),
                         "finder": ("folder", "Finder’da göster", #selector(revealAction)),
                         "refresh": ("arrow.clockwise", "Yenile (⌘R)", #selector(refreshAction))]
            guard let spec = specs[id.rawValue] else { return nil }
            item.image = NSImage(systemSymbolName: spec.0, accessibilityDescription: spec.1)
            item.label = spec.1; item.toolTip = spec.1; item.target = self; item.action = spec.2
        }
        return item
    }
    func reload() {
        if loading { return }
        loading = true; footer.stringValue = "Son 50 mesaj okunuyor…"; canvas.needsDisplay = true
        let request = self.request
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            do {
                let data: Data
                if let fixture = request.fixture { data = try Data(contentsOf: URL(fileURLWithPath: fixture)) }
                else {
                    data = try scanData(request.app_home, payload: ["terminal": request.terminal])
                }
                let result = try JSONDecoder().decode(ScanResult.self, from: data)
                DispatchQueue.main.async {
                    guard let self = self else { return }
                    self.loading = false
                    if let error = result.error { self.showError(error); return }
                    let newPaths = Set(result.items.map(\.path))
                    self.all = self.all.filter { $0.source == "added" && !newPaths.contains($0.path) } + result.items
                    self.canvas.images.removeAll()
                    self.messageCount = result.message_count ?? 50
                    self.window?.subtitle = "Son \(self.messageCount) mesaj · \(request.terminal)"
                    self.refreshView()
                }
            } catch {
                DispatchQueue.main.async { self?.loading = false; self?.showError(error.localizedDescription) }
            }
        }
    }
    func refreshView() {
        canvas.files = visible
        canvas.anchor = nil
        canvas.selected.formIntersection(Set(visible.map(\.path)))
        arrange(); selectionChanged()
        let folder = URL(fileURLWithPath: request.app_home).appendingPathComponent("data/outputs-browser/status")
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let state: [String: Any] = ["terminal": request.terminal, "items": all.count, "visible": canvas.files.count,
                                    "messages": messageCount, "query": search.stringValue]
        if let data = try? JSONSerialization.data(withJSONObject: state) {
            try? data.write(to: folder.appendingPathComponent(request.terminal + ".json"), options: .atomic)
        }
    }
    func selectionChanged() {
        let count = canvas.selected.count
        footer.stringValue = count > 0 ? "\(count) seçili · \(canvas.files.count) öğe" : "\(canvas.files.count) öğe · En yeni paylaşım üstte"
    }
    func selectedFiles() -> [OutputFile] {
        if let file = previewing { return [file] }
        return canvas.files.filter { canvas.selected.contains($0.path) }
    }
    func copySelection() {
        let files = selectedFiles()
        if copyFiles(files, to: .general) { footer.stringValue = "\(files.count) öğe kopyalandı" }
        else { NSSound.beep() }
    }
    func selectAll() { if previewing == nil { canvas.selected = Set(canvas.files.map(\.path)); canvas.changed() } }
    func focusSearch() {
        if previewing != nil && documentKind == nil { back() }
        window?.makeFirstResponder(search); search.selectText(nil)
    }
    func controlTextDidChange(_ obj: Notification) {
        if documentKind != nil { documentIndex = 0; findInDocument(step: 0) } else { refreshView() }
    }
    func control(_ control: NSControl, textView: NSTextView, doCommandBy selector: Selector) -> Bool {
        guard documentKind != nil else { return false }
        if selector == #selector(NSResponder.insertNewline(_:)) { findInDocument(step: NSApp.currentEvent?.modifierFlags.contains(.shift) == true ? -1 : 1); return true }
        if selector == #selector(NSResponder.cancelOperation(_:)) { search.stringValue = ""; documentIndex = 0; findInDocument(step: 0); window?.makeFirstResponder(web); return true }
        return false
    }
    @objc func navigateFind() { findInDocument(step: findNavigation.selectedSegment == 0 ? -1 : 1) }
    func findInDocument(step: Int, completion: ((Int) -> Void)? = nil) {
        guard documentKind != nil, let web = web else { return }
        documentIndex += step
        let query = String(data: try! JSONSerialization.data(withJSONObject: search.stringValue, options: [.fragmentsAllowed]), encoding: .utf8)!
        web.evaluateJavaScript("window.Reader ? Reader.find(\(query),\(documentIndex)) : ({count:0,index:0})") { [weak self] result, _ in
            guard let self = self, let value = result as? [String: Any] else { return }
            let count = value["count"] as? Int ?? 0; self.documentIndex = value["index"] as? Int ?? 0
            self.findCount.stringValue = count == 0 ? "0/0" : "\(self.documentIndex + 1)/\(count)"
            completion?(count)
        }
    }
    @objc func changeViewMode() {
        canvas.listMode = mode.selectedSegment == 1
        UserDefaults.standard.set(mode.selectedSegment, forKey: "mode")
        arrange()
    }
    @objc func filterChanged(_ sender: NSButton) {
        category = buttons[sender.tag].0
        if previewing != nil { back() }
        refreshView()
    }
    @objc func refreshAction() { reload() }
    @objc func copyAction() { copySelection() }
    @objc func addAction() {
        guard let window = window else { return }
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = true
        panel.allowsMultipleSelection = true; panel.prompt = "Ekle"
        panel.beginSheetModal(for: window) { [weak self] response in
            if response == .OK { self?.addPaths(panel.urls.map(\.path).joined(separator: "\n")) }
        }
    }
    func addFromClipboard() {
        let urls = NSPasteboard.general.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL]
        addPaths(urls?.map(\.path).joined(separator: "\n") ?? NSPasteboard.general.string(forType: .string) ?? "")
    }
    func addPaths(_ text: String) {
        if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return }
        let appHome = request.app_home
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            do {
                let result = try JSONDecoder().decode(ScanResult.self, from: scanData(appHome, payload: ["text": text]))
                DispatchQueue.main.async {
                    guard let self = self else { return }
                    if result.items.isEmpty { self.showError("Bu yolda mevcut bir dosya bulunamadı."); return }
                    let paths = Set(result.items.map(\.path))
                    self.all = result.items + self.all.filter { !paths.contains($0.path) }
                    self.refreshView()
                }
            } catch { DispatchQueue.main.async { self?.showError(error.localizedDescription) } }
        }
    }
    @objc func revealAction() {
        let files = selectedFiles()
        if !files.isEmpty { NSWorkspace.shared.activateFileViewerSelecting(files.map(\.url)) }
    }
    @objc func goBack() { back() }
    @objc func changeZoom() {
        guard let scroll = imageScroll else { return }
        let index = zoom.selectedSegment
        if index == 1 {
            scroll.magnification = 1
            scroll.documentView?.frame.size = NSSize(width: root.bounds.width, height: max(100, root.bounds.height - 28))
        }
        else { scroll.magnification = min(8, max(0.2, scroll.magnification * (index == 0 ? 0.8 : 1.25))) }
    }
    func activate(_ file: OutputFile, external: Bool) {
        switch route(file, external: external) {
        case .finderReveal: NSWorkspace.shared.activateFileViewerSelecting([file.url])
        case .finderFolder: NSWorkspace.shared.open(file.url)
        case .previewApp: openApp(file.url, bundle: "com.apple.Preview")
        case .chrome: openApp(file.url, bundle: "com.google.Chrome")
        case .system: NSWorkspace.shared.open(file.url)
        case .image: previewImage(file)
        case .html: previewHTML(file)
        case .markdown: previewDocument(file, kind: "markdown")
        case .json: previewDocument(file, kind: "json")
        }
    }
    func openApp(_ url: URL, bundle: String) {
        guard let app = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundle) else { showError("İstenen uygulama bu Mac’te bulunamadı."); return }
        NSWorkspace.shared.open([url], withApplicationAt: app, configuration: NSWorkspace.OpenConfiguration()) { [weak self] _, error in
            if let error = error { DispatchQueue.main.async { self?.showError(error.localizedDescription) } }
        }
    }
    func beginPreview(_ file: OutputFile, view: NSView) {
        preview?.removeFromSuperview(); web = nil; imageScroll = nil
        previewing = file; preview = view
        scroll.isHidden = true; sidebar.isHidden = true
        root.addSubview(view); backButton.isEnabled = true; mode.isEnabled = false
        zoom.isEnabled = file.category == "image"; search.isEnabled = false
        window?.title = file.name; footer.stringValue = file.path
        arrange()
    }
    func previewImage(_ file: OutputFile) {
        guard let image = NSImage(contentsOf: file.url) else { showError("Görsel açılamadı."); return }
        let scroll = NSScrollView()
        scroll.drawsBackground = true; scroll.backgroundColor = .controlBackgroundColor
        scroll.hasVerticalScroller = true; scroll.hasHorizontalScroller = true
        scroll.autohidesScrollers = true; scroll.allowsMagnification = true; scroll.minMagnification = 0.2; scroll.maxMagnification = 8
        let view = NSImageView(); view.image = image; view.imageScaling = .scaleProportionallyUpOrDown
        let area = NSSize(width: root.bounds.width, height: max(100, root.bounds.height - 28))
        view.frame = NSRect(origin: .zero, size: area)
        scroll.documentView = view
        beginPreview(file, view: scroll); imageScroll = scroll
        window?.makeFirstResponder(canvas)
    }
    func previewHTML(_ file: OutputFile) {
        let view = WKWebView(frame: .zero)
        view.navigationDelegate = self; view.uiDelegate = self
        beginPreview(file, view: view); web = view
        view.loadFileURL(file.url, allowingReadAccessTo: file.url.deletingLastPathComponent())
    }
    func previewDocument(_ file: OutputFile, kind: String) {
        do {
            let size = (try file.url.resourceValues(forKeys: [.fileSizeKey])).fileSize ?? 0
            if size > 16_000_000 { showError("Belge 16 MB’tan büyük. Cmd+tıklama ile dış uygulamada açabilirsin."); return }
            let text = try String(contentsOf: file.url, encoding: .utf8)
            let payload: [String: Any] = ["kind": kind, "text": text, "name": file.name, "baseURL": file.url.deletingLastPathComponent().absoluteString + "/"]
            let json = String(data: try JSONSerialization.data(withJSONObject: payload), encoding: .utf8)!
            let configuration = WKWebViewConfiguration()
            configuration.setURLSchemeHandler(DocumentAssets(root: file.url.deletingLastPathComponent()), forURLScheme: "outputs-asset")
            let source = "window.__readerPayload=\(json);if(window.Reader)Reader.load(window.__readerPayload);"
            configuration.userContentController.addUserScript(WKUserScript(source: source, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
            configuration.userContentController.add(self, name: "reader")
            let view = WKWebView(frame: .zero, configuration: configuration)
            view.navigationDelegate = self; view.uiDelegate = self
            savedGridQuery = search.stringValue
            beginPreview(file, view: view); web = view; documentKind = kind
            search.isEnabled = true; search.stringValue = ""; search.placeholderString = "Belgede ara (⌘F)"; documentIndex = 0; findCount.stringValue = "0/0"
            if let toolbar = window?.toolbar, !toolbar.items.contains(where: { $0.itemIdentifier.rawValue == "documentFind" }) { toolbar.insertItem(withItemIdentifier: NSToolbarItem.Identifier("documentFind"), at: max(0, toolbar.items.count - 1)) }
            guard let resources = Bundle.main.resourceURL?.appendingPathComponent("reader") else { throw NSError(domain: "Reader", code: 1) }
            view.loadFileURL(resources.appendingPathComponent("index.html"), allowingReadAccessTo: resources)
        } catch { showError("Belge açılamadı: \(error.localizedDescription)") }
    }
    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "reader", let body = message.body as? [String: String], body["action"] == "copy", let text = body["text"] else { return }
        NSPasteboard.general.clearContents(); NSPasteboard.general.setString(text, forType: .string)
    }
    func back() {
        web?.configuration.userContentController.removeScriptMessageHandler(forName: "reader")
        if documentKind != nil { search.stringValue = savedGridQuery; search.placeholderString = "Ara"; documentKind = nil }
        if let toolbar = window?.toolbar, let index = toolbar.items.firstIndex(where: { $0.itemIdentifier.rawValue == "documentFind" }) { toolbar.removeItem(at: index) }
        preview?.removeFromSuperview(); preview = nil; previewing = nil; web = nil; imageScroll = nil
        scroll.isHidden = false; sidebar.isHidden = false
        backButton.isEnabled = false; mode.isEnabled = true; zoom.isEnabled = false; search.isEnabled = true
        window?.title = "Çıktılar"; arrange(); selectionChanged(); window?.makeFirstResponder(canvas)
    }
    func stepImage(_ direction: Int) {
        let images = canvas.files.filter { $0.category == "image" }
        guard let index = images.firstIndex(where: { $0.path == previewing?.path }), !images.isEmpty else { return }
        let file = images[(index + direction + images.count) % images.count]
        canvas.selected = [file.path]; previewImage(file)
    }
    func showError(_ text: String) { footer.stringValue = text; canvas.needsDisplay = true }
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if action.navigationType == .linkActivated, let url = action.request.url, ["http", "https"].contains(url.scheme ?? "") {
            openApp(url, bundle: "com.google.Chrome"); decisionHandler(.cancel)
        } else { decisionHandler(.allow) }
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { showError(error.localizedDescription) }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if documentKind != nil && CommandLine.arguments.contains("--verify-document") { verifyDocument(); return }
        if CommandLine.arguments.contains("--verify-html") {
            webView.evaluateJavaScript("document.getElementById('render-check').textContent") { result, error in
                if error != nil || result as? String != "HTML + CSS + JavaScript çalışıyor" { fputs("HTML render check failed: \(String(describing: result))\n", stderr); exit(1) }
                print("PASS: local HTML rendered by WebKit, JavaScript executed")
                if let index = CommandLine.arguments.firstIndex(of: "--snapshot"), CommandLine.arguments.count > index + 1 {
                    let configuration = WKSnapshotConfiguration()
                    webView.takeSnapshot(with: configuration) { image, error in
                        if let image = image, let tiff = image.tiffRepresentation,
                           let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
                            try? png.write(to: URL(fileURLWithPath: CommandLine.arguments[index + 1]))
                        }
                        NSApp.terminate(nil)
                    }
                } else { NSApp.terminate(nil) }
            }
        }
    }
    func verifyDocument() {
        guard let web = web, let kind = documentKind else { return }
        let checks = kind == "markdown" ? """
        (()=>{const state=Reader.inspect();if(!state.ready||state.error)throw Error('Markdown not ready');
        if(!document.querySelector('h1')||!document.querySelector('table')||!document.querySelector('pre code.hljs')||!document.querySelector('.hljs-keyword'))throw Error('Markdown features missing');
        const original=window.__readerPayload;Reader.load({...original,text:'<script>window.__bad=1</script><img src="x" onerror="window.__bad=1">'});
        if(window.__bad||document.querySelector('#content script,#content [onerror]'))throw Error('Markdown sanitization failed');Reader.load(original);return true})()
        """ : """
        (()=>{const state=Reader.inspect();if(!state.ready||state.error)throw Error('JSON not ready');
        if(!document.querySelector('.json-number')||!document.getElementById('content').textContent.includes('9007199254740993'))throw Error('JSON number precision lost');
        let invalid=false;try{Reader.parseJSON('{bad}')}catch(e){invalid=true}if(!invalid)throw Error('Invalid JSON accepted');
        Reader.expandAll();if(document.querySelector('details:not([open])'))throw Error('Expand failed');Reader.collapseAll();if(document.querySelector('details[open]'))throw Error('Collapse failed');return true})()
        """
        web.evaluateJavaScript(checks) { [weak self] value, error in
            guard let self = self else { return }
            if error != nil || value as? Bool != true { fputs("Document check failed: \(String(describing: error))\n", stderr); exit(1) }
            let file = self.previewing?.path
            self.focusSearch()
            if self.documentKind != kind || self.previewing?.path != file { fputs("Cmd+F left the document\n", stderr); exit(1) }
            self.search.stringValue = kind == "markdown" ? "KURULUM" : "gizli-deger"
            self.documentIndex = 0
            self.findInDocument(step: 0) { count in
                if count == 0 { fputs("Document search found no match\n", stderr); exit(1) }
                let probe = kind == "markdown" ? "document.querySelector('mark[data-find].active')!==null" : "(()=>{let n=document.querySelector('.json-active');if(!n)return false;for(let p=n.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS'&&!p.open)return false;return true})()"
                web.evaluateJavaScript(probe) { value, error in
                    if error != nil || value as? Bool != true { fputs("Document highlight/reveal failed\n", stderr); exit(1) }
                    print("PASS: \(kind) renderer, highlighting, document Cmd+F and search navigation\(kind == "json" ? ", expand/collapse and exact numbers" : ", tables, code and sanitization")")
                    if let i = CommandLine.arguments.firstIndex(of: "--snapshot"), CommandLine.arguments.count > i + 1 {
                        self.footer.stringValue = "Örnek belge · \(self.previewing?.name ?? "")"
                        self.window?.subtitle = "Belge görünümü · Cmd+F ile ara"
                        self.snapshotDocument(CommandLine.arguments[i + 1]) { NSApp.terminate(nil) }
                    } else { NSApp.terminate(nil) }
                }
            }
        }
    }
    func snapshotDocument(_ path: String, completion: @escaping () -> Void) {
        guard let web = web else { snapshot(path); completion(); return }
        web.takeSnapshot(with: WKSnapshotConfiguration()) { [weak self] webImage, error in
            guard let self = self, let webImage = webImage, error == nil else { completion(); return }
            let frame = self.window?.contentView?.superview ?? self.root
            frame.layoutSubtreeIfNeeded(); frame.displayIfNeeded()
            guard let bitmap = frame.bitmapImageRepForCachingDisplay(in: frame.bounds) else { completion(); return }
            frame.cacheDisplay(in: frame.bounds, to: bitmap)
            let image = NSImage(size: frame.bounds.size); image.lockFocus()
            bitmap.draw(in: frame.bounds)
            webImage.draw(in: frame.convert(web.bounds, from: web), from: .zero, operation: .sourceOver, fraction: 1)
            image.unlockFocus()
            if let tiff = image.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) { try? png.write(to: URL(fileURLWithPath: path)) }
            completion()
        }
    }
    func windowWillClose(_ notification: Notification) {
        web?.configuration.userContentController.removeScriptMessageHandler(forName: "reader")
        (NSApp.delegate as? AppDelegate)?.controllers.removeValue(forKey: request.terminal)
    }
    func snapshot(_ path: String) {
        root.layoutSubtreeIfNeeded(); root.displayIfNeeded()
        let view = window?.contentView?.superview ?? root
        guard let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return }
        view.cacheDisplay(in: view.bounds, to: rep)
        if let png = rep.representation(using: .png, properties: [:]) { try? png.write(to: URL(fileURLWithPath: path)) }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var controllers: [String: BrowserController] = [:]
    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let appItem = NSMenuItem(); let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Çıktılar’dan Çık", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu; menu.addItem(appItem)
        let fileItem = NSMenuItem(); let fileMenu = NSMenu(title: "Dosya")
        fileMenu.addItem(withTitle: "Pencereyi Kapat", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        fileItem.submenu = fileMenu; menu.addItem(fileItem)
        let editItem = NSMenuItem(); let editMenu = NSMenu(title: "Düzen")
        editMenu.addItem(withTitle: "Kes", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Kopyala", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Yapıştır", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Tümünü Seç", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = editMenu; menu.addItem(editItem)
        NSApp.mainMenu = menu
        if let index = CommandLine.arguments.firstIndex(of: "--request"), CommandLine.arguments.count > index + 1 {
            openRequest(URL(fileURLWithPath: CommandLine.arguments[index + 1]))
        }
    }
    func application(_ application: NSApplication, open urls: [URL]) { for url in urls { openRequest(url) } }
    func openRequest(_ url: URL) {
        do {
            let request = try JSONDecoder().decode(LaunchRequest.self, from: Data(contentsOf: url))
            let expected = Bundle.main.object(forInfoDictionaryKey: "HerdrAppHome") as? String ?? NSHomeDirectory() + "/.config/herdr-app"
            guard request.terminal.range(of: "^[A-Za-z0-9_-]+$", options: .regularExpression) != nil,
                  URL(fileURLWithPath: request.app_home).resolvingSymlinksInPath() == URL(fileURLWithPath: expected).resolvingSymlinksInPath(),
                  request.fixture == nil || CommandLine.arguments.contains("--snapshot") else {
                throw NSError(domain: "Request", code: 1, userInfo: [NSLocalizedDescriptionKey: "Geçersiz Çıktılar isteği."])
            }
            if let existing = controllers[request.terminal] { existing.reload(); existing.window?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true); return }
            let controller = BrowserController(request); controllers[request.terminal] = controller
            let args = CommandLine.arguments
            if let index = args.firstIndex(of: "--snapshot"), args.count > index + 1 {
                let path = args[index + 1]
                // Render only this helper's own content view; no desktop capture or input automation.
                controller.window?.alphaValue = 0; controller.window?.orderBack(nil)
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                    if args.contains("--list") { controller.mode.selectedSegment = 1; controller.canvas.listMode = true; controller.arrange() }
                    if let q = args.firstIndex(of: "--query"), args.count > q + 1 { controller.search.stringValue = args[q + 1]; controller.refreshView() }
                    if args.contains("--verify-html"), let file = controller.all.first(where: { $0.category == "html" && $0.name == "render-check.html" }) {
                        controller.previewHTML(file)
                        DispatchQueue.main.asyncAfter(deadline: .now() + 15) { fputs("HTML render check timed out\n", stderr); exit(1) }
                    } else if args.contains("--verify-document"), let i = args.firstIndex(of: "--document"), args.count > i + 1,
                              let file = controller.all.first(where: { $0.category == args[i + 1] }) {
                        controller.activate(file, external: false)
                        DispatchQueue.main.asyncAfter(deadline: .now() + 15) { fputs("Document check timed out\n", stderr); exit(1) }
                    } else {
                        controller.snapshot(path); print("snapshot: \(path)"); NSApp.terminate(nil)
                    }
                }
            } else {
                controller.showWindow(nil); controller.window?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
            }
        } catch { NSLog("Request failed: %@", error.localizedDescription) }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

func selfTest(_ fixture: String) throws {
    let result = try JSONDecoder().decode(ScanResult.self, from: Data(contentsOf: URL(fileURLWithPath: fixture)))
    guard let image = result.items.first(where: { $0.category == "image" }) else { fatalError("Image fixture required") }
    assert(fileClickAction(count: 1, command: false) == .select)
    assert(fileClickAction(count: 2, command: false) == .open)
    assert(fileClickAction(count: 1, command: true) == .openExternal)
    assert(fileClickAction(count: 2, command: true) == .openExternal)
    assert(route(image, external: false) == .image && route(image, external: true) == .previewApp)
    var html = image; html.kind = "html"; assert(route(html, external: false) == .html && route(html, external: true) == .chrome)
    var markdown = image; markdown.kind = "markdown"; assert(route(markdown, external: false) == .markdown && route(markdown, external: true) == .system)
    var json = image; json.kind = "json"; assert(route(json, external: false) == .json && route(json, external: true) == .system)
    var zip = image; zip.kind = "zip"; assert(route(zip, external: false) == .finderReveal && route(zip, external: true) == .finderReveal)
    var folder = image; folder.directory = true; assert(route(folder, external: false) == .finderFolder)
    var context = image; context.search_text = "Yeşil yüzen parçalı marka kimliği çizimleri"
    assert(matches(context, query: "yesil marka") && matches(context, query: "KİMLİĞİ") && !matches(context, query: "alakasız dosya"))
    let board = NSPasteboard(name: NSPasteboard.Name("HerdrOutputTests-\(UUID().uuidString)"))
    defer { board.releaseGlobally() }
    assert(copyFiles([image], to: board))
    assert(board.data(forType: .png) != nil && board.data(forType: .tiff) != nil)
    assert(board.string(forType: .fileURL) == image.url.absoluteString)
    let selectedImages = Array(result.items.filter { $0.category == "image" }.prefix(2))
    assert(copyFiles(selectedImages, to: board))
    assert(board.pasteboardItems?.count == selectedImages.count)
    assert(board.pasteboardItems?.allSatisfy { $0.data(forType: .png) != nil } == true)
    assert(board.string(forType: .string) == selectedImages.map(\.path).joined(separator: "\n"))
    assert(copyFiles([html, zip], to: board))
    assert(board.string(forType: .string) == html.path + "\n" + zip.path)
    board.clearContents()
    let urls = Array(result.items.prefix(3)).map { $0.url as NSURL }
    assert(board.writeObjects(urls))
    let restored = board.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) ?? []
    assert(restored.count == urls.count)
    assert(NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.Preview") != nil)
    assert(NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.google.Chrome") != nil)
    print("PASS: single-click selection, double-click opening, Cmd-click external opening, search, routes, clipboard and drag payloads")
}

if let index = CommandLine.arguments.firstIndex(of: "--self-test"), CommandLine.arguments.count > index + 1 {
    _ = NSApplication.shared
    do { try selfTest(CommandLine.arguments[index + 1]); exit(0) }
    catch { fputs("\(error)\n", stderr); exit(1) }
}
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
