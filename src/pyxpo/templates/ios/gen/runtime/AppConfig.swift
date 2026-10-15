import UIKit

/// App config values written to Info.plist by `pyxpo build` (`PyxpoBackgroundColor`, `PyxpoStatusBar*`).
enum PxAppConfig {
    static func string(_ key: String) -> String? { Bundle.main.object(forInfoDictionaryKey: key) as? String }

    /// CSS order: #RGB, #RRGGBB or #RRGGBBAA.
    static func parse(_ s: String?) -> UIColor? {
        guard var h = s?.trimmingCharacters(in: .whitespaces), h.hasPrefix("#") else { return nil }
        h.removeFirst()
        if h.count == 3 { h = h.map { "\($0)\($0)" }.joined() }
        guard h.count == 6 || h.count == 8, let n = UInt64(h, radix: 16) else { return nil }
        let a = h.count == 8 ? CGFloat(n & 255) / 255 : 1
        let rgb = h.count == 8 ? n >> 8 : n
        return UIColor(red: CGFloat((rgb >> 16) & 255) / 255, green: CGFloat((rgb >> 8) & 255) / 255,
                       blue: CGFloat(rgb & 255) / 255, alpha: a)
    }

    static func apply(container: UIView) {
        if let c = parse(string("PyxpoBackgroundColor")) { container.backgroundColor = c }
        let vc = PxRootViewController.shared
        switch string("PyxpoStatusBarStyle") {
        case "light": vc?.setBarStyle(light: true)
        case "dark": vc?.setBarStyle(light: false)
        default: break
        }
        if (Bundle.main.object(forInfoDictionaryKey: "PyxpoStatusBarHidden") as? Bool) == true { vc?.setBarHidden(true) }
    }
}

/// In-app copy of the launch screen: stays up until the first batch is applied, or until `SplashScreen.hide()` when
/// the app called `SplashScreen.prevent_auto_hide()`. Debug builds honour `PYXPO_SPLASH_HOLD_MS` (screenshots, tests).
final class PxSplash {
    private var view: UIView?
    private var held = false
    private var first = true

    func show(in container: UIView) {
        let v = UIView(frame: container.bounds)
        v.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        v.backgroundColor = UIColor(named: "SplashBackground") ?? PxAppConfig.parse(PxAppConfig.string("PyxpoBackgroundColor"))
        if let img = UIImage(named: "SplashImage") {
            let iv = UIImageView(image: img)
            iv.center = CGPoint(x: v.bounds.midX, y: v.bounds.midY)
            iv.autoresizingMask = [.flexibleLeftMargin, .flexibleRightMargin, .flexibleTopMargin, .flexibleBottomMargin]
            v.addSubview(iv)
        }
        container.addSubview(v)
        view = v
    }

    func preventAutoHide() { held = true }

    /// Called after every applied batch; the first one decides whether the splash goes away on its own.
    func batchApplied() {
        guard first else { return }
        first = false
        var holdMs = 0
        #if DEBUG
        holdMs = Int(ProcessInfo.processInfo.environment["PYXPO_SPLASH_HOLD_MS"] ?? "") ?? 0
        #endif
        if holdMs > 0 { DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(holdMs)) { [weak self] in self?.hide() } }
        else if !held { hide() }
    }

    func hide() {
        guard let v = view else { return }
        view = nil
        UIView.animate(withDuration: 0.25, animations: { v.alpha = 0 }, completion: { _ in v.removeFromSuperview() })
    }
}
