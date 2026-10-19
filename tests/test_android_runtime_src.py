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
