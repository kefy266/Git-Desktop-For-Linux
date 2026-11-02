/* Unified diff → display rows with old/new line numbers (GitHub Desktop style). */
#pragma once

#include <glib.h>

G_BEGIN_DECLS

typedef enum {
  GDL_ROW_CONTEXT,
  GDL_ROW_ADD,
  GDL_ROW_DEL,
  GDL_ROW_HUNK,
  GDL_ROW_META,      /* "\ No newline at end of file", truncation notice */
} GdlRowKind;

typedef struct {
  GdlRowKind kind;
  int        old_no;   /* 0 = none */
  int        new_no;
  char      *text;
} GdlDiffRow;

typedef struct {
  GPtrArray *rows;     /* of GdlDiffRow* */
  gboolean   binary;
  int        max_line; /* widest line number, for the gutter */
} GdlDiff;

/* File headers (diff --git, index, ---, +++) are dropped. Stops after max_rows. */
GdlDiff *gdl_diff_parse (const char *text, guint max_rows);
void     gdl_diff_free  (GdlDiff *diff);
G_DEFINE_AUTOPTR_CLEANUP_FUNC (GdlDiff, gdl_diff_free)

G_END_DECLS
