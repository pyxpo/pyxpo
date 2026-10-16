import UIKit

/// expo-application on iOS. Constants come from the main bundle's Info.plist; signing details from the
/// embedded provisioning profile (absent in App Store and Simulator builds).
final class ApplicationModule: PxModule {
    static let moduleName = "Application"

    required init() {}

    static var constants: [String: Any] {
        let info = Bundle.main.infoDictionary ?? [:]
        let name = info["CFBundleDisplayName"] ?? info["CFBundleName"]
        return [
            "applicationName": name ?? NSNull(),
            "applicationId": Bundle.main.bundleIdentifier ?? NSNull(),
            "nativeApplicationVersion": info["CFBundleShortVersionString"] ?? NSNull(),
            "nativeBuildVersion": info["CFBundleVersion"] ?? NSNull(),
        ]
    }

    /// The plist inside embedded.mobileprovision (a CMS envelope around plain XML).
    private static var profile: [String: Any]? {
        guard let url = Bundle.main.url(forResource: "embedded", withExtension: "mobileprovision"),
              let data = try? Data(contentsOf: url),
              let start = data.range(of: Data("<?xml".utf8)),
              let end = data.range(of: Data("</plist>".utf8), in: start.lowerBound..<data.endIndex) else { return nil }
        let xml = data.subdata(in: start.lowerBound..<end.upperBound)
        return (try? PropertyListSerialization.propertyList(from: xml, format: nil)) as? [String: Any]
    }

    private static var releaseType: Int {
        #if targetEnvironment(simulator)
        return 1
        #else
        guard let p = profile else { return 5 }  // no profile: App Store (or TestFlight)
        if p["ProvisionsAllDevices"] as? Bool == true { return 2 }
        let ent = p["Entitlements"] as? [String: Any] ?? [:]
        if p["ProvisionedDevices"] != nil { return ent["get-task-allow"] as? Bool == true ? 3 : 4 }
        return 5
        #endif
    }

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        switch method {
        case "getInstallationTime":
            let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            guard let attrs = try? FileManager.default.attributesOfItem(atPath: docs.path),
                  let date = attrs[.creationDate] as? Date else { reply(nil, "could not read the install time"); return }
            reply(date.timeIntervalSince1970 * 1000, nil)
        case "getIdForVendor":
            reply(UIDevice.current.identifierForVendor?.uuidString ?? NSNull(), nil)
        case "getReleaseType":
            reply(Self.releaseType, nil)
        case "getPushEnvironment":
            let ent = Self.profile?["Entitlements"] as? [String: Any]
            reply(ent?["aps-environment"] as? String ?? NSNull(), nil)
        default:
            reply(nil, "Application has no method '\(method)'")
        }
    }
}
