import AuthenticationServices
import SafariServices
import UIKit

/// In-app browser (SFSafariViewController) and sign-in sessions (ASWebAuthenticationSession).
final class WebBrowserModule: PxModule {
    static let moduleName = "WebBrowser"

    private var browser: SFSafariViewController?
    private var browserReply: PxReply?
    private var browserDelegate: BrowserDelegate?
    private var auth: ASWebAuthenticationSession?
    private var authReply: PxReply?
    private var authAnchor: AuthAnchor?

    required init() {}

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        switch method {
        case "open": open(ctx, args, reply)
        case "dismiss": dismiss(reply)
        case "auth": startAuth(ctx, args, reply)
        case "dismissAuth":
            if let session = auth {
                session.cancel()
                finishAuth(["type": "dismiss"], nil)
            }
            reply(nil, nil)
        default: reply(nil, "unknown native call WebBrowser.\(method)")
        }
    }

    private static func color(_ v: Any?) -> UIColor? {
        guard let n = v as? NSNumber else { return nil }
        let c = n.uint32Value
        return UIColor(red: CGFloat((c >> 16) & 0xFF) / 255, green: CGFloat((c >> 8) & 0xFF) / 255,
                       blue: CGFloat(c & 0xFF) / 255, alpha: CGFloat((c >> 24) & 0xFF) / 255)
    }

    private static let styles: [String: UIModalPresentationStyle] = [
        "fullScreen": .fullScreen, "pageSheet": .pageSheet, "formSheet": .formSheet, "currentContext": .currentContext,
        "overFullScreen": .overFullScreen, "overCurrentContext": .overCurrentContext, "popover": .popover,
        "automatic": .automatic,
    ]

    private func open(_ ctx: PxModuleContext, _ args: [Any], _ reply: @escaping PxReply) {
        guard browser == nil else { reply(["type": "locked"], nil); return }
        guard let s = args.first as? String, let url = URL(string: s) else { reply(nil, "bad URL"); return }
        let o = (args.count > 1 ? args[1] as? [String: Any] : nil) ?? [:]
        guard let top = ctx.presenter() else { reply(nil, "no view controller to present the browser"); return }
        let config = SFSafariViewController.Configuration()
        config.barCollapsingEnabled = (o["enableBarCollapsing"] as? Bool) ?? false
        config.entersReaderIfAvailable = (o["readerMode"] as? Bool) ?? false
        let vc = SFSafariViewController(url: url, configuration: config)
        switch o["dismissButtonStyle"] as? String {
        case "close": vc.dismissButtonStyle = .close
        case "cancel": vc.dismissButtonStyle = .cancel
        default: vc.dismissButtonStyle = .done
        }
        if let c = Self.color(o["toolbarColor"]) { vc.preferredBarTintColor = c }
        if let c = Self.color(o["controlsColor"]) { vc.preferredControlTintColor = c }
        let style = Self.styles[(o["presentationStyle"] as? String) ?? ""] ?? .overFullScreen
        vc.modalPresentationStyle = style
        if style == .popover, let pop = vc.popoverPresentationController {
            pop.sourceView = top.view
            pop.sourceRect = CGRect(x: top.view.bounds.midX, y: top.view.bounds.midY, width: 0, height: 0)
        }
        let delegate = BrowserDelegate { [weak self] in self?.finishBrowser(["type": "cancel"]) }
        vc.delegate = delegate
        // A swipe-down on a sheet closes it without safariViewControllerDidFinish.
        vc.presentationController?.delegate = delegate
        browser = vc
        browserReply = reply
        browserDelegate = delegate
        top.present(vc, animated: true)
    }

    private func finishBrowser(_ result: [String: Any]) {
        let r = browserReply
        browser = nil
        browserReply = nil
        browserDelegate = nil
        r?(result, nil)
    }

    private func dismiss(_ reply: @escaping PxReply) {
        guard let vc = browser else { reply(["type": "dismiss"], nil); return }
        vc.dismiss(animated: true) { [weak self] in
            self?.finishBrowser(["type": "dismiss"])
            reply(["type": "dismiss"], nil)
        }
    }

    private func startAuth(_ ctx: PxModuleContext, _ args: [Any], _ reply: @escaping PxReply) {
        guard auth == nil else { reply(["type": "locked"], nil); return }
        guard let s = args.first as? String, let url = URL(string: s) else { reply(nil, "bad URL"); return }
        let redirect = (args.count > 1 ? args[1] as? String : nil) ?? ""
        let o = (args.count > 2 ? args[2] as? [String: Any] : nil) ?? [:]
        let scheme = URL(string: redirect)?.scheme
        guard let window = ctx.presenter()?.view.window else { reply(nil, "no window to present the sign-in page"); return }
        let session = ASWebAuthenticationSession(url: url, callbackURLScheme: scheme) { [weak self] callback, error in
            DispatchQueue.main.async {
                if let callback = callback {
                    self?.finishAuth(["type": "success", "url": callback.absoluteString], nil)
                } else if let e = error as? ASWebAuthenticationSessionError, e.code == .canceledLogin {
                    self?.finishAuth(["type": "cancel"], nil)
                } else {
                    self?.finishAuth(nil, error?.localizedDescription ?? "sign-in failed")
                }
            }
        }
        let anchor = AuthAnchor(window)
        session.presentationContextProvider = anchor
        session.prefersEphemeralWebBrowserSession = (o["preferEphemeralSession"] as? Bool) ?? false
        auth = session
        authReply = reply
        authAnchor = anchor
        if !session.start() {
            finishAuth(nil, "could not start the sign-in session")
        }
    }

    private func finishAuth(_ result: [String: Any]?, _ error: String?) {
        guard let r = authReply else { return }
        auth = nil
        authReply = nil
        authAnchor = nil
        r(result, error)
    }
}

private final class BrowserDelegate: NSObject, SFSafariViewControllerDelegate, UIAdaptivePresentationControllerDelegate {
    private let onClose: () -> Void

    init(_ onClose: @escaping () -> Void) { self.onClose = onClose }

    func safariViewControllerDidFinish(_ controller: SFSafariViewController) { onClose() }

    func presentationControllerDidDismiss(_ presentationController: UIPresentationController) { onClose() }
}

private final class AuthAnchor: NSObject, ASWebAuthenticationPresentationContextProviding {
    private let window: UIWindow

    init(_ window: UIWindow) { self.window = window }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor { window }
}
