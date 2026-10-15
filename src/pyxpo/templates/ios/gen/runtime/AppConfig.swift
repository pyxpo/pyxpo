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
