/* pyxpo flexbox layout engine. See pyxpo_layout.h.
 *
 * Model: border-box sizing, CSS flexbox with React-Native defaults (column, align stretch, shrink 0,
 * align-content flex-start). Left-to-right only. Auto margins are not supported (treated as 0).
 */
#include "pyxpo_layout.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#define UNDEF NAN
#define DEF(x) (!isnan(x))

enum { M_EXACT = 0, M_ATMOST = 1, M_UNDEF = 2 };
enum { U_NONE = 0, U_POINT = 1, U_PERCENT = 2, U_AUTO = 3 };
enum { DIR_COLUMN = 0, DIR_ROW = 1, DIR_COLUMN_REV = 2, DIR_ROW_REV = 3 };
enum { J_START = 0, J_CENTER, J_END, J_BETWEEN, J_AROUND, J_EVENLY };
enum { A_AUTO = 0, A_START, A_CENTER, A_END, A_STRETCH, A_BASELINE, A_BETWEEN, A_AROUND, A_EVENLY };

typedef struct { float v; int unit; } PxVal;

typedef struct {
    int display, position, direction, wrap, justify, align_items, align_self, align_content;
    PxVal dim[2], min[2], max[2], basis;
    PxVal pos[4], margin[4], padding[4], border[4]; /* left, top, right, bottom */
    float grow, shrink, aspect, gap[2], scroll;           /* gap[0] = column gap (x), gap[1] = row gap (y) */
} PxStyle;

typedef struct { float aw, ah, ow; int wm, hm; float rw, rh; } PxCache;
#define CACHE_N 6

typedef struct PxNode {
    int id;
    struct PxNode *parent, *hnext;
    struct PxNode **kids;
    int nkids, capkids;
    PxStyle s;
    int measured, dirty;
    float x, y, w, h;      /* result, relative to parent */
    float sx, sy, sw, sh;  /* last frame reported by calc */
    int reported;
    PxCache cache[CACHE_N];
    int ncache, cnext;
    PxCache perf;          /* constraints of the last perform pass */
    int perf_valid;
} PxNode;

struct PxTree {
    PxMeasureFn measure;
    void *ctx;
    PxNode **buckets;
    int nbuckets, count;
    PxNode *root;
    int *changed;
    int nchanged, capchanged;
    float rw, rh;
    int calced;
};

/* ---- properties --------------------------------------------------------------------------- */
enum { K_ENUM, K_DIM, K_NUM, K_BORDER };
enum {
    P_DISPLAY, P_POSITION, P_DIRECTION, P_WRAP, P_JUSTIFY, P_ALIGN_ITEMS, P_ALIGN_SELF, P_ALIGN_CONTENT,
    P_WIDTH, P_HEIGHT, P_MIN_W, P_MIN_H, P_MAX_W, P_MAX_H, P_BASIS,
    P_GROW, P_SHRINK, P_ASPECT, P_COL_GAP, P_ROW_GAP, P_SCROLL,
    P_LEFT, P_TOP, P_RIGHT, P_BOTTOM,
    P_ML, P_MT, P_MR, P_MB, P_PL, P_PT, P_PR, P_PB, P_BL, P_BT, P_BR, P_BB,
    P_COUNT
};
static const struct { const char *name; int kind; } PROPS[P_COUNT] = {
    {"display", K_ENUM}, {"position", K_ENUM}, {"flex_direction", K_ENUM}, {"flex_wrap", K_ENUM},
    {"justify_content", K_ENUM}, {"align_items", K_ENUM}, {"align_self", K_ENUM}, {"align_content", K_ENUM},
    {"width", K_DIM}, {"height", K_DIM}, {"min_width", K_DIM}, {"min_height", K_DIM},
    {"max_width", K_DIM}, {"max_height", K_DIM}, {"flex_basis", K_DIM},
    {"flex_grow", K_NUM}, {"flex_shrink", K_NUM}, {"aspect_ratio", K_NUM}, {"column_gap", K_NUM}, {"row_gap", K_NUM}, {"scroll", K_NUM},
    {"left", K_DIM}, {"top", K_DIM}, {"right", K_DIM}, {"bottom", K_DIM},
    {"margin_left", K_DIM}, {"margin_top", K_DIM}, {"margin_right", K_DIM}, {"margin_bottom", K_DIM},
    {"padding_left", K_DIM}, {"padding_top", K_DIM}, {"padding_right", K_DIM}, {"padding_bottom", K_DIM},
    {"border_left_width", K_BORDER}, {"border_top_width", K_BORDER},
    {"border_right_width", K_BORDER}, {"border_bottom_width", K_BORDER},
};

static void style_default(PxStyle *s) {
    memset(s, 0, sizeof *s);
    s->align_items = A_STRETCH;
    s->align_content = A_START;
    s->aspect = UNDEF;
    for (int i = 0; i < 2; i++) s->dim[i].unit = s->min[i].unit = s->max[i].unit = U_NONE;
}

int px_prop_id(const char *name) {
    for (int i = 0; i < P_COUNT; i++)
        if (strcmp(PROPS[i].name, name) == 0) return i;
    return -1;
}

