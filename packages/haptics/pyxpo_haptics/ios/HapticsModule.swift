import UIKit

/// expo-haptics on iOS: the UIKit feedback generators. The Simulator has no Taptic Engine, so calls succeed
/// there without anything to feel.
final class HapticsModule: PxModule {
    static let moduleName = "Haptics"

    required init() {}

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        let value = args.first as? String ?? ""
        switch method {
        case "impact":
            let style: UIImpactFeedbackGenerator.FeedbackStyle
            switch value {
            case "light": style = .light
            case "medium": style = .medium
            case "heavy": style = .heavy
            case "rigid": style = .rigid
            case "soft": style = .soft
            default: reply(nil, "unknown ImpactFeedbackStyle '\(value)'"); return
            }
            let g = UIImpactFeedbackGenerator(style: style)
            g.prepare()
            g.impactOccurred()
        case "notification":
            let type: UINotificationFeedbackGenerator.FeedbackType
            switch value {
            case "success": type = .success
            case "warning": type = .warning
            case "error": type = .error
            default: reply(nil, "unknown NotificationFeedbackType '\(value)'"); return
            }
            let g = UINotificationFeedbackGenerator()
            g.prepare()
            g.notificationOccurred(type)
        case "selection":
            let g = UISelectionFeedbackGenerator()
            g.prepare()
            g.selectionChanged()
        default:
            reply(nil, "unknown native call Haptics.\(method)")
            return
        }
        reply(nil, nil)
    }
}
