import AVFoundation
import AVKit
import UIKit

/// pyxpo-video on iOS and the Mac (Catalyst): `PxVideoView` plays a file or URL with AVPlayer in an
/// AVPlayerViewController, so the system controls (play, scrub, full screen) come for free.
final class VideoModule: PxViewModule {
    static let moduleName = "Video"
    static let viewTypes = ["PxVideoView"]

    required init() {}

    func makeView(_ ctx: PxModuleContext, _ type: String, _ emit: @escaping (String, Any?) -> Void) -> PxNativeView {
        PxVideoView(emit)
    }

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        DispatchQueue.main.async {
            guard let tag = (args.first as? NSNumber)?.intValue, let v = ctx.view(tag) as? PxVideoView else {
                reply(nil, "The VideoView is not mounted")
                return
            }
            switch method {
            case "play": v.player.play()
            case "pause": v.player.pause()
            case "seek":
                let s = args.count > 1 ? (args[1] as? NSNumber)?.doubleValue ?? 0 : 0
                v.player.seek(to: CMTime(seconds: s, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
            default:
                reply(nil, "Video has no method \(method)")
                return
            }
            reply(nil, nil)
        }
    }
}

/// Holds the AVPlayerViewController's view and makes the controller a child of the nearest one on screen,
/// which its controls need.
final class VideoHost: UIView {
    let controller = AVPlayerViewController()

    override init(frame: CGRect) {
        super.init(frame: frame)
        clipsToBounds = true
        backgroundColor = .black
        controller.view.frame = bounds
        controller.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        controller.view.backgroundColor = .black
        addSubview(controller.view)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        if window != nil, controller.parent == nil, let parent = owner() {
            parent.addChild(controller)
            controller.didMove(toParent: parent)
        } else if window == nil, controller.parent != nil {
            controller.willMove(toParent: nil)
            controller.removeFromParent()
        }
    }

    private func owner() -> UIViewController? {
        var r: UIResponder? = next
        while let x = r {
            if let vc = x as? UIViewController { return vc }
            r = x.next
        }
        return nil
    }
}

final class PxVideoView: PxNativeView {
    let host = VideoHost()
    let player = AVPlayer()
    var view: UIView { host }

    private let emit: (String, Any?) -> Void
    private var source: String?
    private var playing = true
    private var loop = false
    private var loaded = false
    private var status: NSKeyValueObservation?
    private var ended: NSObjectProtocol?

    init(_ emit: @escaping (String, Any?) -> Void) {
        self.emit = emit
        host.controller.player = player
        host.controller.videoGravity = .resizeAspect
        ended = NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: nil,
                                                       queue: .main) { [weak self] n in
            guard let self = self, let item = n.object as? AVPlayerItem, item === self.player.currentItem else { return }
            if self.loop {
                self.player.seek(to: .zero)
                self.player.play()
            } else {
                self.emit("end", nil)
            }
        }
    }

    func update(_ props: [String: Any], _ removed: [String]) {
        if let l = props["loop"] as? Bool { loop = l }
        if let m = props["muted"] as? Bool { player.isMuted = m }
        if let c = props["controls"] as? Bool { host.controller.showsPlaybackControls = c }
        if let r = props["resize_mode"] as? String {
            host.controller.videoGravity = r == "cover" ? .resizeAspectFill : r == "stretch" ? .resize : .resizeAspect
        }
        if props.keys.contains("source") {
            let s = props["source"] as? String
            if s != source { source = s; load() }
        }
        if let p = props["playing"] as? Bool {
            playing = p
            if p { player.play() } else { player.pause() }
        }
    }

    private func load() {
        status = nil
        loaded = false
        guard let s = source, let url = s.contains("://") ? URL(string: s) : URL(fileURLWithPath: s) else {
            player.replaceCurrentItem(with: nil)
            return
        }
        let item = AVPlayerItem(url: url)
        status = item.observe(\.status, options: [.initial, .new]) { [weak self] item, _ in
            DispatchQueue.main.async { self?.changed(item) }
        }
        player.replaceCurrentItem(with: item)
        if playing { player.play() }
    }

    private func changed(_ item: AVPlayerItem) {
        guard item === player.currentItem else { return }
        switch item.status {
        case .readyToPlay where !loaded:
            loaded = true
            let d = item.duration.seconds
            let size = item.presentationSize
            emit("load", ["duration": d.isFinite ? d : 0, "width": Double(size.width), "height": Double(size.height)])
        case .failed:
            emit("error", ["message": item.error?.localizedDescription ?? "cannot play the video"])
        default:
            break
        }
    }

    func dispose() {
        status = nil
        if let e = ended { NotificationCenter.default.removeObserver(e) }
        ended = nil
        player.pause()
        player.replaceCurrentItem(with: nil)
        if host.controller.parent != nil {
            host.controller.willMove(toParent: nil)
            host.controller.removeFromParent()
        }
    }
}
