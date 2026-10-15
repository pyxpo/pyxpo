package dev.pyxpo.modules.securestore

import android.app.Activity
import android.content.Context
import android.hardware.biometrics.BiometricManager
import android.hardware.biometrics.BiometricPrompt
import android.os.Build
import android.os.CancellationSignal
import android.os.Handler
import android.os.Looper
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyPermanentlyInvalidatedException
import android.security.keystore.KeyProperties
import android.util.Base64
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import org.json.JSONObject
import java.security.KeyStore
import java.util.concurrent.Executors
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * expo-secure-store on Android. Each value is encrypted with an AES-256-GCM key that never leaves the
 * Android Keystore; the ciphertext is kept in SharedPreferences "SecureStore" under `<service>-<key>`.
 * Items saved with requireAuthentication use a second key that needs a biometric prompt for every use.
 */
class SecureStoreModule : PxModule() {
    override val name = "SecureStore"

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        val activity = ctx.activity
        if (method == "canUseBiometric") { reply(canUseBiometric(activity), null); return }
        val key = args.optString(0)
        if (key.isEmpty()) { reply(null, "SecureStore.$method needs a key"); return }
        val opts = args.optJSONObject(args.length() - 1) ?: JSONObject()
        executor.execute {
            try {
                when (method) {
                    "get" -> get(activity, key, opts, reply)
                    "set" -> set(activity, key, args.optString(1), opts, reply)
                    "delete" -> { prefs(activity).edit().remove(storageKey(key, opts)).commit(); reply(null, null) }
                    else -> reply(null, "unknown native call SecureStore.$method")
                }
            } catch (e: Throwable) {
                reply(null, e.message ?: e.toString())
            }
        }
    }

    private fun prefs(c: Context) = c.applicationContext.getSharedPreferences("SecureStore", Context.MODE_PRIVATE)

    private fun service(opts: JSONObject) = opts.optString("keychainService").ifEmpty { "app" }

    private fun storageKey(key: String, opts: JSONObject) = "${service(opts)}-$key"

    private fun alias(opts: JSONObject, auth: Boolean) = "$TRANSFORMATION:${service(opts)}" + if (auth) ":auth" else ""

    // keys

    private fun keyStore() = KeyStore.getInstance(KEYSTORE).apply { load(null) }

    private fun secretKey(alias: String, auth: Boolean, create: Boolean): SecretKey? {
        (keyStore().getKey(alias, null) as? SecretKey)?.let { return it }
        if (!create) return null
        val spec = KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setKeySize(256)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
        if (auth) {
            spec.setUserAuthenticationRequired(true)
            spec.setInvalidatedByBiometricEnrollment(true)
            if (Build.VERSION.SDK_INT >= 30) spec.setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG)
        }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE).run { init(spec.build()); generateKey() }
    }

    // set / get

    private fun set(a: Activity, key: String, value: String, opts: JSONObject, reply: PxReply) {
        val auth = opts.optBoolean("requireAuthentication", false)
        if (auth) requireBiometric(a)
        val alias = alias(opts, auth)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        try {
            cipher.init(Cipher.ENCRYPT_MODE, secretKey(alias, auth, true))
        } catch (e: KeyPermanentlyInvalidatedException) {
            // New fingerprints or face were enrolled: the old key is gone for good. Start a fresh one.
            keyStore().deleteEntry(alias)
            cipher.init(Cipher.ENCRYPT_MODE, secretKey(alias, auth, true))
        }
        withAuth(a, cipher, auth, opts, reply) { c ->
            val record = JSONObject()
                .put("ct", Base64.encodeToString(c.doFinal(value.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP))
                .put("iv", Base64.encodeToString(c.iv, Base64.NO_WRAP))
                .put("tlen", TAG_BITS)
                .put("scheme", "aes")
                .put("requireAuthentication", auth)
            if (!prefs(a).edit().putString(storageKey(key, opts), record.toString()).commit()) throw IllegalStateException("could not save the value")
            null
        }
    }

    private fun get(a: Activity, key: String, opts: JSONObject, reply: PxReply) {
        val raw = prefs(a).getString(storageKey(key, opts), null) ?: run { reply(null, null); return }
        val record = JSONObject(raw)
        val auth = record.optBoolean("requireAuthentication", false)
        val alias = alias(opts, auth)
        val secret = secretKey(alias, auth, false)
        if (secret == null) {
            // The key was removed (app data restored to another device, or keys reset): the value cannot be read.
            prefs(a).edit().remove(storageKey(key, opts)).commit()
            reply(null, null)
            return
        }
        val cipher = Cipher.getInstance(TRANSFORMATION)
        try {
            cipher.init(Cipher.DECRYPT_MODE, secret, GCMParameterSpec(record.optInt("tlen", TAG_BITS), Base64.decode(record.getString("iv"), Base64.NO_WRAP)))
        } catch (e: KeyPermanentlyInvalidatedException) {
            keyStore().deleteEntry(alias)
            prefs(a).edit().remove(storageKey(key, opts)).commit()
            reply(null, "the biometric key was invalidated because biometrics changed; the item was deleted")
            return
        }
        withAuth(a, cipher, auth, opts, reply) { c ->
            String(c.doFinal(Base64.decode(record.getString("ct"), Base64.NO_WRAP)), Charsets.UTF_8)
        }
    }

    // biometrics

    private fun canUseBiometric(a: Activity): Boolean = when {
        Build.VERSION.SDK_INT >= 30 -> a.getSystemService(BiometricManager::class.java)
            ?.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) == BiometricManager.BIOMETRIC_SUCCESS
        Build.VERSION.SDK_INT == 29 -> @Suppress("DEPRECATION")
            (a.getSystemService(BiometricManager::class.java)?.canAuthenticate() == BiometricManager.BIOMETRIC_SUCCESS)
        else -> false
    }

    private fun requireBiometric(a: Activity) {
        if (Build.VERSION.SDK_INT < 29) throw IllegalStateException("requireAuthentication needs Android 10 or newer")
        if (!canUseBiometric(a)) throw IllegalStateException("no biometrics are enrolled on this device")
    }

    /** Runs `use` with `cipher` directly, or after a biometric prompt unlocks it. Replies with its result. */
    private fun withAuth(a: Activity, cipher: Cipher, auth: Boolean, opts: JSONObject, reply: PxReply, use: (Cipher) -> Any?) {
        if (!auth) { reply(use(cipher), null); return }
        if (Build.VERSION.SDK_INT < 29) { reply(null, "requireAuthentication needs Android 10 or newer"); return }
        main.post {
            val prompt = BiometricPrompt.Builder(a)
                .setTitle(opts.optString("authenticationPrompt").ifEmpty { "Authenticate to continue" })
                .setNegativeButton(a.getString(android.R.string.cancel), executor) { _, _ -> reply(null, "User canceled the operation") }
                .build()
            prompt.authenticate(BiometricPrompt.CryptoObject(cipher), CancellationSignal(), executor,
                object : BiometricPrompt.AuthenticationCallback() {
                    override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                        try { reply(use(result.cryptoObject?.cipher ?: cipher), null) }
                        catch (e: Throwable) { reply(null, e.message ?: e.toString()) }
                    }
                    override fun onAuthenticationError(code: Int, msg: CharSequence) {
                        reply(null, if (code == BiometricPrompt.BIOMETRIC_ERROR_USER_CANCELED || code == BiometricPrompt.BIOMETRIC_ERROR_CANCELED)
                            "User canceled the operation" else "Authentication failed: $msg")
                    }
                })
        }
    }

    companion object {
        private const val KEYSTORE = "AndroidKeyStore"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val TAG_BITS = 128
        private val main = Handler(Looper.getMainLooper())
        private val executor = Executors.newSingleThreadExecutor { r -> Thread(r, "pyxpo-securestore") }
    }
}
