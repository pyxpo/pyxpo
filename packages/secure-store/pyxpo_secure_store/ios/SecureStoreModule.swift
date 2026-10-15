import Foundation
import LocalAuthentication
import Security

/// expo-secure-store on iOS: generic-password Keychain items.
/// Service `<keychainService>:no-auth` holds plain items, `<keychainService>:auth` the ones that need
/// biometrics. A key lives in only one of the two: setting it removes the other.
final class SecureStoreModule: PxModule {
    static let moduleName = "SecureStore"

    /// Keychain calls can block (an authentication prompt waits for the user), so they run here, one at a time.
    private let queue = DispatchQueue(label: "dev.pyxpo.securestore")

    required init() {}

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        if method == "canUseBiometric" {
            let ctx = LAContext()
            var err: NSError?
            reply(ctx.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &err), nil)
            return
        }
        guard let key = args.first as? String else { reply(nil, "SecureStore.\(method) needs a key"); return }
        let opts = (args.last as? [String: Any]) ?? [:]
        let value = args.count > 2 ? args[1] as? String : nil
        queue.async {
            switch method {
            case "get": self.get(key, opts, reply)
            case "set":
                guard let value = value else { reply(nil, "SecureStore.set needs a string value"); return }
                self.set(key, value, opts, reply)
            case "delete":
                self.delete(key, opts)
                reply(nil, nil)
            default: reply(nil, "unknown native call SecureStore.\(method)")
            }
        }
    }

    // MARK: Keychain

    private func service(_ opts: [String: Any], auth: Bool) -> String {
        let s = (opts["keychainService"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "app"
        return s + (auth ? ":auth" : ":no-auth")
    }

    private func base(_ key: String, _ opts: [String: Any], auth: Bool) -> [String: Any] {
        let account = Data(key.utf8)
        var q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service(opts, auth: auth),
            kSecAttrGeneric as String: account,
            kSecAttrAccount as String: account,
        ]
        if let group = opts["accessGroup"] as? String, !group.isEmpty { q[kSecAttrAccessGroup as String] = group }
        return q
    }

    private func accessible(_ opts: [String: Any]) -> CFString {
        switch (opts["keychainAccessible"] as? Int) ?? 5 {
        case 0, 2: return kSecAttrAccessibleAfterFirstUnlock
        case 1, 4: return kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        case 3: return kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly
        case 6: return kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        default: return kSecAttrAccessibleWhenUnlocked
        }
    }

    private func get(_ key: String, _ opts: [String: Any], _ reply: PxReply) {
        let wantAuth = (opts["requireAuthentication"] as? Bool) ?? false
        // Look where the caller expects first, then in the other service.
        for auth in [wantAuth, !wantAuth] {
            var q = base(key, opts, auth: auth)
            q[kSecMatchLimit as String] = kSecMatchLimitOne
            q[kSecReturnData as String] = true
            if auth {
                // Reading attributes needs no authentication, so this finds out whether the item exists first.
                var probe = base(key, opts, auth: true)
                probe[kSecMatchLimit as String] = kSecMatchLimitOne
                probe[kSecReturnAttributes as String] = true
                if SecItemCopyMatching(probe as CFDictionary, nil) == errSecItemNotFound { continue }
                // Show the prompt ourselves, then hand the unlocked context to the Keychain so it does not ask again.
                // (The simulator Keychain does not enforce biometric access control, so without this it never asks.)
                let la = LAContext()
                la.localizedFallbackTitle = ""
                let prompt = (opts["authenticationPrompt"] as? String) ?? ""
                if let error = evaluate(la, prompt.isEmpty ? "Authenticate to continue" : prompt) {
                    reply(nil, error)
                    return
                }
                q[kSecUseAuthenticationContext as String] = la
            }
            var out: AnyObject?
            let status = SecItemCopyMatching(q as CFDictionary, &out)
            switch status {
            case errSecSuccess:
                guard let data = out as? Data, let s = String(data: data, encoding: .utf8) else {
                    reply(nil, "stored value is not text")
                    return
                }
                reply(s, nil)
                return
            case errSecItemNotFound: continue
            default:
                reply(nil, message(status))
                return
            }
        }
        reply(nil, nil)
    }

    private func set(_ key: String, _ value: String, _ opts: [String: Any], _ reply: PxReply) {
        let auth = (opts["requireAuthentication"] as? Bool) ?? false
        var q = base(key, opts, auth: auth)
        q[kSecValueData as String] = Data(value.utf8)
        if auth {
            // Same rule as Android: an item that needs biometrics cannot be read back when none are enrolled.
            var laErr: NSError?
            guard LAContext().canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &laErr) else {
                reply(nil, "no biometrics are enrolled on this device")
                return
            }
            var err: Unmanaged<CFError>?
            guard let access = SecAccessControlCreateWithFlags(nil, accessible(opts), .biometryCurrentSet, &err) else {
                reply(nil, "cannot create access control: \(err?.takeRetainedValue().localizedDescription ?? "unknown error")")
                return
            }
            q[kSecAttrAccessControl as String] = access
        } else {
            q[kSecAttrAccessible as String] = accessible(opts)
        }
        // Replace: drop the key from both services, then add.
        delete(key, opts)
        let status = SecItemAdd(q as CFDictionary, nil)
        reply(nil, status == errSecSuccess ? nil : message(status))
    }

    /// Shows the biometric prompt and waits for it (this runs on `queue`, never the main thread). nil on success.
    private func evaluate(_ la: LAContext, _ reason: String) -> String? {
        let done = DispatchSemaphore(value: 0)
        var failure: Error?
        la.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: reason) { ok, error in
            if !ok { failure = error ?? LAError(.authenticationFailed) }
            done.signal()
        }
        done.wait()
        guard let error = failure else { return nil }
        switch (error as? LAError)?.code {
        case .userCancel?, .appCancel?, .systemCancel?, .userFallback?: return "User canceled the operation"
        default: return "Authentication failed: \(error.localizedDescription)"
        }
    }

    private func delete(_ key: String, _ opts: [String: Any]) {
        SecItemDelete(base(key, opts, auth: false) as CFDictionary)
        SecItemDelete(base(key, opts, auth: true) as CFDictionary)
    }

    private func message(_ status: OSStatus) -> String {
        switch status {
        case errSecUserCanceled: return "User canceled the operation"
        case errSecAuthFailed: return "Authentication failed"
        case errSecInteractionNotAllowed: return "Keychain is not available while the device is locked"
        case errSecMissingEntitlement: return "Keychain access is missing an entitlement (check accessGroup)"
        default:
            let text = SecCopyErrorMessageString(status, nil) as String? ?? "unknown error"
            return "Keychain error \(status): \(text)"
        }
    }
}
