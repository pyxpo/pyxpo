import UIKit

/// expo-device on iOS. Constants are read once at startup; the model name comes from a table of iPhone
/// identifiers (unknown models, iPads and newer phones report the raw identifier, for example "iPad14,1").
final class DeviceModule: PxModule {
    static let moduleName = "Device"

    required init() {}

    /// iPhone identifier: (marketing name, release year).
    private static let iPhones: [String: (String, Int)] = [
        "iPhone10,1": ("iPhone 8", 2017), "iPhone10,4": ("iPhone 8", 2017),
        "iPhone10,2": ("iPhone 8 Plus", 2017), "iPhone10,5": ("iPhone 8 Plus", 2017),
        "iPhone10,3": ("iPhone X", 2017), "iPhone10,6": ("iPhone X", 2017),
        "iPhone11,2": ("iPhone XS", 2018), "iPhone11,4": ("iPhone XS Max", 2018),
        "iPhone11,6": ("iPhone XS Max", 2018), "iPhone11,8": ("iPhone XR", 2018),
        "iPhone12,1": ("iPhone 11", 2019), "iPhone12,3": ("iPhone 11 Pro", 2019),
        "iPhone12,5": ("iPhone 11 Pro Max", 2019), "iPhone12,8": ("iPhone SE (2nd generation)", 2020),
        "iPhone13,1": ("iPhone 12 mini", 2020), "iPhone13,2": ("iPhone 12", 2020),
        "iPhone13,3": ("iPhone 12 Pro", 2020), "iPhone13,4": ("iPhone 12 Pro Max", 2020),
        "iPhone14,4": ("iPhone 13 mini", 2021), "iPhone14,5": ("iPhone 13", 2021),
        "iPhone14,2": ("iPhone 13 Pro", 2021), "iPhone14,3": ("iPhone 13 Pro Max", 2021),
        "iPhone14,6": ("iPhone SE (3rd generation)", 2022), "iPhone14,7": ("iPhone 14", 2022),
        "iPhone14,8": ("iPhone 14 Plus", 2022), "iPhone15,2": ("iPhone 14 Pro", 2022),
        "iPhone15,3": ("iPhone 14 Pro Max", 2022), "iPhone15,4": ("iPhone 15", 2023),
        "iPhone15,5": ("iPhone 15 Plus", 2023), "iPhone16,1": ("iPhone 15 Pro", 2023),
        "iPhone16,2": ("iPhone 15 Pro Max", 2023), "iPhone17,3": ("iPhone 16", 2024),
        "iPhone17,4": ("iPhone 16 Plus", 2024), "iPhone17,1": ("iPhone 16 Pro", 2024),
        "iPhone17,2": ("iPhone 16 Pro Max", 2024), "iPhone17,5": ("iPhone 16e", 2025),
        "iPhone18,3": ("iPhone 17", 2025), "iPhone18,1": ("iPhone 17 Pro", 2025),
        "iPhone18,2": ("iPhone 17 Pro Max", 2025), "iPhone18,4": ("iPhone Air", 2025),
        "iPhone18,5": ("iPhone 17e", 2026), "iPhone19,2": ("iPhone 18 Pro", 2026),
        "iPhone19,3": ("iPhone 18 Pro Max", 2026),
    ]

    private static func sysctlString(_ name: String) -> String? {
        var size = 0
        guard sysctlbyname(name, nil, &size, nil, 0) == 0, size > 0 else { return nil }
        var buf = [CChar](repeating: 0, count: size)
        guard sysctlbyname(name, &buf, &size, nil, 0) == 0 else { return nil }
        return String(cString: buf)
    }

    private static var isSimulator: Bool {
        #if targetEnvironment(simulator)
        return true
        #else
        return false
        #endif
    }

    private static var modelId: String? {
        if isSimulator, let id = ProcessInfo.processInfo.environment["SIMULATOR_MODEL_IDENTIFIER"] { return id }
        return sysctlString("hw.machine")
    }

    private static var deviceType: Int {
        if ProcessInfo.processInfo.isiOSAppOnMac || ProcessInfo.processInfo.isMacCatalystApp { return 3 }
        switch UIDevice.current.userInterfaceIdiom {
        case .phone: return 1
        case .pad: return 2
        case .mac: return 3
        case .tv: return 4
        default: return 0
        }
    }

    static var constants: [String: Any] {
        let d = UIDevice.current
        let id = modelId
        let known = id.flatMap { iPhones[$0] }
        let build: Any = sysctlString("kern.osversion") ?? NSNull()
        var arch = "arm64"
        #if arch(x86_64)
        arch = "x86_64"
        #endif
        return [
            "isDevice": !isSimulator,
            "brand": "Apple",
            "manufacturer": "Apple",
            "modelName": known?.0 ?? id ?? NSNull(),
            "modelId": id ?? NSNull(),
            "designName": NSNull(),
            "productName": NSNull(),
            "deviceYearClass": known?.1 ?? NSNull(),
            "totalMemory": ProcessInfo.processInfo.physicalMemory,
            "supportedCpuArchitectures": [arch],
            "osName": d.userInterfaceIdiom == .pad ? "iPadOS" : d.systemName,
            "osVersion": d.systemVersion,
            "osBuildId": build,
            "osInternalBuildId": build,
            "osBuildFingerprint": NSNull(),
            "platformApiLevel": NSNull(),
            "deviceName": d.name,
            "deviceType": deviceType,
        ]
    }

    private static var looksJailbroken: Bool {
        if isSimulator { return false }
        let paths = ["/Applications/Cydia.app", "/Library/MobileSubstrate/MobileSubstrate.dylib", "/bin/bash",
                     "/usr/sbin/sshd", "/etc/apt", "/private/var/lib/apt/", "/var/jb"]
        if paths.contains(where: { FileManager.default.fileExists(atPath: $0) }) { return true }
        // A sandboxed app cannot write outside its container.
        let probe = "/private/pyxpo-jb-probe.txt"
        if (try? "x".write(toFile: probe, atomically: true, encoding: .utf8)) != nil {
            try? FileManager.default.removeItem(atPath: probe)
            return true
        }
        return false
    }

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        switch method {
        case "getUptime": reply(Int(ProcessInfo.processInfo.systemUptime * 1000), nil)
        case "isRooted": reply(Self.looksJailbroken, nil)
        default: reply(nil, "Device has no method '\(method)'")
        }
    }
}
