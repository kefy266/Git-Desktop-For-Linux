#include "settings.h"

#include <glib/gstdio.h>

#define GROUP "app"
#define MAX_RECENT 20

static GKeyFile *keyfile;
static char *keyfile_path;

static GKeyFile *
kf (void)
{
  if (!keyfile) {
    g_autofree char *dir = g_build_filename (g_get_user_config_dir (), "git-desktop-linux", NULL);
    g_mkdir_with_parents (dir, 0700);
    keyfile_path = g_build_filename (dir, "native.ini", NULL);
    keyfile = g_key_file_new ();
    g_key_file_load_from_file (keyfile, keyfile_path, G_KEY_FILE_NONE, NULL);
  }
  return keyfile;
}

static void
save (void)
{
  gsize len = 0;
  g_autofree char *data = g_key_file_to_data (kf (), &len, NULL);
  g_autoptr (GError) error = NULL;
  if (!g_file_set_contents_full (keyfile_path, data, len, G_FILE_SET_CONTENTS_CONSISTENT, 0600, &error))
    g_warning ("Could not save settings: %s", error->message);
}

char *
settings_get_string (const char *key)
{
  char *v = g_key_file_get_string (kf (), GROUP, key, NULL);
  if (v && !*v)
    g_clear_pointer (&v, g_free);
  return v;
}

void
settings_set_string (const char *key, const char *value)
{
  g_key_file_set_string (kf (), GROUP, key, value ? value : "");
  save ();
}

gboolean
settings_get_bool (const char *key, gboolean fallback)
{
  g_autoptr (GError) error = NULL;
  gboolean v = g_key_file_get_boolean (kf (), GROUP, key, &error);
  return error ? fallback : v;
}

void
settings_set_bool (const char *key, gboolean value)
{
  g_key_file_set_boolean (kf (), GROUP, key, value);
  save ();
}

static GStrv
recent_raw (void)
{
  GStrv v = g_key_file_get_string_list (kf (), GROUP, "recent", NULL, NULL);
  return v ? v : g_new0 (char *, 1);
}

GPtrArray *
settings_recent (void)
{
  g_auto (GStrv) raw = recent_raw ();
  GPtrArray *out = g_ptr_array_new_with_free_func (g_free);
  for (char **p = raw; *p; p++)
    if (g_file_test (*p, G_FILE_TEST_IS_DIR))
      g_ptr_array_add (out, g_strdup (*p));
  return out;
}

static void
store_recent (GPtrArray *list)
{
  g_key_file_set_string_list (kf (), GROUP, "recent", (const char *const *) list->pdata, list->len);
  save ();
}

void
settings_add_recent (const char *path)
{
  g_autoptr (GPtrArray) list = settings_recent ();
  for (guint i = 0; i < list->len; i++)
    if (g_str_equal (g_ptr_array_index (list, i), path))
      g_ptr_array_remove_index (list, i--);
  g_ptr_array_insert (list, 0, g_strdup (path));
  if (list->len > MAX_RECENT)
    g_ptr_array_set_size (list, MAX_RECENT);
  store_recent (list);
}

void
settings_remove_recent (const char *path)
{
  g_autoptr (GPtrArray) list = settings_recent ();
  for (guint i = 0; i < list->len; i++)
    if (g_str_equal (g_ptr_array_index (list, i), path))
      g_ptr_array_remove_index (list, i--);
  store_recent (list);
}
