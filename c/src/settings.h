/* App settings in $XDG_CONFIG_HOME/git-desktop-linux/native.ini (mode 0600). */
#pragma once

#include <glib.h>

G_BEGIN_DECLS

char      *settings_get_string (const char *key);              /* NULL when unset */
void       settings_set_string (const char *key, const char *value);
gboolean   settings_get_bool   (const char *key, gboolean fallback);
void       settings_set_bool   (const char *key, gboolean value);

GPtrArray *settings_recent        (void);                      /* existing paths, newest first */
void       settings_add_recent    (const char *path);
void       settings_remove_recent (const char *path);

G_END_DECLS
