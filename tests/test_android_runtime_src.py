"""Android runtime fixes that only show on a device, pinned in the Kotlin source so they do not come undone."""
from pyxpo.build import android as droid

RUNTIME = droid.TEMPLATE / "gen" / "runtime" / "java" / "dev" / "pyxpo" / "runtime"


def test_password_field_stays_masked_in_the_app_font():
    kt = (RUNTIME / "OpApplier.kt").read_text()
    # setSingleLine after the input type swapped the password mask for a plain single-line transform
    single, itype = kt.index("e.setSingleLine(!multi)"), kt.index("e.inputType = t")
    assert single < itype
    # a password input type switches the font to monospace: the field's own font comes back
    assert kt.index("val face = e.typeface") < itype < kt.index("e.typeface = face")
    assert "e.transformationMethod = android.text.method.PasswordTransformationMethod.getInstance()" in kt


def test_switch_thumb_follows_the_track_colour():
    kt = (RUNTIME / "PxControls.kt").read_text()
    assert 'color(c, "thumb_on") ?: color(c, "track_on")' in kt


def test_scroll_view_reveals_the_focused_field_when_the_keyboard_shrinks_it():
    kt = (RUNTIME / "PxViews.kt").read_text()
    scroll = kt[kt.index("class PxScroll("):]
    assert "override fun onSizeChanged" in scroll and "if (h < oldh)" in scroll
    assert "computeScrollDeltaToGetChildRectOnScreen" in scroll


def test_a_pushed_screen_takes_the_keyboard_away_from_the_screen_it_covers():
    kt = (RUNTIME / "OpApplier.kt").read_text()
    insert = kt[kt.index("private fun insert("):kt.index("private fun remove(")]
    # a field still focused on the covered screen kept the keyboard open over the new one and swallowed taps
    assert "g.pushed(v)" in insert and "g.hasFocus() && !v.hasFocus()) dropFocus(g)" in insert
    drop = kt[kt.index("private fun dropFocus("):]
    assert "hideSoftInputFromWindow" in drop[:400] and "views[1]?.requestFocus()" in drop[:400]
    delete = kt[kt.index("private fun delete("):]
    assert "v.hasFocus()) dropFocus(v)" in delete[:300]
    # a removed field (a whole form swapped out) took the keyboard with it on iOS only: here it stayed up
    remove = kt[kt.index("private fun remove("):]
    assert "v.hasFocus()) dropFocus(v)" in remove[:400]


def test_edge_to_edge_root_ends_above_the_keyboard():
    kt = (RUNTIME / "MainActivity.kt").read_text()
    # edge-to-edge windows are not resized for adjustResize: the root pads itself by the keyboard height
    assert "SOFT_INPUT_ADJUST_RESIZE" in kt and "v.setPadding(0, 0, 0, kb)" in kt
    assert "if (kb > 0) b = 0" in kt


def test_a_service_can_run_python_without_an_activity():
    api = (droid.TEMPLATE / "gen/module-api/src/main/java/dev/pyxpo/moduleapi/PxModule.kt").read_text()
    assert "object PxProcess" in api and '"dev.pyxpo.runtime.PyxpoRuntime"' in api and '"startHeadless"' in api
    assert "val context: Context get() = activity" in api and "val hasActivity: Boolean get() = true" in api
    rt = (RUNTIME / "PyxpoRuntime.kt").read_text()
    assert "@JvmStatic\n        fun startHeadless(context: Context)" in rt  # the name PxProcess looks up
    assert "PxProcess.sink = " in rt and "PxModuleHost(ctx, null)" in rt
    # no activity: call ops go to the headless host, and the first activity after a headless start remounts
    assert "if (a != null) a.apply(json) else applyHeadless(json)" in rt
    attach = rt[rt.index("fun attach("):rt.index("fun detach(")]
    assert "if (!started) return" in attach and "old == null" not in attach
    assert "runtime?.detach(it)" in (RUNTIME / "MainActivity.kt").read_text()
    host = (RUNTIME / "PxModuleHost.kt").read_text()
    assert "private val act: Activity?" in host and "context.checkSelfPermission" in host


def test_text_input_has_no_theme_underline():
    kt = (RUNTIME / "OpApplier.kt").read_text()
    # the theme's EditText background drew an accent underline inside every styled field
    assert '"TextInput" -> EditText(ctx).also { it.background = null }' in kt


def test_image_decodes_at_view_size_not_full_resolution():
    img = (RUNTIME / "Images.kt").read_text()
    # each target size gets its own cache entry, subsampled so cover still fills the view
    assert 'val key = if (tw > 0 && th > 0) "$uri@${tw}x$th" else uri' in img
    assert "while (w / (s * 2) >= tw && h / (s * 2) >= th) s *= 2" in img
    kt = (RUNTIME / "OpApplier.kt").read_text()
    # a grid cell's Image (flex: 1 in a sized Pressable) is measured during layout but still has a full frame: it
    # decodes at the frame size. Only a frame that is 0 on a side (sized by the bitmap) gets the full image.
    assert "val sized = f != null && f[2] >= 1f && f[3] >= 1f" in kt
    assert "measuredImages" not in kt
    # many cells showing one photo share one decode instead of each decoding it while the cache is cold
    assert "waiting[key]?.let { it.add(done); return }" in img
    assert "for (cb in waiting.remove(key) ?: emptyList())" in img


def test_text_defaults_to_primary_text_colour():
    kt = (RUNTIME / "OpApplier.kt").read_text()
    assert "android.R.attr.textColorPrimary" in kt
    assert '"Text" -> TextView(ctx).also { it.includeFontPadding = false; primaryText?.let(it::setTextColor) }' in kt


def test_release_build_shrinks_with_r8_and_keeps_what_c_calls_by_name():
    from pyxpo.build import android_config
    rules = "\n".join(android_config.KEEP_RULES)
    jni = (droid.TEMPLATE / "gen/cpp/pyxpo_jni.c").read_text() + (droid.TEMPLATE / "gen/cpp/pyxpo_layout_jni.c").read_text()
    assert '"onOps"' in jni and "void onOps(java.lang.String)" in rules
    assert '"measure", "(IFIFI)J"' in jni and "long measure(int, float, int, float, int)" in rules
    assert "native <methods>" in rules and "startHeadless(android.content.Context)" in rules
