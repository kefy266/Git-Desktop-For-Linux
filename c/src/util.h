/* Small GTK-free helpers (unit tested). */
#pragma once

#include <glib.h>

G_BEGIN_DECLS

/* "3 hours ago", "just now", … */
char *gdl_time_ago        (gint64 unix_time);
/* URL of rel="next" in a GitHub `Link:` header, or NULL */
char *gdl_link_next       (const char *link_header);
/* "owner/repo" for github.com remotes (https or ssh), else NULL */
char *gdl_github_slug     (const char *remote_url);
/* Last path component without ".git": folder name for a clone */
char *gdl_clone_dir_name  (const char *url);
/* "owner/repo" shorthand → https URL; other input returned as is */
char *gdl_expand_clone_url (const char *input);
/* Markup-safe copy */
char *gdl_escape          (const char *text);

G_END_DECLS
