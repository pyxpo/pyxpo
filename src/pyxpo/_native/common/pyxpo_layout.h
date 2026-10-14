/* pyxpo flexbox layout engine. Shared by the Android and iOS appliers.
 * All lengths are dp/pt floats; the caller converts to pixels. Frames are relative to the parent.
 * Not thread safe: call from one thread (the UI thread). */
#ifndef PYXPO_LAYOUT_H
#define PYXPO_LAYOUT_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct PxTree PxTree;

/* Text/leaf measure callback. w/h are the available INNER size (padding and border removed).
 * mode: 0 = exact, 1 = at most, 2 = undefined (w/h ignored). Write the content size to out_w/out_h. */
typedef void (*PxMeasureFn)(void *ctx, int id, float w, int w_mode, float h, int h_mode,
                            float *out_w, float *out_h);

/* The tree always contains a root node with id 1. */
PxTree *px_tree_new(PxMeasureFn measure, void *ctx);
void px_tree_free(PxTree *t);

/* Structure. Return 0 on success, -1 on error (unknown id, cycle, already attached...). */
int px_node_create(PxTree *t, int id);
int px_node_delete(PxTree *t, int id);              /* detaches from parent; children become detached */
int px_node_insert(PxTree *t, int parent, int child, int index);
int px_node_remove(PxTree *t, int parent, int child);

/* Mark a measured leaf as needing remeasure (text changed). */
int px_node_set_measured(PxTree *t, int id, int measured);  /* flag leaf as having a measure callback */
int px_node_mark_dirty(PxTree *t, int id);

/* Style. px_prop_id maps a style key such as "flex_direction" to a property id (-1 if not a layout key). */
int px_prop_id(const char *name);
int px_node_set_num(PxTree *t, int id, int prop, float value);        /* points, or a unitless number */
int px_node_set_str(PxTree *t, int id, int prop, const char *value);  /* "50%", "auto", or an enum word */
int px_node_reset(PxTree *t, int id, int prop);                       /* back to default */

/* Layout. Computes frames for the whole tree with the root fixed at width x height. */
int px_tree_calc(PxTree *t, float width, float height);
int px_tree_changed_count(PxTree *t);                          /* frames that changed in the last calc */
int px_tree_changed_at(PxTree *t, int i, float *xywh);         /* returns node id, fills x,y,w,h */
int px_node_frame(PxTree *t, int id, float *xywh);             /* last computed frame, 0 on success */

#ifdef __cplusplus
}
#endif
#endif