static PxVal *dim_slot(PxStyle *s, int p) {
    switch (p) {
    case P_WIDTH: return &s->dim[0];
    case P_HEIGHT: return &s->dim[1];
    case P_MIN_W: return &s->min[0];
    case P_MIN_H: return &s->min[1];
    case P_MAX_W: return &s->max[0];
    case P_MAX_H: return &s->max[1];
    case P_BASIS: return &s->basis;
    case P_LEFT: case P_TOP: case P_RIGHT: case P_BOTTOM: return &s->pos[p - P_LEFT];
    case P_ML: case P_MT: case P_MR: case P_MB: return &s->margin[p - P_ML];
    case P_PL: case P_PT: case P_PR: case P_PB: return &s->padding[p - P_PL];
    case P_BL: case P_BT: case P_BR: case P_BB: return &s->border[p - P_BL];
    }
    return NULL;
}

static int *enum_slot(PxStyle *s, int p) {
    switch (p) {
    case P_DISPLAY: return &s->display;
    case P_POSITION: return &s->position;
    case P_DIRECTION: return &s->direction;
    case P_WRAP: return &s->wrap;
    case P_JUSTIFY: return &s->justify;
    case P_ALIGN_ITEMS: return &s->align_items;
    case P_ALIGN_SELF: return &s->align_self;
    case P_ALIGN_CONTENT: return &s->align_content;
    }
    return NULL;
}

static float *num_slot(PxStyle *s, int p) {
    switch (p) {
    case P_GROW: return &s->grow;
    case P_SHRINK: return &s->shrink;
    case P_ASPECT: return &s->aspect;
    case P_COL_GAP: return &s->gap[0];
    case P_ROW_GAP: return &s->gap[1];
    case P_SCROLL: return &s->scroll;
    }
    return NULL;
}

static int norm_eq(const char *a, const char *b) { /* case-insensitive, '-' == '_' */
    for (;; a++, b++) {
        char x = *a == '-' ? '_' : (char)((*a >= 'A' && *a <= 'Z') ? *a + 32 : *a);
        char y = *b == '-' ? '_' : (char)((*b >= 'A' && *b <= 'Z') ? *b + 32 : *b);
        if (x != y) return 0;
        if (!x) return 1;
    }
}

typedef struct { const char *w; int val; } EnumWord;

static int parse_enum(int p, const char *v, int *out) {
    static const EnumWord JUST[] = {
        {"start", J_START}, {"flex_start", J_START}, {"center", J_CENTER}, {"end", J_END}, {"flex_end", J_END},
        {"space_between", J_BETWEEN}, {"space_around", J_AROUND}, {"space_evenly", J_EVENLY}, {0, 0}};
    static const EnumWord ALIGN[] = {
        {"auto", A_AUTO}, {"start", A_START}, {"flex_start", A_START}, {"center", A_CENTER}, {"end", A_END},
        {"flex_end", A_END}, {"stretch", A_STRETCH}, {"baseline", A_BASELINE}, {"space_between", A_BETWEEN},
        {"space_around", A_AROUND}, {"space_evenly", A_EVENLY}, {0, 0}};
    static const EnumWord DIRS[] = {
        {"column", DIR_COLUMN}, {"row", DIR_ROW}, {"column_reverse", DIR_COLUMN_REV},
        {"row_reverse", DIR_ROW_REV}, {0, 0}};
    static const EnumWord WRAP[] = {
        {"nowrap", 0}, {"wrap", 1}, {"wrap_reverse", 2}, {0, 0}};
    static const EnumWord DISP[] = {{"flex", 0}, {"none", 1}, {0, 0}};
    static const EnumWord POS[] = {
        {"relative", 0}, {"static", 0}, {"absolute", 1}, {0, 0}};
    const EnumWord *tab = NULL;
    switch (p) {
    case P_DISPLAY: tab = DISP; break;
    case P_POSITION: tab = POS; break;
    case P_DIRECTION: tab = DIRS; break;
    case P_WRAP: tab = WRAP; break;
    case P_JUSTIFY: tab = JUST; break;
    default: tab = ALIGN; break;
    }
    for (int i = 0; tab[i].w; i++)
        if (norm_eq(v, tab[i].w)) {
            if (p == P_ALIGN_ITEMS && tab[i].val == A_AUTO) return -1;
            *out = tab[i].val;
            return 0;
        }
    return -1;
}

/* ---- tree --------------------------------------------------------------------------------- */
static PxNode *find(PxTree *t, int id) {
    if (id < 0) return NULL;
    for (PxNode *n = t->buckets[(unsigned)id % (unsigned)t->nbuckets]; n; n = n->hnext)
        if (n->id == id) return n;
    return NULL;
}

static void mark(PxNode *n) {
    for (; n; n = n->parent) {
        n->dirty = 1;
        n->ncache = 0;
        n->perf_valid = 0;
    }
}

static void rehash(PxTree *t) {
    int nb = t->nbuckets * 2;
    PxNode **b = (PxNode **)calloc((size_t)nb, sizeof *b);
    if (!b) return;
    for (int i = 0; i < t->nbuckets; i++)
        for (PxNode *n = t->buckets[i], *nx; n; n = nx) {
            nx = n->hnext;
            unsigned k = (unsigned)n->id % (unsigned)nb;
            n->hnext = b[k];
            b[k] = n;
        }
    free(t->buckets);
    t->buckets = b;
    t->nbuckets = nb;
}

