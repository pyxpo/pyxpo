package dev.pyxpo.runtime

import android.content.Context
import android.view.View
import android.view.ViewGroup
import kotlin.math.max
import kotlin.math.roundToInt

/** Flexbox subset: flex_direction, flex, gap, padding, margin, align_items, justify_content, width, height. */
class PyxpoLayout(ctx: Context) : ViewGroup(ctx) {
    var row = false
    var gap = 0
    var alignItems = "stretch"        // stretch | start | center | end
    var justify = "start"             // start | center | end | space_between
    var fixedW = -1                   // px, -1 = auto
    var fixedH = -1
    var flexGrow = 0f
    var margin = 0

    private fun lp(v: View): PyxpoLayout = (v as? PyxpoLayout) ?: this

    private fun grow(v: View) = (v as? PyxpoLayout)?.flexGrow ?: (v.tag as? Extra)?.flex ?: 0f
    private fun marg(v: View) = (v as? PyxpoLayout)?.margin ?: (v.tag as? Extra)?.margin ?: 0

    override fun onMeasure(wSpec: Int, hSpec: Int) {
        val pl = paddingLeft; val pt = paddingTop
        val availW = if (fixedW >= 0) fixedW else MeasureSpec.getSize(wSpec)
        val availH = if (fixedH >= 0) fixedH else MeasureSpec.getSize(hSpec)
        val wMode = if (fixedW >= 0) MeasureSpec.EXACTLY else MeasureSpec.getMode(wSpec)
        val hMode = if (fixedH >= 0) MeasureSpec.EXACTLY else MeasureSpec.getMode(hSpec)
        val innerW = availW - pl - paddingRight
        val innerH = availH - pt - paddingBottom
        val kids = (0 until childCount).map { getChildAt(it) }.filter { it.visibility != GONE }
        val mainAvail = if (row) innerW else innerH
        val mainBounded = (if (row) wMode else hMode) != MeasureSpec.UNSPECIFIED
        val crossAvail = if (row) innerH else innerW
        val crossExact = (if (row) hMode else wMode) == MeasureSpec.EXACTLY

        var used = gap * max(0, kids.size - 1)
        var totalGrow = 0f
        var cross = 0
        // pass 1: non-flex children
        for (k in kids) {
            val m = marg(k) * 2
            if (grow(k) > 0f && mainBounded) { totalGrow += grow(k); used += m; continue }
            val cSpec = crossSpec(k, crossAvail - m, crossExact)
            val mSpec = MeasureSpec.makeMeasureSpec(max(0, mainAvail - used - m), MeasureSpec.AT_MOST)
            if (row) k.measure(mSpec, cSpec) else k.measure(cSpec, mSpec)
            used += (if (row) k.measuredWidth else k.measuredHeight) + m
            cross = max(cross, (if (row) k.measuredHeight else k.measuredWidth) + m)
        }
        // pass 2: flex children share the remainder
        val remaining = max(0, mainAvail - used)
        for (k in kids) {
            if (!(grow(k) > 0f && mainBounded)) continue
            val share = (remaining * grow(k) / totalGrow).roundToInt()
            val m = marg(k) * 2
            val mSpec = MeasureSpec.makeMeasureSpec(max(0, share), MeasureSpec.EXACTLY)
            val cSpec = crossSpec(k, crossAvail - m, crossExact)
            if (row) k.measure(mSpec, cSpec) else k.measure(cSpec, mSpec)
            used += share
            cross = max(cross, (if (row) k.measuredHeight else k.measuredWidth) + m)
        }
        val mainSize = used
        val w = if (wMode == MeasureSpec.EXACTLY) availW
                else (if (row) mainSize else cross) + pl + paddingRight
        val h = if (hMode == MeasureSpec.EXACTLY) availH
                else (if (row) cross else mainSize) + pt + paddingBottom
        setMeasuredDimension(
            if (wMode == MeasureSpec.AT_MOST) minOf(w, availW) else w,
            if (hMode == MeasureSpec.AT_MOST) minOf(h, availH) else h,
        )
    }

    private fun crossSpec(k: View, avail: Int, exact: Boolean): Int {
        val stretch = alignItems == "stretch" && exact
        val k2 = k as? PyxpoLayout
        val own = if (row) k2?.fixedH ?: -1 else k2?.fixedW ?: -1
        return when {
            own >= 0 -> MeasureSpec.makeMeasureSpec(own, MeasureSpec.EXACTLY)
            stretch -> MeasureSpec.makeMeasureSpec(max(0, avail), MeasureSpec.EXACTLY)
            else -> MeasureSpec.makeMeasureSpec(max(0, avail), MeasureSpec.AT_MOST)
        }
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        val kids = (0 until childCount).map { getChildAt(it) }.filter { it.visibility != GONE }
        val innerW = r - l - paddingLeft - paddingRight
        val innerH = b - t - paddingTop - paddingBottom
        val mainSize = if (row) innerW else innerH
        val crossSize = if (row) innerH else innerW
        val used = kids.sumOf { (if (row) it.measuredWidth else it.measuredHeight) + marg(it) * 2 } +
            gap * max(0, kids.size - 1)
        var extra = max(0, mainSize - used)
        var pos = when (justify) { "center" -> extra / 2; "end" -> extra; else -> 0 }
        val between = if (justify == "space_between" && kids.size > 1) extra / (kids.size - 1) else 0
        for (k in kids) {
            val m = marg(k)
            val kMain = if (row) k.measuredWidth else k.measuredHeight
            val kCross = if (row) k.measuredHeight else k.measuredWidth
            val cOff = when (alignItems) { "center" -> (crossSize - kCross) / 2; "end" -> crossSize - kCross - m; else -> m }
            val x = paddingLeft + if (row) pos + m else cOff
            val y = paddingTop + if (row) cOff else pos + m
            k.layout(x, y, x + k.measuredWidth, y + k.measuredHeight)
            pos += kMain + m * 2 + gap + between
        }
    }

    /** Flex data for non-PyxpoLayout children (stored in View.tag). */
    class Extra(val flex: Float, val margin: Int)
}
