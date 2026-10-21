package dev.pyxpo.modules.translate

import com.google.android.gms.tasks.Tasks
import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateLanguage
import com.google.mlkit.nl.translate.TranslateRemoteModel
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.Translator
import com.google.mlkit.nl.translate.TranslatorOptions
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class TranslateError(message: String) : Exception(message)

/**
 * Native side of `pyxpo_translate`: ML Kit on-device translation. A model downloads only on `download`; `translate`
 * refuses a pair whose models are not on the phone (ML Kit would otherwise fetch them), so text never waits on
 * the network and is never sent anywhere. Text is not logged. Works headless (an input method calls it).
 */
class TranslateModule : PxModule() {
    override val name = "Translate"

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        when (method) {
            "languages" -> background(reply) { JSONArray(TranslateLanguage.getAllLanguages().sorted()) }
            "downloaded" -> background(reply) { JSONArray(downloaded().sorted()) }
            "download" -> {
                val o = args.optJSONObject(1) ?: JSONObject()
                download(lang(args, 0), o.optBoolean("wifiOnly", false), reply)
            }
            "delete" -> background(reply) {
                val l = lang(args, 0)
                if (l == TranslateLanguage.ENGLISH) throw TranslateError("the English model is built in and cannot be deleted")
                Tasks.await(models.deleteDownloadedModel(TranslateRemoteModel.Builder(l).build()), 30, TimeUnit.SECONDS)
                null
            }
            "translate" -> background(reply) {
                val text = args.optString(0, "")
                val from = lang(args, 1)
                val to = lang(args, 2)
                if (from == to || text.isBlank()) return@background text
                val have = downloaded()
                val missing = listOf(from, to).filter { it !in have }
                if (missing.isNotEmpty()) throw TranslateError("not on the phone: ${missing.joinToString()} (download_async first)")
                Tasks.await(translator(from, to).translate(text), 60, TimeUnit.SECONDS)
            }
            "close" -> background(reply) { closeAll(); null }
            else -> reply(null, "unknown native call Translate.$method")
        }
    }

    companion object {
        private val executor = Executors.newSingleThreadExecutor { r -> Thread(r, "pyxpo-translate") }
        private val models by lazy { RemoteModelManager.getInstance() }
        // one open translator per pair: opening loads the model (about a second), so keep it for the next call
        private val open = HashMap<String, Translator>()

        private fun lang(args: JSONArray, i: Int): String {
            val tag = args.optString(i, "")
            return TranslateLanguage.fromLanguageTag(tag) ?: throw TranslateError("ML Kit cannot translate '$tag'")
        }

        /** Language codes whose models are on the phone; English is always there. */
        private fun downloaded(): Set<String> {
            val set = Tasks.await(models.getDownloadedModels(TranslateRemoteModel::class.java), 30, TimeUnit.SECONDS)
            return set.map { it.language }.toSet() + TranslateLanguage.ENGLISH
        }

        private fun translator(from: String, to: String): Translator = open.getOrPut("$from>$to") {
            Translation.getClient(TranslatorOptions.Builder().setSourceLanguage(from).setTargetLanguage(to).build())
        }

        private fun closeAll() {
            for (t in open.values) t.close()
            open.clear()
        }

        /** Downloads one language's model; the reply comes when it is on the phone (or the download failed). */
        private fun download(l: String, wifiOnly: Boolean, reply: PxReply) {
            if (l == TranslateLanguage.ENGLISH) return reply(null, null)
            val conditions = DownloadConditions.Builder().apply { if (wifiOnly) requireWifi() }.build()
            models.download(TranslateRemoteModel.Builder(l).build(), conditions)
                .addOnSuccessListener(executor) { reply(null, null) }
                .addOnFailureListener(executor) { e -> reply(null, "the $l model did not download: ${e.message ?: e}") }
        }

        private fun background(reply: PxReply, work: () -> Any?) {
            executor.execute {
                var value: Any? = null
                var message: String? = null
                try { value = work() }
                catch (e: TranslateError) { message = e.message }
                catch (e: java.util.concurrent.ExecutionException) { message = e.cause?.message ?: e.toString() }
                catch (e: java.util.concurrent.TimeoutException) { message = "ML Kit did not answer in time" }
                catch (e: Throwable) { message = e.toString() }
                reply(value, message)
            }
        }
    }
}