static PxNode *node_new(PxTree *t, int id) {
    if (t->count > t->nbuckets * 2) rehash(t);
    PxNode *n = (PxNode *)calloc(1, sizeof *n);
    if (!n) return NULL;
    n->id = id;
    style_default(&n->s);
    n->dirty = 1;
    unsigned k = (unsigned)id % (unsigned)t->nbuckets;
    n->hnext = t->buckets[k];
    t->buckets[k] = n;
    t->count++;
    return n;
}

PxTree *px_tree_new(PxMeasureFn measure, void *ctx) {
    PxTree *t = (PxTree *)calloc(1, sizeof *t);
    if (!t) return NULL;
    t->measure = measure;
    t->ctx = ctx;
    t->nbuckets = 64;
    t->buckets = (PxNode **)calloc((size_t)t->nbuckets, sizeof *t->buckets);
    if (!t->buckets) { free(t); return NULL; }
    t->root = node_new(t, 1);
    return t;
}

void px_tree_free(PxTree *t) {
    if (!t) return;
    for (int i = 0; i < t->nbuckets; i++)
        for (PxNode *n = t->buckets[i], *nx; n; n = nx) {
            nx = n->hnext;
            free(n->kids);
            free(n);
        }
    free(t->buckets);
    free(t->changed);
    free(t);
}

int px_node_create(PxTree *t, int id) {
    if (id < 0 || find(t, id)) return -1;
    return node_new(t, id) ? 0 : -1;
}

static void detach(PxNode *c) {
    PxNode *p = c->parent;
    if (!p) return;
    for (int i = 0; i < p->nkids; i++)
        if (p->kids[i] == c) {
            memmove(&p->kids[i], &p->kids[i + 1], (size_t)(p->nkids - i - 1) * sizeof *p->kids);
            p->nkids--;
            break;
        }
    c->parent = NULL;
    mark(p);
}

int px_node_delete(PxTree *t, int id) {
    PxNode *n = find(t, id);
    if (!n || n == t->root) return -1;
    detach(n);
    for (int i = 0; i < n->nkids; i++) n->kids[i]->parent = NULL;
    unsigned k = (unsigned)id % (unsigned)t->nbuckets;
    for (PxNode **pp = &t->buckets[k]; *pp; pp = &(*pp)->hnext)
        if (*pp == n) { *pp = n->hnext; break; }
    t->count--;
    free(n->kids);
    free(n);
    return 0;
}

int px_node_insert(PxTree *t, int parent, int child, int index) {
    PxNode *p = find(t, parent), *c = find(t, child);
    if (!p || !c || c == t->root || c->parent) return -1;
    for (PxNode *a = p; a; a = a->parent)
        if (a == c) return -1; /* cycle */
    if (p->nkids == p->capkids) {
        int nc = p->capkids ? p->capkids * 2 : 4;
        PxNode **k = (PxNode **)realloc(p->kids, (size_t)nc * sizeof *k);
        if (!k) return -1;
        p->kids = k;
        p->capkids = nc;
    }
    if (index < 0 || index > p->nkids) index = p->nkids;
    memmove(&p->kids[index + 1], &p->kids[index], (size_t)(p->nkids - index) * sizeof *p->kids);
    p->kids[index] = c;
    p->nkids++;
    c->parent = p;
    c->reported = 0;
    mark(p);
    mark(c);
    return 0;
}

int px_node_remove(PxTree *t, int parent, int child) {
    PxNode *p = find(t, parent), *c = find(t, child);
    if (!p || !c || c->parent != p) return -1;
    detach(c);
    return 0;
}

int px_node_set_measured(PxTree *t, int id, int measured) {
    PxNode *n = find(t, id);
    if (!n) return -1;
    n->measured = measured != 0;
    mark(n);
    return 0;
}

int px_node_mark_dirty(PxTree *t, int id) {
    PxNode *n = find(t, id);
    if (!n) return -1;
    mark(n);
    return 0;
}

int px_node_set_num(PxTree *t, int id, int prop, float value) {
    PxNode *n = find(t, id);
    if (!n || prop < 0 || prop >= P_COUNT) return -1;
    PxVal *d = dim_slot(&n->s, prop);
    float *f = num_slot(&n->s, prop);
    if (d) {
        if (d->unit == U_POINT && d->v == value) return 0;  /* unchanged: no relayout */
        d->v = value; d->unit = U_POINT;
    } else if (f) {
        if (*f == value) return 0;
        *f = value;
    } else if (PROPS[prop].kind == K_ENUM) {
        int *e = enum_slot(&n->s, prop);
        if (*e == (int)value) return 0;
        *e = (int)value;
    } else return -1;
    mark(n);
    return 0;
}

