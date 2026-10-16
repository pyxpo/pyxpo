package dev.pyxpo.modules.haptics

import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.view.HapticFeedbackConstants
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray

/**
 * expo-haptics on Android. Impact, notification and selection feedback play short vibration patterns
 * (timings in ms, amplitudes 0-255; devices without amplitude control use the default strength).
 * `performAndroid` uses the system haptic constants on the activity's window.
 */
class HapticsModule : PxModule() {
    override val name = "Haptics"

    private class Pattern(val timings: LongArray, val amplitudes: IntArray)

    private val impacts = mapOf(
        "light" to Pattern(longArrayOf(0, 20), intArrayOf(0, 60)),
        "medium" to Pattern(longArrayOf(0, 30), intArrayOf(0, 120)),
        "heavy" to Pattern(longArrayOf(0, 45), intArrayOf(0, 255)),
        "rigid" to Pattern(longArrayOf(0, 15), intArrayOf(0, 200)),
        "soft" to Pattern(longArrayOf(0, 40), intArrayOf(0, 50)),
    )
    private val notifications = mapOf(
        "success" to Pattern(longArrayOf(0, 40, 100, 40), intArrayOf(0, 60, 0, 120)),
        "warning" to Pattern(longArrayOf(0, 40, 120, 60), intArrayOf(0, 120, 0, 60)),
        "error" to Pattern(longArrayOf(0, 60, 100, 40, 80, 50), intArrayOf(0, 150, 0, 120, 0, 180)),
    )
    private val selection = Pattern(longArrayOf(0, 12), intArrayOf(0, 90))

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        val value = args.optString(0)
        when (method) {
            "impact" -> play(ctx.activity, impacts[value] ?: return reply(null, "unknown ImpactFeedbackStyle '$value'"))
            "notification" -> play(ctx.activity, notifications[value] ?: return reply(null, "unknown NotificationFeedbackType '$value'"))
            "selection" -> play(ctx.activity, selection)
            "performAndroid" -> {
                val c = constant(value) ?: return reply(null, "unknown AndroidHaptics '$value'")
                if (c >= 0) ctx.activity.window.decorView.performHapticFeedback(c)
            }
            else -> return reply(null, "unknown native call Haptics.$method")
        }
        reply(null, null)
    }

    private fun vibrator(context: Context): Vibrator? =
        if (Build.VERSION.SDK_INT >= 31) (context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager)?.defaultVibrator
        else @Suppress("DEPRECATION") (context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator)

    private fun play(context: Context, p: Pattern) {
        val v = vibrator(context) ?: return
        if (!v.hasVibrator()) return
        if (Build.VERSION.SDK_INT >= 26) {
            val effect = if (v.hasAmplitudeControl()) VibrationEffect.createWaveform(p.timings, p.amplitudes, -1)
                         else VibrationEffect.createWaveform(p.timings, -1)
            v.vibrate(effect)
        } else {
            @Suppress("DEPRECATION") v.vibrate(p.timings, -1)
        }
    }

    /** The HapticFeedbackConstants value, a close older one on older Android, -1 for nothing, null if unknown. */
    private fun constant(type: String): Int? {
        val sdk = Build.VERSION.SDK_INT
        return when (type) {
            "confirm" -> if (sdk >= 30) HapticFeedbackConstants.CONFIRM else HapticFeedbackConstants.VIRTUAL_KEY
            "reject" -> if (sdk >= 30) HapticFeedbackConstants.REJECT else HapticFeedbackConstants.LONG_PRESS
            "gesture-start" -> if (sdk >= 30) HapticFeedbackConstants.GESTURE_START else HapticFeedbackConstants.VIRTUAL_KEY
            "gesture-end" -> if (sdk >= 30) HapticFeedbackConstants.GESTURE_END else HapticFeedbackConstants.VIRTUAL_KEY
            "toggle-on" -> if (sdk >= 34) HapticFeedbackConstants.TOGGLE_ON else HapticFeedbackConstants.VIRTUAL_KEY
            "toggle-off" -> if (sdk >= 34) HapticFeedbackConstants.TOGGLE_OFF else HapticFeedbackConstants.VIRTUAL_KEY
            "clock-tick" -> HapticFeedbackConstants.CLOCK_TICK
            "context-click" -> HapticFeedbackConstants.CONTEXT_CLICK
            "drag-start" -> if (sdk >= 34) HapticFeedbackConstants.DRAG_START else HapticFeedbackConstants.LONG_PRESS
            "keyboard-tap" -> HapticFeedbackConstants.KEYBOARD_TAP
            "keyboard-press" -> if (sdk >= 27) HapticFeedbackConstants.KEYBOARD_PRESS else HapticFeedbackConstants.KEYBOARD_TAP
            "keyboard-release" -> if (sdk >= 27) HapticFeedbackConstants.KEYBOARD_RELEASE else -1
            "long-press" -> HapticFeedbackConstants.LONG_PRESS
            "virtual-key" -> HapticFeedbackConstants.VIRTUAL_KEY
            "virtual-key-release" -> if (sdk >= 27) HapticFeedbackConstants.VIRTUAL_KEY_RELEASE else -1
            "no-haptics" -> if (sdk >= 34) HapticFeedbackConstants.NO_HAPTICS else -1
            "segment-tick" -> if (sdk >= 34) HapticFeedbackConstants.SEGMENT_TICK else HapticFeedbackConstants.CLOCK_TICK
            "segment-frequent-tick" -> if (sdk >= 34) HapticFeedbackConstants.SEGMENT_FREQUENT_TICK else HapticFeedbackConstants.CLOCK_TICK
            "text-handle-move" -> if (sdk >= 27) HapticFeedbackConstants.TEXT_HANDLE_MOVE else HapticFeedbackConstants.CLOCK_TICK
            else -> null
        }
    }
}
