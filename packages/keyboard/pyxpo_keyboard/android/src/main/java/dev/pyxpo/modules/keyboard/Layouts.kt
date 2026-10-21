package dev.pyxpo.modules.keyboard

/** Special key codes. Text keys have code 0 and type [Key.text]. */
object Codes {
    const val SHIFT = -1
    const val DELETE = -2
    const val ENTER = -3
    const val SYMBOLS = -4      // ?123: first symbol page
    const val LETTERS = -5      // ABC
    const val MORE = -6         // =\<: second symbol page
    const val SPACE = -7
    const val EMOJI = -8
    const val GLOBE = -9        // next input method
    const val SPACER = -10      // empty room, not a key
}

/** One key. `width` is in key units (a letter key is 1); `alt` is typed on a long press. */
class Key(val label: String, val text: String = label, val code: Int = 0, val width: Float = 1f, val alt: String? = null,
          /** A text key drawn in the darker special-key color, like the punctuation beside the space bar. */
          val side: Boolean = false) {
    val special get() = code != 0 && code != Codes.SPACE
    // set by the view's layout pass, in px
    var x = 0f
    var y = 0f
    var w = 0f
    var h = 0f
}

/** Which page the keys show. */
enum class Page { LETTERS, SYMBOLS, MORE, NUMBERS, PHONE }

/** What a text field holds: email and web address fields get "@" or "/" next to the space bar. */
enum class Field { TEXT, EMAIL, URL }

object Layouts {
    private fun chars(s: String, alts: String? = null) = s.mapIndexed { i, c -> Key(c.toString(), alt = alts?.getOrNull(i)?.toString()) }

    /**
     * The bottom row of the text pages, iOS style: `123 ☺ 🌐 space return` (two spaces type ". "). `globe` adds the
     * switch-keyboard key the system asks for; email and web address fields get "@" or "/" beside the space bar.
     */
    private fun bottom(toggle: Key, globe: Boolean, field: Field): List<Key> {
        val side = when (field) { Field.EMAIL -> Key("@", side = true); Field.URL -> Key("/", side = true); Field.TEXT -> null }
        val small = if (globe) 1.25f else 1.5f
        val space = 10f - 2 * small - (if (globe) small else 0f) - 2f - (if (side != null) 1f else 0f)
        return listOfNotNull(
            Key(toggle.label, toggle.text, toggle.code, small),
            Key("", code = Codes.EMOJI, width = small),
            if (globe) Key("", code = Codes.GLOBE, width = small) else null,
            Key("", " ", Codes.SPACE, space),
            side,
            Key("", code = Codes.ENTER, width = 2f),
        )
    }

    fun rows(page: Page, globe: Boolean, numberRow: Boolean, field: Field = Field.TEXT): List<List<Key>> = when (page) {
        Page.LETTERS -> listOfNotNull(
            if (numberRow) chars("1234567890") else null,
            chars("qwertyuiop", if (numberRow) null else "1234567890"),
            listOf(Key("", code = Codes.SPACER, width = 0.5f)) + chars("asdfghjkl", "@#₹_&-+()") +
                Key("", code = Codes.SPACER, width = 0.5f),
            listOf(Key("", code = Codes.SHIFT, width = 1.5f)) + chars("zxcvbnm", "*\"':;!?") +
                Key("", code = Codes.DELETE, width = 1.5f),
            bottom(Key("123", code = Codes.SYMBOLS, width = 1.5f), globe, field),
        )
        Page.SYMBOLS -> listOf(
            chars("1234567890"),
            chars("@#₹_&-+()/", "  $£€    "),
            listOf(Key("=\\<", code = Codes.MORE, width = 1.5f)) + chars("*\"':;!?") +
                Key("", code = Codes.DELETE, width = 1.5f),
            bottom(Key("ABC", code = Codes.LETTERS, width = 1.5f), globe, field),
        )
        Page.MORE -> listOf(
            chars("~`|•√π÷×¶∆"),
            chars("£€$¢^°={}\\"),
            listOf(Key("?123", code = Codes.SYMBOLS, width = 1.5f)) + chars("%©®™✓[]") +
                Key("", code = Codes.DELETE, width = 1.5f),
            bottom(Key("ABC", code = Codes.LETTERS, width = 1.5f), globe, field),
        )
        Page.NUMBERS, Page.PHONE -> listOf(
            chars("123-"),
            chars("456") + Key(if (page == Page.PHONE) "+" else "/"),
            chars("789") + Key("", code = Codes.DELETE),
            (if (page == Page.PHONE) chars("*0#") else chars(",0.")) + Key("", code = Codes.ENTER),
        ).map(::wide)
    }

    /** A pad row spread over the full width, like a phone dialer: four keys of 2.5 units each. */
    private fun wide(row: List<Key>) = row.map { Key(it.label, it.text, it.code, 2.5f, it.alt, it.side) }

    /** Common emoji for the emoji panel, one grapheme each (split with a BreakIterator). */
    const val EMOJI = "😀😃😄😁😆😅🤣😂🙂😉😊😇🥰😍🤩😘😋😛😜🤪🤗🤭🤫🤔🤐😐😑😶😏😒🙄😬😌😔😪😴😷🤒🤕🤢🥵🥶🥴😵🤯🥳😎🤓🧐😕😟🙁😮😯😲😳🥺😦😧😨😰😥😢😭😱😖😣😞😓😩😫🥱😤😡😠🤬" +
        "👍👎👌✌️🤞🤟🤘🤙👈👉👆👇☝️✋🤚🖐️🖖👋🤝🙏👏🙌👐🤲💪✍️💅🤳" +
        "❤️🧡💛💚💙💜🖤🤍🤎💔❣️💕💞💓💗💖💘💝💯💢💥💫💦💨🔥✨⭐🌟🎉🎊🎁🎂🎈" +
        "☕🍵🍕🍔🍟🌭🍿🥗🍛🍚🍜🍎🍌🍉🍇🍓🥭🍫🍩🍪🍺🍻🥂" +
        "⚽🏏🏀🎮🎧🎵🎶📱💻⌚📷📞📧📅📌✅❌⚠️❓❗➡️⬅️⬆️⬇️🔁🕐🚗✈️🏠🌍☀️🌙🌧️⛄🌈🐶🐱🦁🐯🐒🦋🌸🌹🌻🍀"
}