int px_node_set_str(PxTree *t, int id, int prop, const char *value) {
    PxNode *n = find(t, id);
    if (!n || prop < 0 || prop >= P_COUNT || !value) return -1;
    int kind = PROPS[prop].kind;
    if (kind == K_ENUM) {
        int v;
        if (parse_enum(prop, value, &v)) return -1;
        *enum_slot(&n->s, prop) = v;
    } else {
        PxVal *d = dim_slot(&n->s, prop);
        if (!d) return -1;
        if (norm_eq(value, "auto")) { d->v = 0; d->unit = U_AUTO; }
        else {
            char *end = NULL;
            float v = strtof(value, &end);
            if (end == value) return -1;
            if (*end == '%') { if (kind == K_BORDER) return -1; d->v = v; d->unit = U_PERCENT; }
            else if (*end == 0) { d->v = v; d->unit = U_POINT; }
            else return -1;
        }
    }
    mark(n);
    return 0;
}

int px_node_reset(PxTree *t, int id, int prop) {
    PxNode *n = find(t, id);
    if (!n || prop < 0 || prop >= P_COUNT) return -1;
    PxStyle d;
    style_default(&d);
    PxVal *s = dim_slot(&n->s, prop);
    if (s) *s = *dim_slot(&d, prop);
    else if (num_slot(&n->s, prop)) *num_slot(&n->s, prop) = *num_slot(&d, prop);
    else if (enum_slot(&n->s, prop)) *enum_slot(&n->s, prop) = *enum_slot(&d, prop);
    mark(n);
    return 0;
}

/* ---- layout ------------------------------------------------------------------------------- */
static float resolve(PxVal v, float ref) {
    if (v.unit == U_POINT) return v.v;
    if (v.unit == U_PERCENT && DEF(ref)) return v.v * ref / 100.0f;
    return UNDEF;
}

static float fmaxf_(float a, float b) { return a > b ? a : b; }
static float fminf_(float a, float b) { return a < b ? a : b; }

static float clampf(float v, float lo, float hi) {
    if (DEF(hi) && v > hi) v = hi;
    if (DEF(lo) && v < lo) v = lo;
    return v;
}

static float zero(float v) { return DEF(v) ? v : 0.0f; }

/* margin/padding/border of node on edge e, percentages relative to reference width ref */
static float edge(const PxVal *arr, int e, float ref) { return zero(resolve(arr[e], ref)); }

typedef struct {
    PxNode *c;
    float ms[2], me[2];     /* margin start/end per axis */
    float dim[2];           /* definite style size per axis (border-box) or UNDEF */
    float lo[2], hi[2];     /* min/max per axis or UNDEF */
    float basis, hypo, target, cross;
    int frozen, align;
} Item;

static void layout(PxTree *t, PxNode *n, float aw, int wm, float ah, int hm, float ow, int perform,
                   float *out_w, float *out_h);

static void resolve_item_dims(PxNode *c, float iw, float ih, float *dim, float *lo, float *hi) {
    float ref[2] = {iw, ih};
    for (int a = 0; a < 2; a++) {
        dim[a] = resolve(c->s.dim[a], ref[a]);
        lo[a] = resolve(c->s.min[a], ref[a]);
        hi[a] = resolve(c->s.max[a], ref[a]);
    }
    if (DEF(c->s.aspect) && c->s.aspect > 0) {
        if (DEF(dim[0]) && !DEF(dim[1])) dim[1] = dim[0] / c->s.aspect;
        else if (DEF(dim[1]) && !DEF(dim[0])) dim[0] = dim[1] * c->s.aspect;
    }
    for (int a = 0; a < 2; a++)
        if (DEF(dim[a])) dim[a] = clampf(dim[a], lo[a], hi[a]);
}

/* measure child with given (border-box) constraints, no positioning */
static void measure_child(PxTree *t, PxNode *c, float aw, int wm, float ah, int hm, float ow, float *w, float *h) {
    layout(t, c, aw, wm, ah, hm, ow, 0, w, h);
}

static void layout_flex(PxTree *t, PxNode *n, float W, int wm, float H, int hm, float ow, int perform,
                        float pad[4], float *out_w, float *out_h);

static void layout(PxTree *t, PxNode *n, float aw, int wm, float ah, int hm, float ow, int perform,
                   float *out_w, float *out_h) {
    if (perform) {
        PxCache *p = &n->perf;
        if (!n->dirty && n->perf_valid && p->wm == wm && p->hm == hm &&
            (wm == M_UNDEF || p->aw == aw) && (hm == M_UNDEF || p->ah == ah) &&
            (!DEF(ow) ? !DEF(p->ow) : (DEF(p->ow) && p->ow == ow))) {
            *out_w = p->rw;
            *out_h = p->rh;
            return;
        }
    } else {
        for (int i = 0; i < n->ncache; i++) {
            PxCache *c = &n->cache[i];
            if (c->wm == wm && c->hm == hm && (wm == M_UNDEF || c->aw == aw) && (hm == M_UNDEF || c->ah == ah) &&
                (!DEF(ow) ? !DEF(c->ow) : (DEF(c->ow) && c->ow == ow))) {
                *out_w = c->rw;
                *out_h = c->rh;
                return;
            }
        }
    }
    float pad[4]; /* padding + border per edge */
    for (int e = 0; e < 4; e++)
        pad[e] = edge(n->s.padding, e, ow) + zero(n->s.border[e].v);
    float rw, rh;
    layout_flex(t, n, aw, wm, ah, hm, ow, perform, pad, &rw, &rh);
    PxCache e = {aw, ah, ow, wm, hm, rw, rh};
    if (perform) {
        n->perf = e;
        n->perf_valid = 1;
        n->dirty = 0;
        n->w = rw;
        n->h = rh;
    }
    if (n->ncache < CACHE_N) n->cache[n->ncache++] = e;
    else { n->cache[n->cnext] = e; n->cnext = (n->cnext + 1) % CACHE_N; }
    *out_w = rw;
    *out_h = rh;
}

