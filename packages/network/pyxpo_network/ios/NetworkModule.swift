import Foundation
import Network

/// expo-network on iOS. One `NWPathMonitor` runs from the first call; all of its state lives on `queue`.
final class NetworkModule: PxModule {
    static let moduleName = "Network"

    private let queue = DispatchQueue(label: "dev.pyxpo.network")
    private var monitor: NWPathMonitor?
    private var path: NWPath?
    private var waiting: [PxReply] = []
    private weak var observer: PxModuleContext?

    required init() {}

    deinit { monitor?.cancel() }

    private func start() {
        guard monitor == nil else { return }
        let m = NWPathMonitor()
        m.pathUpdateHandler = { [weak self] p in self?.update(p) }
        monitor = m
        m.start(queue: queue)
    }

    /// On `queue`.
    private func update(_ p: NWPath) {
        path = p
        let state = Self.state(p)
        let replies = waiting
        waiting = []
        replies.forEach { $0(state, nil) }
        observer?.emit("Network.state", state)
    }

    private static func state(_ p: NWPath) -> [String: Any] {
        let up = p.status == .satisfied
        let type: String
        if !up { type = "NONE" }
        else if p.usesInterfaceType(.wifi) { type = "WIFI" }
        else if p.usesInterfaceType(.cellular) { type = "CELLULAR" }
        else if p.usesInterfaceType(.wiredEthernet) { type = "ETHERNET" }
        else if p.usesInterfaceType(.other) {
            // Virtual interfaces: utun/ipsec/ppp are VPN tunnels.
            let vpn = p.availableInterfaces.contains { i in
                i.type == .other && ["utun", "ipsec", "ppp", "tap", "tun"].contains { i.name.hasPrefix($0) }
            }
            type = vpn ? "VPN" : "OTHER"
        }
        else { type = "UNKNOWN" }
        return ["type": type, "isConnected": up, "isInternetReachable": up]
    }

    /// The IPv4 address of the interface in use: Wi-Fi (en0) first, then cellular (pdp_ip0), then any other.
    private static func ipAddress() -> String {
        var found: [String: String] = [:]
        var head: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&head) == 0, let first = head else { return "0.0.0.0" }
        defer { freeifaddrs(head) }
        var cur: UnsafeMutablePointer<ifaddrs>? = first
        while let ifa = cur {
            defer { cur = ifa.pointee.ifa_next }
            let flags = Int32(ifa.pointee.ifa_flags)
            guard let addr = ifa.pointee.ifa_addr, addr.pointee.sa_family == UInt8(AF_INET),
                  flags & IFF_UP != 0, flags & IFF_LOOPBACK == 0 else { continue }
            var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            guard getnameinfo(addr, socklen_t(addr.pointee.sa_len), &host, socklen_t(host.count), nil, 0, NI_NUMERICHOST) == 0 else { continue }
            let name = String(cString: ifa.pointee.ifa_name)
            if found[name] == nil { found[name] = String(cString: host) }
        }
        if let ip = found["en0"] ?? found["pdp_ip0"] { return ip }
        return found.sorted { $0.key < $1.key }.first?.value ?? "0.0.0.0"
    }

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        switch method {
        case "getState":
            start()
            queue.async {
                if let p = self.path { reply(Self.state(p), nil) } else { self.waiting.append(reply) }
            }
        case "getIpAddress":
            DispatchQueue.global(qos: .userInitiated).async { reply(Self.ipAddress(), nil) }
        case "startObserving":
            start()
            queue.async {
                self.observer = ctx
                if let p = self.path { ctx.emit("Network.state", Self.state(p)) }
            }
            reply(nil, nil)
        case "stopObserving":
            queue.async { self.observer = nil }
            reply(nil, nil)
        default:
            reply(nil, "Network has no method '\(method)'")
        }
    }
}
