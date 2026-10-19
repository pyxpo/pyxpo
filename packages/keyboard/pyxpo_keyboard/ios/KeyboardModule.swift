import UIKit

/// The app side of the keyboard on iOS. The keyboard itself is an app extension, which this version does not
/// add yet: `status` reports it as unsupported, and `openSettings` opens the app's page in Settings.
final class KeyboardModule: PxModule {
    static let moduleName = "Keyboard"

    required init() {}

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        switch method {
        case "status":
            reply(["supported": false, "enabled": false, "selected": false, "id": ""], nil)
        case "openSettings":
            if let url = URL(string: UIApplication.openSettingsURLString) {
                UIApplication.shared.open(url)
            }
            reply(nil, nil)
        case "showPicker", "getOptions", "setOptions":
            reply(nil, "Keyboard.\(method) is not supported on iOS yet")
        default:
            reply(nil, "unknown native call Keyboard.\(method)")
        }
    }
}