static int item_align(PxNode *container, PxNode *c) {
    int a = c->s.align_self;
    return a == A_AUTO ? container->s.align_items : a;
}

static void layout_flex(PxTree *t, PxNode *n, float W, int wm, float H, int hm, float ow, int perform,
                        float pad[4], float *out_w, float *out_h) {
    const PxStyle *s = &n->s;
    int row = (s->direction == DIR_ROW || s->direction == DIR_ROW_REV);
    int rev = (s->direction == DIR_ROW_REV || s->direction == DIR_COLUMN_REV);
    int M = row ? 0 : 1, C = row ? 1 : 0;           /* main / cross axis index (0 = x, 1 = y) */
    float hpad = pad[0] + pad[2], vpad = pad[1] + pad[3];
    float ext[2] = {hpad, vpad};
    float avail[2] = {W, H};
    int mode[2] = {wm, hm};

    /* own size when it does not depend on children */
    float size[2];
    for (int a = 0; a < 2; a++) {
        if (mode[a] == M_EXACT) size[a] = fmaxf_(avail[a], ext[a]);
        else size[a] = UNDEF;
    }

    /* inner (content box) availability */
    float inner[2];
    int imode[2];
    for (int a = 0; a < 2; a++) {
        imode[a] = mode[a];
        inner[a] = (mode[a] == M_UNDEF) ? UNDEF : fmaxf_(avail[a] - ext[a], 0);
    }
    float innerw_ref = DEF(inner[0]) ? inner[0] : UNDEF; /* percent reference for children's margin/padding */

    /* leaf with measure callback */
    if (n->nkids == 0) {
        float cw = 0, ch = 0;
        if (n->measured && t->measure) {
            t->measure(t->ctx, n->id, DEF(inner[0]) ? inner[0] : 0, imode[0], DEF(inner[1]) ? inner[1] : 0,
                       imode[1], &cw, &ch);
            if (!(cw >= 0)) cw = 0;
            if (!(ch >= 0)) ch = 0;
        }
        for (int a = 0; a < 2; a++) {
            float c = (a == 0 ? cw : ch) + ext[a];
            if (mode[a] == M_EXACT) continue;
            if (mode[a] == M_ATMOST) c = fminf_(c, avail[a]);
            size[a] = c;
        }
        *out_w = size[0];
        *out_h = size[1];
        return;
    }

    /* ---- collect flex items ---- */
    Item *items = (Item *)calloc((size_t)n->nkids, sizeof *items);
    int ni = 0;
    if (!items) { *out_w = DEF(size[0]) ? size[0] : hpad; *out_h = DEF(size[1]) ? size[1] : vpad; return; }
    for (int i = 0; i < n->nkids; i++) {
        PxNode *c = n->kids[i];
        if (c->s.display == 1 || c->s.position == 1) continue;
        Item *it = &items[ni++];
        it->c = c;
        for (int a = 0; a < 2; a++) {
            it->ms[a] = edge(c->s.margin, a, innerw_ref);
            it->me[a] = edge(c->s.margin, a + 2, innerw_ref);
        }
        resolve_item_dims(c, inner[0], inner[1], it->dim, it->lo, it->hi);
        it->align = item_align(n, c);
    }
    /* box-model: min/max are border-box already */

    /* hypothetical main size (basis) */
    for (int i = 0; i < ni; i++) {
        Item *it = &items[i];
        PxNode *c = it->c;
        float b = resolve(c->s.basis, inner[M]);
        if (!DEF(b)) b = it->dim[M];
        if (!DEF(b)) {
            float cw, ch, caw, cah;
            int cwm, chm;
            /* content size: main AT_MOST inner (or undefined), cross as constrained as known */
            float ma = (DEF(inner[M]) && s->scroll == 0) ? inner[M] - it->ms[M] - it->me[M] : UNDEF; /* scroll: main axis unbounded */
            int mm = DEF(ma) ? M_ATMOST : M_UNDEF;
            float ca = UNDEF;
            int cm = M_UNDEF;
            if (DEF(it->dim[C])) { ca = it->dim[C]; cm = M_EXACT; }
            else if (DEF(inner[C])) {
                ca = inner[C] - it->ms[C] - it->me[C];
                cm = (imode[C] == M_EXACT && it->align == A_STRETCH && s->wrap == 0) ? M_EXACT : M_ATMOST;
            }
            if (M == 0) { caw = ma; cwm = mm; cah = ca; chm = cm; }
            else { caw = ca; cwm = cm; cah = ma; chm = mm; }
            measure_child(t, c, caw, cwm, cah, chm, innerw_ref, &cw, &ch);
            b = (M == 0) ? cw : ch;
        }
        it->basis = b;
        it->hypo = clampf(b, it->lo[M], it->hi[M]);
    }

    /* ---- lines ---- */
    float gapM = s->gap[M == 0 ? 0 : 1], gapC = s->gap[C == 0 ? 0 : 1];
    int *line_start = (int *)calloc((size_t)ni + 2, sizeof(int));
    int nlines = 0;
    if (!line_start) { free(items); *out_w = hpad; *out_h = vpad; return; }
    {
        float sum = 0;
        int cnt = 0;
        line_start[0] = 0;
        for (int i = 0; i < ni; i++) {
            float outer = items[i].hypo + items[i].ms[M] + items[i].me[M];
            if (s->wrap && cnt > 0 && DEF(inner[M]) && sum + gapM + outer > inner[M] + 0.001f) {
                line_start[++nlines] = i;
                sum = 0;
                cnt = 0;
            }
            sum += (cnt ? gapM : 0) + outer;
            cnt++;
        }
        nlines++;
        line_start[nlines] = ni;
        if (ni == 0) nlines = 0;
    }

    /* ---- resolve flexible lengths per line ---- */
    float *line_cross = (float *)calloc((size_t)nlines + 1, sizeof(float));
    float *line_main = (float *)calloc((size_t)nlines + 1, sizeof(float));
    if (!line_cross || !line_main) { free(line_cross); free(line_main); free(line_start); free(items); *out_w = hpad; *out_h = vpad; return; }
    float content_main = 0;
    for (int L = 0; L < nlines; L++) {
        int b = line_start[L], e = line_start[L + 1];
        int cnt = e - b;
        float gaps = gapM * (cnt > 1 ? cnt - 1 : 0);
        float sum_hypo = gaps;
        for (int i = b; i < e; i++) sum_hypo += items[i].hypo + items[i].ms[M] + items[i].me[M];
        float free_ = 0;
        if (imode[M] == M_EXACT) free_ = inner[M] - sum_hypo;
        else if (imode[M] == M_ATMOST && sum_hypo > inner[M]) free_ = inner[M] - sum_hypo;
        for (int i = b; i < e; i++) {
            Item *it = &items[i];
            it->target = it->hypo;
            it->frozen = 0;
            if (free_ == 0 || (free_ > 0 && it->c->s.grow <= 0) || (free_ < 0 && it->c->s.shrink <= 0))
                it->frozen = 1;
        }
        for (int iter = 0; iter < cnt + 1 && free_ != 0; iter++) {
            float used = gaps, tg = 0, ts = 0;
            for (int i = b; i < e; i++) {
                Item *it = &items[i];
                used += it->ms[M] + it->me[M] + (it->frozen ? it->target : it->basis);
                if (!it->frozen) { tg += it->c->s.grow; ts += it->c->s.shrink * it->basis; }
            }
            if (tg <= 0 && ts <= 0 && free_ > 0) break;
            float rem = inner[M] - used;
            if (imode[M] != M_EXACT && free_ > 0) rem = 0;
            if (free_ > 0) {
                float k = tg < 1 ? tg : 1;
                rem = rem * k; /* when total grow < 1 only that fraction of free space is distributed */
            }
            float viol = 0;
            for (int i = b; i < e; i++) {
                Item *it = &items[i];
                if (it->frozen) continue;
                float tgt = it->basis;
                if (free_ > 0 && tg > 0) tgt += rem * it->c->s.grow / tg;
                else if (free_ < 0 && ts > 0) tgt += rem * (it->c->s.shrink * it->basis) / ts;
                float cl = clampf(tgt, it->lo[M], it->hi[M]);
                if (cl < 0) cl = 0;
                viol += cl - tgt;
                it->target = cl;
                it->cross = cl - tgt; /* temp: violation */
            }
            int any = 0;
            for (int i = b; i < e; i++) {
                Item *it = &items[i];
                if (it->frozen) continue;
                if (viol == 0 || (viol > 0 && it->cross > 0) || (viol < 0 && it->cross < 0)) {
                    it->frozen = 1;
                    any = 1;
                }
            }
            if (!any) break;
            int left = 0;
            for (int i = b; i < e; i++) if (!items[i].frozen) left = 1;
            if (!left) break;
        }
        float lm = gaps;
        for (int i = b; i < e; i++) lm += items[i].target + items[i].ms[M] + items[i].me[M];
        line_main[L] = lm;
        if (lm > content_main) content_main = lm;
    }

    /* ---- cross sizes ---- */
    float content_cross = 0;
    for (int L = 0; L < nlines; L++) {
        int b = line_start[L], e = line_start[L + 1];
        float lc = 0;
        for (int i = b; i < e; i++) {
            Item *it = &items[i];
            float cw, ch, ca, cm_;
            int cmode;
            if (DEF(it->dim[C])) { ca = it->dim[C]; cmode = M_EXACT; }
            else {
                ca = DEF(inner[C]) ? inner[C] - it->ms[C] - it->me[C] : UNDEF;
                cmode = DEF(ca) ? M_ATMOST : M_UNDEF;
            }
            (void)cm_;
            if (M == 0) measure_child(t, it->c, it->target, M_EXACT, ca, cmode, innerw_ref, &cw, &ch);
            else measure_child(t, it->c, ca, cmode, it->target, M_EXACT, innerw_ref, &cw, &ch);
            it->cross = clampf(M == 0 ? ch : cw, it->lo[C], it->hi[C]);
            float outer = it->cross + it->ms[C] + it->me[C];
            if (outer > lc) lc = outer;
        }
        line_cross[L] = lc;
        content_cross += lc;
    }
    if (nlines > 1) content_cross += gapC * (nlines - 1);

    /* ---- container size ---- */
    float content[2];
    content[M] = content_main + ext[M];
    content[C] = content_cross + ext[C];
    for (int a = 0; a < 2; a++) {
        if (mode[a] == M_EXACT) continue;
        float c = content[a];
        if (mode[a] == M_ATMOST) c = fminf_(c, avail[a]);
        size[a] = c;
    }
    float fin[2] = {fmaxf_(size[0] - hpad, 0), fmaxf_(size[1] - vpad, 0)}; /* final inner size */

    if (!perform) goto done;

    /* ---- single line takes the full cross size; multi-line uses align-content ---- */
    {
        float *line_off = (float *)calloc((size_t)nlines + 1, sizeof(float));
        if (!line_off) goto done;
        float free_c = fin[C] - content_cross;
        float between = 0, start = 0;
        if (nlines == 1) {
            line_cross[0] = fin[C];
        } else if (nlines > 1) {
            switch (s->align_content) {
            case A_STRETCH:
                if (free_c > 0) for (int L = 0; L < nlines; L++) line_cross[L] += free_c / nlines;
                break;
            case A_CENTER: start = free_c / 2; break;
            case A_END: start = free_c; break;
            case A_BETWEEN: if (free_c > 0) between = free_c / (nlines - 1); break;
            case A_AROUND: if (free_c > 0) { between = free_c / nlines; start = between / 2; } break;
            case A_EVENLY: if (free_c > 0) { between = free_c / (nlines + 1); start = between; } break;
            default: break;
            }
        }
        float off = start;
        for (int L = 0; L < nlines; L++) {
            line_off[L] = off;
            off += line_cross[L] + gapC + between;
        }
        int wrap_rev = (s->wrap == 2);

        for (int L = 0; L < nlines; L++) {
            int b = line_start[L], e = line_start[L + 1];
            int cnt = e - b;
            float used = gapM * (cnt > 1 ? cnt - 1 : 0);
            for (int i = b; i < e; i++) used += items[i].target + items[i].ms[M] + items[i].me[M];
            float free_m = fin[M] - used, lead = 0, gap = gapM;
            switch (s->justify) {
            case J_CENTER: lead = free_m / 2; break;
            case J_END: lead = free_m; break;
            case J_BETWEEN: if (free_m > 0 && cnt > 1) gap += free_m / (cnt - 1); break;
            case J_AROUND: if (free_m > 0) { float g = free_m / cnt; lead = g / 2; gap += g; } break;
            case J_EVENLY: if (free_m > 0) { float g = free_m / (cnt + 1); lead = g; gap += g; } break;
            default: break;
            }
            float pos = lead;
            for (int i = b; i < e; i++) {
                Item *it = &items[i];
                float msize = it->target, csize = it->cross;
                int al = it->align;
                if (al == A_STRETCH && !DEF(it->dim[C])) {
                    csize = clampf(line_cross[L] - it->ms[C] - it->me[C], it->lo[C], it->hi[C]);
                    if (csize < 0) csize = 0;
                }
                float lc = line_cross[L];
                float coff;
                float outer_c = csize + it->ms[C] + it->me[C];
                if (al == A_CENTER) coff = (lc - outer_c) / 2;
                else if (al == A_END) coff = lc - outer_c;
                else coff = 0;
                float mstart = pos + it->ms[M];
                float cstart = line_off[L] + coff + it->ms[C];
                if (rev) mstart = fin[M] - mstart - msize;
                if (wrap_rev) cstart = fin[C] - cstart - csize;
                float fx, fy, fw, fh;
                float cw, ch;
                if (M == 0) { fx = mstart; fy = cstart; fw = msize; fh = csize; }
                else { fx = cstart; fy = mstart; fw = csize; fh = msize; }
                layout(t, it->c, fw, M_EXACT, fh, M_EXACT, innerw_ref, 1, &cw, &ch);
                PxNode *c = it->c;
                float dx = 0, dy = 0; /* position: relative offsets (no layout effect on siblings) */
                if (c->s.position == 0) {
                    float rl = resolve(c->s.pos[0], fin[0]), rr = resolve(c->s.pos[2], fin[0]);
                    float rt = resolve(c->s.pos[1], fin[1]), rb = resolve(c->s.pos[3], fin[1]);
                    dx = DEF(rl) ? rl : (DEF(rr) ? -rr : 0);
                    dy = DEF(rt) ? rt : (DEF(rb) ? -rb : 0);
                }
                c->x = pad[0] + fx + dx;
                c->y = pad[1] + fy + dy;
                c->w = cw;
                c->h = ch;
                pos += msize + it->ms[M] + it->me[M] + gap;
            }
        }
        free(line_off);
    }

    /* ---- absolutely positioned children: containing block = padding box ---- */
    {
        float bw = fmaxf_(size[0] - (zero(n->s.border[0].v) + zero(n->s.border[2].v)), 0);
        float bh = fmaxf_(size[1] - (zero(n->s.border[1].v) + zero(n->s.border[3].v)), 0);
        float bl = zero(n->s.border[0].v), bt = zero(n->s.border[1].v);
        for (int i = 0; i < n->nkids; i++) {
            PxNode *c = n->kids[i];
            if (c->s.display == 1 || c->s.position != 1) continue;
            float ref[2] = {bw, bh};
            float dim[2], lo[2], hi[2], off[4], ms[2], me[2];
            resolve_item_dims(c, bw, bh, dim, lo, hi);
            for (int e = 0; e < 4; e++) off[e] = resolve(c->s.pos[e], ref[e % 2]);
            for (int a = 0; a < 2; a++) {
                ms[a] = edge(c->s.margin, a, bw);
                me[a] = edge(c->s.margin, a + 2, bw);
            }
            float sz[2];
            int sm[2];
            for (int a = 0; a < 2; a++) {
                if (DEF(dim[a])) { sz[a] = dim[a]; sm[a] = M_EXACT; }
                else if (DEF(off[a]) && DEF(off[a + 2])) {
                    sz[a] = clampf(fmaxf_(ref[a] - off[a] - off[a + 2] - ms[a] - me[a], 0), lo[a], hi[a]);
                    sm[a] = M_EXACT;
                } else { sz[a] = fmaxf_(ref[a] - (DEF(off[a]) ? off[a] : 0) - (DEF(off[a + 2]) ? off[a + 2] : 0) - ms[a] - me[a], 0); sm[a] = M_ATMOST; }
            }
            float cw, ch;
            layout(t, c, sz[0], sm[0], sz[1], sm[1], bw, 0, &cw, &ch);
            cw = clampf(cw, lo[0], hi[0]);
            ch = clampf(ch, lo[1], hi[1]);
            layout(t, c, cw, M_EXACT, ch, M_EXACT, bw, 1, &cw, &ch);
            float csz[2] = {cw, ch}, p[2];
            for (int a = 0; a < 2; a++) {
                if (DEF(off[a])) p[a] = off[a] + ms[a];
                else if (DEF(off[a + 2])) p[a] = ref[a] - off[a + 2] - csz[a] - me[a];
                else {
                    /* static position: honour justify (main) and align (cross) of the container */
                    int is_main = (a == M);
                    int al = is_main ? (s->justify == J_CENTER ? A_CENTER : s->justify == J_END ? A_END : A_START)
                                     : item_align(n, c);
                    float room = fin[a] - csz[a] - ms[a] - me[a];
                    float o = al == A_CENTER ? room / 2 : al == A_END ? room : 0;
                    p[a] = (a == 0 ? pad[0] - bl : pad[1] - bt) + o + ms[a];
                }
            }
            c->x = bl + p[0];
            c->y = bt + p[1];
            c->w = csz[0];
            c->h = csz[1];
        }
    }

done:
    free(line_cross);
    free(line_main);
    free(line_start);
    free(items);
    *out_w = size[0];
    *out_h = size[1];
}

