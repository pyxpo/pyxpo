package dev.pyxpo.runtime

import android.content.Context
import android.view.View
import android.view.ViewGroup

/** Container whose children are positioned by [OpApplier] from the shared layout engine, never by Android. */
open class PxGroup(ctx: Context) : ViewGroup(ctx) {
    /** Forced size in px (ScrollView content). -1 = follow the measure spec. */
    var fw = -1
    var fh = -1

    init { clipChildren = false }

    override fun onMeasure(wSpec: Int, hSpec: Int) {
        setMeasuredDimension(
            if (fw >= 0) fw else View.MeasureSpec.getSize(wSpec),
            if (fh >= 0) fh else View.MeasureSpec.getSize(hSpec),
        )
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {}
}

/** Root view: reports its pixel size so the engine can lay out against the real window. */
class PxRoot(ctx: Context, private val onSize: (Int, Int) -> Unit) : PxGroup(ctx) {
    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        onSize(w, h)
    }
}
