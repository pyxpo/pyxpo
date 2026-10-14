#ifndef PYXPO_UTF_H
#define PYXPO_UTF_H

#include <stddef.h>
#include <stdint.h>

/* Strict UTF-16 <-> UTF-8 conversion. JNI's *StringUTF* functions use "modified UTF-8"
 * (non-BMP chars become CESU-8 surrogate triplets), which CPython rejects, so the JNI layer
 * goes through UTF-16 with these instead. Invalid input (lone surrogates, malformed UTF-8)
 * becomes U+FFFD. Results are malloc'd (free with free()) and NUL-terminated; NULL on OOM. */

/* units: UTF-16 code units (n of them). out_len (optional): bytes written, excluding the NUL. */
char *pyxpo_utf16_to_utf8(const uint16_t *units, size_t n, size_t *out_len);

/* s: NUL-terminated UTF-8. out_len (optional): UTF-16 units written, excluding the terminating 0. */
uint16_t *pyxpo_utf8_to_utf16(const char *s, size_t *out_len);

#endif
