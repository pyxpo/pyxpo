import AVFoundation
import UIKit

/// pyxpo-audio on iOS and the Mac: AVAudioPlayer for files (gapless loops), AVPlayer for URLs. Players are keyed
/// by the id Python gives them. Sound pauses while the app is in the background and plays on when it comes back.
final class AudioModule: PxModule {
    static let moduleName = "Audio"

    private final class Player {
        var file: AVAudioPlayer?
        var stream: AVPlayer?
        var loop: Bool
        var wantsPlay = false
        private var endToken: NSObjectProtocol?

        init(_ src: String, loop: Bool, volume: Float) throws {
            self.loop = loop
            if src.hasPrefix("http://") || src.hasPrefix("https://"), let url = URL(string: src) {
                let p = AVPlayer(url: url)
                p.actionAtItemEnd = .pause
                stream = p
                endToken = NotificationCenter.default.addObserver(
                    forName: .AVPlayerItemDidPlayToEndTime, object: p.currentItem, queue: .main) { [weak self] _ in
                    guard let self = self, self.loop, self.wantsPlay else { return }
                    p.seek(to: .zero)
                    p.play()
                }
            } else {
                let path = src.hasPrefix("file://") ? (URL(string: src)?.path ?? src) : src
                let p = try AVAudioPlayer(contentsOf: URL(fileURLWithPath: path))
                p.prepareToPlay()
                file = p
            }
            setLoop(loop)
            setVolume(volume)
        }

        deinit {
            if let t = endToken { NotificationCenter.default.removeObserver(t) }
            file?.stop()
            stream?.pause()
        }

        func setLoop(_ on: Bool) {
            loop = on
            file?.numberOfLoops = on ? -1 : 0
        }

        func setVolume(_ v: Float) {
            file?.volume = v
            stream?.volume = v
        }

        func play() {
            wantsPlay = true
            resume()
        }

        /// Plays without changing what Python asked for (used when the app comes back to the foreground).
        func resume() {
            if let p = stream {
                if let item = p.currentItem, item.currentTime() >= item.duration, item.duration.isNumeric {
                    p.seek(to: .zero)
                }
                p.play()
            }
            file?.play()
        }

        func pause(keepWish: Bool = false) {
            if !keepWish { wantsPlay = false }
            file?.pause()
            stream?.pause()
        }

        func seek(_ t: Double) {
            if let p = file { p.currentTime = min(t, p.duration) }
            stream?.seek(to: CMTime(seconds: t, preferredTimescale: 600))
        }
    }

    private var players: [Int: Player] = [:]
    private var observers: [NSObjectProtocol] = []
    private var sessionReady = false

    required init() {}

    deinit {
        observers.forEach { NotificationCenter.default.removeObserver($0) }
    }

    private func prepareSession() {
        if sessionReady { return }
        sessionReady = true
        let s = AVAudioSession.sharedInstance()
        try? s.setCategory(.playback, mode: .default, options: [.mixWithOthers])
        try? s.setActive(true)
        let nc = NotificationCenter.default
        observers.append(nc.addObserver(forName: UIApplication.didEnterBackgroundNotification, object: nil,
                                        queue: .main) { [weak self] _ in
            self?.players.values.forEach { if $0.wantsPlay { $0.pause(keepWish: true) } }
        })
        observers.append(nc.addObserver(forName: UIApplication.willEnterForegroundNotification, object: nil,
                                        queue: .main) { [weak self] _ in
            self?.players.values.forEach { if $0.wantsPlay { $0.resume() } }
        })
    }

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        guard let id = (args.first as? NSNumber)?.intValue else { reply(nil, "Audio.\(method) needs a player id"); return }
        let num = { (i: Int) -> Double? in args.count > i ? (args[i] as? NSNumber)?.doubleValue : nil }
        switch method {
        case "create":
            prepareSession()
            guard let src = args.count > 1 ? args[1] as? String : nil else { reply(nil, "Audio.create needs a source"); return }
            do {
                players[id] = try Player(src, loop: (args.count > 2 ? args[2] as? Bool : nil) ?? false,
                                         volume: Float(num(3) ?? 1))
            } catch {
                reply(nil, "cannot open \(src): \(error.localizedDescription)")
                return
            }
        case "play": players[id]?.play()
        case "pause": players[id]?.pause()
        case "seek": players[id]?.seek(num(1) ?? 0)
        case "set":
            let o = args.count > 1 ? args[1] as? [String: Any] ?? [:] : [:]
            if let l = o["loop"] as? Bool { players[id]?.setLoop(l) }
            if let v = (o["volume"] as? NSNumber)?.floatValue { players[id]?.setVolume(v) }
        case "release":
            players[id]?.pause()
            players[id] = nil
        default:
            reply(nil, "unknown native call Audio.\(method)")
            return
        }
        reply(nil, nil)
    }
}
