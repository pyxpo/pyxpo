#include "pyxpo_utf.h"

#include <stdlib.h>
#include <string.h>

#define REPLACEMENT 0xFFFDu

char *pyxpo_utf16_to_utf8(const uint16_t *units, size_t n, size_t *out_len) {
    /* Worst case 3 bytes per unit (a surrogate pair is 2 units -> 4 bytes). */
    if (n > (SIZE_MAX - 1) / 3) return NULL;
    char *out = malloc(n * 3 + 1);
    if (out == NULL) return NULL;
    size_t o = 0;
    for (size_t i = 0; i < n; i++) {
        uint32_t c = units[i];
        if (c >= 0xD800 && c <= 0xDBFF && i + 1 < n && units[i + 1] >= 0xDC00 && units[i + 1] <= 0xDFFF) {
            c = 0x10000 + ((c - 0xD800) << 10) + (units[i + 1] - 0xDC00);
            i++;
        } else if (c >= 0xD800 && c <= 0xDFFF) {
            c = REPLACEMENT; /* lone surrogate */
        }
        if (c < 0x80) {
            out[o++] = (char)c;
        } else if (c < 0x800) {
            out[o++] = (char)(0xC0 | (c >> 6));
            out[o++] = (char)(0x80 | (c & 0x3F));
        } else if (c < 0x10000) {
            out[o++] = (char)(0xE0 | (c >> 12));
            out[o++] = (char)(0x80 | ((c >> 6) & 0x3F));
            out[o++] = (char)(0x80 | (c & 0x3F));
        } else {
            out[o++] = (char)(0xF0 | (c >> 18));
            out[o++] = (char)(0x80 | ((c >> 12) & 0x3F));
            out[o++] = (char)(0x80 | ((c >> 6) & 0x3F));
            out[o++] = (char)(0x80 | (c & 0x3F));
        }
    }
    out[o] = '\0';
    if (out_len) *out_len = o;
    return out;
}

uint16_t *pyxpo_utf8_to_utf16(const char *s, size_t *out_len) {
    const unsigned char *p = (const unsigned char *)s;
    size_t len = strlen(s);
    /* Every UTF-16 unit consumes at least one input byte. */
    if (len > SIZE_MAX / sizeof(uint16_t) - 1) return NULL;
    uint16_t *out = malloc((len + 1) * sizeof(uint16_t));
    if (out == NULL) return NULL;
    size_t i = 0, o = 0;
    while (i < len) {
        unsigned char b = p[i];
        uint32_t c;
        size_t need;
        uint32_t min;
        if (b < 0x80) { out[o++] = b; i++; continue; }
        else if (b >= 0xC2 && b <= 0xDF) { c = b & 0x1F; need = 1; min = 0x80; }
        else if (b >= 0xE0 && b <= 0xEF) { c = b & 0x0F; need = 2; min = 0x800; }
        else if (b >= 0xF0 && b <= 0xF4) { c = b & 0x07; need = 3; min = 0x10000; }
        else { out[o++] = REPLACEMENT; i++; continue; }
        size_t k = 1;
        for (; k <= need && i + k < len && (p[i + k] & 0xC0) == 0x80; k++) c = (c << 6) | (p[i + k] & 0x3F);
        if (k <= need || c < min || c > 0x10FFFF || (c >= 0xD800 && c <= 0xDFFF)) {
            out[o++] = REPLACEMENT; /* truncated, overlong, out of range or encoded surrogate */
            i++;
            continue;
        }
        i += need + 1;
        if (c >= 0x10000) {
            c -= 0x10000;
            out[o++] = (uint16_t)(0xD800 + (c >> 10));
            out[o++] = (uint16_t)(0xDC00 + (c & 0x3FF));
        } else {
            out[o++] = (uint16_t)c;
        }
    }
    out[o] = 0;
    if (out_len) *out_len = o;
    return out;
}
