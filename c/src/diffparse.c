#include "diffparse.h"

#include <stdlib.h>
#include <string.h>

static void
row_free (GdlDiffRow *row)
{
  g_free (row->text);
  g_free (row);
}

static void
add_row (GdlDiff *diff, GdlRowKind kind, int old_no, int new_no, const char *text, gsize len)
{
  GdlDiffRow *row = g_new0 (GdlDiffRow, 1);
  row->kind = kind;
  row->old_no = old_no;
  row->new_no = new_no;
  row->text = g_strndup (text, len);
  g_ptr_array_add (diff->rows, row);
  diff->max_line = MAX (diff->max_line, MAX (old_no, new_no));
}

/* "@@ -12,3 +14,5 @@" -> 12, 14 */
static gboolean
parse_hunk (const char *line, int *old_no, int *new_no)
{
  if (strncmp (line, "@@ -", 4) != 0)
    return FALSE;
  char *end = NULL;
  long o = strtol (line + 4, &end, 10);
  const char *plus = strchr (end, '+');
  if (!plus)
    return FALSE;
  long n = strtol (plus + 1, NULL, 10);
  *old_no = (int) o;
  *new_no = (int) n;
  return TRUE;
}

GdlDiff *
gdl_diff_parse (const char *text, guint max_rows)
{
  GdlDiff *diff = g_new0 (GdlDiff, 1);
  diff->rows = g_ptr_array_new_with_free_func ((GDestroyNotify) row_free);
  if (!text)
    return diff;

  int old_no = 0, new_no = 0;
  gboolean in_hunk = FALSE;
  const char *p = text;
  while (*p) {
    const char *nl = strchr (p, '\n');
    gsize len = nl ? (gsize) (nl - p) : strlen (p);
    g_autofree char *line = g_strndup (p, len);

    if (max_rows && diff->rows->len >= max_rows) {
      add_row (diff, GDL_ROW_META, 0, 0, "… diff truncated", strlen ("… diff truncated"));
      break;
    }
    if (!in_hunk && g_str_has_prefix (line, "Binary files")) {
      diff->binary = TRUE;
      g_ptr_array_set_size (diff->rows, 0);
      break;
    }
    if (parse_hunk (line, &old_no, &new_no)) {
      in_hunk = TRUE;
      add_row (diff, GDL_ROW_HUNK, 0, 0, line, len);
    } else if (g_str_has_prefix (line, "diff --git")) {
      in_hunk = FALSE;  /* next file in a multi-file diff */
    } else if (in_hunk) {
      switch (line[0]) {
      case '+':  add_row (diff, GDL_ROW_ADD, 0, new_no++, line, len); break;
      case '-':  add_row (diff, GDL_ROW_DEL, old_no++, 0, line, len); break;
      case '\\': add_row (diff, GDL_ROW_META, 0, 0, line, len); break;
      default:   add_row (diff, GDL_ROW_CONTEXT, old_no++, new_no++, line, len); break;
      }
    }
    if (!nl)
      break;
    p = nl + 1;
  }
  return diff;
}

void
gdl_diff_free (GdlDiff *diff)
{
  if (!diff) return;
  g_ptr_array_unref (diff->rows);
  g_free (diff);
}
