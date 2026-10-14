package dev.pyxpo.runtime

/** Kotlin face of the shared C flexbox engine (native/common/pyxpo_layout.c). UI thread only. */
class NativeLayout(private val measurer: (Int, Float, Int, Float, Int) -> Long) {
    private var ptr: Long = 0
    private var buf = FloatArray(5 * 64)

    init {
        System.loadLibrary("pyxpo_jni")
        ptr = nCreate()
        check(ptr != 0L) { "layout engine init failed" }
    }

    /** Called from C for measured leaves. Returns float bits of width (high) and height (low). */
    @Suppress("unused")
    fun measure(id: Int, w: Float, wm: Int, h: Float, hm: Int): Long = measurer(id, w, wm, h, hm)

    fun create(id: Int) = nNodeCreate(ptr, id)
    fun delete(id: Int) = nNodeDelete(ptr, id)
    fun insert(parent: Int, child: Int, index: Int) = nInsert(ptr, parent, child, index)
    fun remove(parent: Int, child: Int) = nRemove(ptr, parent, child)
    fun setMeasured(id: Int, on: Boolean) = nSetMeasured(ptr, id, if (on) 1 else 0)
    fun markDirty(id: Int) = nMarkDirty(ptr, id)
    fun propId(name: String) = nPropId(name)
    fun setNum(id: Int, prop: Int, v: Float) = nSetNum(ptr, id, prop, v)
    fun setStr(id: Int, prop: Int, v: String) = nSetStr(ptr, id, prop, v)
    fun reset(id: Int, prop: Int) = nReset(ptr, id, prop)

    /** Lays out the tree and reports changed frames (dp, relative to the parent). */
    inline fun calc(w: Float, h: Float, onFrame: (Int, Float, Float, Float, Float) -> Unit) {
        val n = runCalc(w, h)
        val b = frames()
        for (i in 0 until n) onFrame(b[i * 5].toInt(), b[i * 5 + 1], b[i * 5 + 2], b[i * 5 + 3], b[i * 5 + 4])
    }

    @PublishedApi internal fun frames(): FloatArray = buf

    @PublishedApi internal fun runCalc(w: Float, h: Float): Int {
        var n = nCalc(ptr, w, h, buf)
        if (n < 0) {
            buf = FloatArray(5 * (-n))
            n = nChanged(ptr, buf)
        }
        return n
    }

    fun release() { nFree(ptr); ptr = 0 }

    private external fun nCreate(): Long
    private external fun nFree(p: Long)
    private external fun nNodeCreate(p: Long, id: Int): Int
    private external fun nNodeDelete(p: Long, id: Int): Int
    private external fun nInsert(p: Long, parent: Int, child: Int, index: Int): Int
    private external fun nRemove(p: Long, parent: Int, child: Int): Int
    private external fun nSetMeasured(p: Long, id: Int, f: Int): Int
    private external fun nMarkDirty(p: Long, id: Int): Int
    private external fun nSetNum(p: Long, id: Int, prop: Int, v: Float): Int
    private external fun nSetStr(p: Long, id: Int, prop: Int, v: String): Int
    private external fun nReset(p: Long, id: Int, prop: Int): Int
    private external fun nPropId(name: String): Int
    private external fun nCalc(p: Long, w: Float, h: Float, out: FloatArray): Int
    private external fun nChanged(p: Long, out: FloatArray): Int
}