/* ---- calc --------------------------------------------------------------------------------- */
static void push_changed(PxTree *t, int id) {
    if (t->nchanged == t->capchanged) {
        int nc = t->capchanged ? t->capchanged * 2 : 32;
        int *c = (int *)realloc(t->changed, (size_t)nc * sizeof *c);
        if (!c) return;
        t->changed = c;
        t->capchanged = nc;
    }
    t->changed[t->nchanged++] = id;
}

static void collect(PxTree *t, PxNode *n) {
    if (!n->reported || n->sx != n->x || n->sy != n->y || n->sw != n->w || n->sh != n->h) {
        n->sx = n->x; n->sy = n->y; n->sw = n->w; n->sh = n->h;
        n->reported = 1;
        push_changed(t, n->id);
    }
    if (n->s.display == 1) return;
    for (int i = 0; i < n->nkids; i++) collect(t, n->kids[i]);
}

int px_tree_calc(PxTree *t, float width, float height) {
    PxNode *r = t->root;
    t->nchanged = 0;
    if (!(width >= 0) || !(height >= 0)) return -1;
    if (t->calced && (t->rw != width || t->rh != height)) mark(r);
    t->rw = width;
    t->rh = height;
    t->calced = 1;
    float w, h;
    r->x = r->y = 0;
    /* a root with size styles keeps the window size: the window is authoritative */
    layout(t, r, width, M_EXACT, height, M_EXACT, width, 1, &w, &h);
    r->w = w;
    r->h = h;
    collect(t, r);
    return t->nchanged;
}

int px_tree_changed_count(PxTree *t) { return t->nchanged; }

int px_tree_changed_at(PxTree *t, int i, float *xywh) {
    if (i < 0 || i >= t->nchanged) return -1;
    PxNode *n = find(t, t->changed[i]);
    if (!n) return -1;
    xywh[0] = n->x; xywh[1] = n->y; xywh[2] = n->w; xywh[3] = n->h;
    return n->id;
}

int px_node_frame(PxTree *t, int id, float *xywh) {
    PxNode *n = find(t, id);
    if (!n) return -1;
    xywh[0] = n->x; xywh[1] = n->y; xywh[2] = n->w; xywh[3] = n->h;
    return 0;
}
