#include "util.h"

#include <string.h>

char *
gdl_time_ago (gint64 t)
{
  if (t <= 0)
    return g_strdup ("never");
  gint64 secs = MAX (0, g_get_real_time () / G_USEC_PER_SEC - t);
  static const struct { const char *unit; gint64 size; } units[] = {
    { "year", 365 * 86400 }, { "month", 30 * 86400 }, { "day", 86400 }, { "hour", 3600 }, { "minute", 60 },
  };
  for (guint i = 0; i < G_N_ELEMENTS (units); i++) {
    if (secs >= units[i].size) {
      gint64 n = secs / units[i].size;
      return g_strdup_printf ("%" G_GINT64_FORMAT " %s%s ago", n, units[i].unit, n > 1 ? "s" : "");
    }
  }
  return g_strdup ("just now");
}

char *
gdl_link_next (const char *link)
{
  /* <https://api.github.com/user/repos?page=2>; rel="next", <…>; rel="last" */
  if (!link)
    return NULL;
  g_auto (GStrv) parts = g_strsplit (link, ",", -1);
  for (char **p = parts; *p; p++) {
    if (!strstr (*p, "rel=\"next\""))
      continue;
    const char *lt = strchr (*p, '<'), *gt = lt ? strchr (lt, '>') : NULL;
    if (lt && gt)
      return g_strndup (lt + 1, gt - lt - 1);
  }
  return NULL;
}

char *
gdl_github_slug (const char *url)
{
  if (!url)
    return NULL;
  const char *host = strstr (url, "github.com");
  if (!host)
    return NULL;
  const char *rest = host + strlen ("github.com");
  while (*rest == ':' || *rest == '/')
    rest++;
  char *slug = g_strdup (rest);
  if (g_str_has_suffix (slug, ".git"))
    slug[strlen (slug) - 4] = '\0';
  if (g_str_has_suffix (slug, "/"))
    slug[strlen (slug) - 1] = '\0';
  if (!strchr (slug, '/')) {
    g_free (slug);
    return NULL;
  }
  return slug;
}

char *
gdl_clone_dir_name (const char *url)
{
  g_autofree char *trimmed = g_strdup (url ? url : "");
  g_strstrip (trimmed);
  while (g_str_has_suffix (trimmed, "/"))
    trimmed[strlen (trimmed) - 1] = '\0';
  const char *base = strrchr (trimmed, '/');
  const char *colon = strrchr (trimmed, ':');
  if (colon && (!base || colon > base))
    base = colon;
  char *name = g_strdup (base ? base + 1 : trimmed);
  if (g_str_has_suffix (name, ".git"))
    name[strlen (name) - 4] = '\0';
  return name;
}

char *
gdl_expand_clone_url (const char *input)
{
  g_autofree char *s = g_strstrip (g_strdup (input ? input : ""));
  /* "desktop/desktop" as GitHub Desktop accepts it */
  if (*s && !strstr (s, "://") && !strchr (s, '@') && !strchr (s, ':') &&
      strchr (s, '/') == strrchr (s, '/') && s[0] != '/' && s[0] != '.')
    return g_strdup_printf ("https://github.com/%s.git", s);
  return g_strdup (s);
}

char *
gdl_escape (const char *text)
{
  return g_markup_escape_text (text ? text : "", -1);
}
