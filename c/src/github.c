#include "github.h"

#include "settings.h"
#include "util.h"

#include <json-glib/json-glib.h>
#include <libsecret/secret.h>
#include <libsoup/soup.h>

#define API "https://api.github.com"
#define MAX_PAGES 30  /* 30 × 100 = 3000 repositories */

static const SecretSchema *
token_schema (void)
{
  static const SecretSchema schema = {
    APP_ID ".Token", SECRET_SCHEMA_NONE,
    { { "host", SECRET_SCHEMA_ATTRIBUTE_STRING }, { NULL, 0 } },
  };
  return &schema;
}

void
gdl_profile_free (GdlProfile *p)
{
  if (!p) return;
  g_free (p->login);
  g_free (p->name);
  g_free (p->avatar_url);
  g_free (p->html_url);
  g_free (p);
}

GdlProfile *
gdl_profile_copy (const GdlProfile *p)
{
  if (!p) return NULL;
  GdlProfile *c = g_new0 (GdlProfile, 1);
  c->login = g_strdup (p->login);
  c->name = g_strdup (p->name);
  c->avatar_url = g_strdup (p->avatar_url);
  c->html_url = g_strdup (p->html_url);
  return c;
}

void
gdl_gh_repo_free (GdlGhRepo *r)
{
  if (!r) return;
  g_free (r->name);
  g_free (r->full_name);
  g_free (r->owner);
  g_free (r->description);
  g_free (r->clone_url);
  g_free (r->updated_at);
  g_free (r);
}

void
gdl_account_free (GdlAccount *a)
{
  if (!a) return;
  g_free (a->token);
  gdl_profile_free (a->profile);
  if (a->repos)
    g_ptr_array_unref (a->repos);
  g_free (a);
}

/* ------------------------------------------------------------------ */
/* Token                                                               */
/* ------------------------------------------------------------------ */

gboolean
gdl_token_store (const char *token, GError **error)
{
  settings_set_bool ("use_gh_cli", TRUE);
  return secret_password_store_sync (token_schema (), SECRET_COLLECTION_DEFAULT, "Git Desktop For Linux (GitHub)",
                                     token, NULL, error, "host", "github.com", NULL);
}

void
gdl_token_clear (void)
{
  secret_password_clear_sync (token_schema (), NULL, NULL, "host", "github.com", NULL);
  /* otherwise the gh CLI token would sign the user straight back in */
  settings_set_bool ("use_gh_cli", FALSE);
}

/* Blocking: call from a worker thread */
static char *
token_lookup (void)
{
  g_autoptr (GError) error = NULL;
  char *token = secret_password_lookup_sync (token_schema (), NULL, &error, "host", "github.com", NULL);
  if (token && *token)
    return token;
  g_free (token);
  if (!settings_get_bool ("use_gh_cli", TRUE))
    return NULL;

  /* the GitHub CLI's login, if any */
  g_autofree char *out = NULL;
  int status = 0;
  const char *argv[] = { "gh", "auth", "token", NULL };
  if (!g_spawn_sync (NULL, (char **) argv, NULL, G_SPAWN_SEARCH_PATH | G_SPAWN_STDERR_TO_DEV_NULL,
                     NULL, NULL, &out, NULL, &status, NULL) ||
      !g_spawn_check_wait_status (status, NULL))
    return NULL;
  g_strstrip (out);
  return *out ? g_steal_pointer (&out) : NULL;
}

/* ------------------------------------------------------------------ */
/* HTTP                                                                */
/* ------------------------------------------------------------------ */

static SoupSession *
new_session (void)
{
  return soup_session_new_with_options ("user-agent", "GitDesktopLinux", "timeout", 15, NULL);
}

/* GET → body, optionally the Link header. NULL unless HTTP 200. */
static GBytes *
http_get (SoupSession *session, const char *url, const char *token, char **link, GCancellable *c, GError **error)
{
  g_autoptr (SoupMessage) msg = soup_message_new ("GET", url);
  if (!msg) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT, "Bad URL: %s", url);
    return NULL;
  }
  SoupMessageHeaders *h = soup_message_get_request_headers (msg);
  soup_message_headers_append (h, "Accept", "application/vnd.github+json");
  if (token) {
    g_autofree char *auth = g_strdup_printf ("Bearer %s", token);
    soup_message_headers_append (h, "Authorization", auth);
  }
  GBytes *body = soup_session_send_and_read (session, msg, c, error);
  if (!body)
    return NULL;
  guint code = soup_message_get_status (msg);
  if (code != 200) {
    g_bytes_unref (body);
    g_set_error (error, G_IO_ERROR, code == 401 ? G_IO_ERROR_PERMISSION_DENIED : G_IO_ERROR_FAILED,
                 "GitHub answered %u", code);
    return NULL;
  }
  if (link)
    *link = g_strdup (soup_message_headers_get_one (soup_message_get_response_headers (msg), "Link"));
  return body;
}

static JsonNode *
parse_json (GBytes *body, GError **error)
{
  g_autoptr (JsonParser) parser = json_parser_new ();
  gsize len = 0;
  const char *data = g_bytes_get_data (body, &len);
  if (!json_parser_load_from_data (parser, data, (gssize) len, error))
    return NULL;
  return json_node_copy (json_parser_get_root (parser));
}

static char *
member_string (JsonObject *o, const char *name)
{
  if (!json_object_has_member (o, name) || JSON_NODE_HOLDS_NULL (json_object_get_member (o, name)))
    return g_strdup ("");
  return g_strdup (json_object_get_string_member_with_default (o, name, ""));
}

static GdlProfile *
fetch_profile (SoupSession *s, const char *token, GCancellable *c, GError **error)
{
  g_autoptr (GBytes) body = http_get (s, API "/user", token, NULL, c, error);
  if (!body)
    return NULL;
  g_autoptr (JsonNode) root = parse_json (body, error);
  if (!root || !JSON_NODE_HOLDS_OBJECT (root))
    return NULL;
  JsonObject *o = json_node_get_object (root);
  GdlProfile *p = g_new0 (GdlProfile, 1);
  p->login = member_string (o, "login");
  p->name = member_string (o, "name");
  if (!*p->name) {
    g_free (p->name);
    p->name = g_strdup (p->login);
  }
  p->avatar_url = member_string (o, "avatar_url");
  p->html_url = member_string (o, "html_url");
  return p;
}

/* Every repository the account can access: follows the Link rel="next" pages */
static GPtrArray *
fetch_repos (SoupSession *s, const char *token, GCancellable *c)
{
  GPtrArray *repos = g_ptr_array_new_with_free_func ((GDestroyNotify) gdl_gh_repo_free);
  g_autofree char *url = g_strdup (API "/user/repos?sort=updated&per_page=100"
                                       "&affiliation=owner,collaborator,organization_member");
  for (int page = 0; url && page < MAX_PAGES; page++) {
    g_autofree char *link = NULL;
    g_autoptr (GBytes) body = http_get (s, url, token, &link, c, NULL);
    if (!body)
      break;
    g_autoptr (JsonNode) root = parse_json (body, NULL);
    if (!root || !JSON_NODE_HOLDS_ARRAY (root))
      break;
    JsonArray *arr = json_node_get_array (root);
    for (guint i = 0; i < json_array_get_length (arr); i++) {
      JsonObject *o = json_array_get_object_element (arr, i);
      GdlGhRepo *r = g_new0 (GdlGhRepo, 1);
      r->name = member_string (o, "name");
      r->full_name = member_string (o, "full_name");
      JsonObject *owner = json_object_get_object_member (o, "owner");
      r->owner = owner ? member_string (owner, "login") : g_strdup ("");
      r->description = member_string (o, "description");
      r->clone_url = member_string (o, "clone_url");
      g_autofree char *updated = member_string (o, "updated_at");
      r->updated_at = g_strndup (updated, 10);
      r->is_private = json_object_get_boolean_member_with_default (o, "private", FALSE);
      r->is_fork = json_object_get_boolean_member_with_default (o, "fork", FALSE);
      r->is_archived = json_object_get_boolean_member_with_default (o, "archived", FALSE);
      g_ptr_array_add (repos, r);
    }
    g_free (url);
    url = gdl_link_next (link);
  }
  return repos;
}

/* ------------------------------------------------------------------ */
/* Async entry points                                                  */
/* ------------------------------------------------------------------ */

static void
account_thread (GTask *task, gpointer src, gpointer data, GCancellable *c)
{
  GdlAccount *a = g_new0 (GdlAccount, 1);
  a->token = token_lookup ();
  if (a->token) {
    g_autoptr (SoupSession) s = new_session ();
    a->profile = fetch_profile (s, a->token, c, NULL);
    if (a->profile)
      a->repos = fetch_repos (s, a->token, c);
    else
      g_clear_pointer (&a->token, g_free);  /* revoked/expired token: treat as signed out */
  }
  g_task_return_pointer (task, a, (GDestroyNotify) gdl_account_free);
}

void
gdl_account_load_async (GCancellable *c, GAsyncReadyCallback cb, gpointer user_data)
{
  g_autoptr (GTask) task = g_task_new (NULL, c, cb, user_data);
  g_task_run_in_thread (task, account_thread);
}

GdlAccount *
gdl_account_load_finish (GAsyncResult *res, GError **error)
{
  return g_task_propagate_pointer (G_TASK (res), error);
}

static void
validate_thread (GTask *task, gpointer src, gpointer data, GCancellable *c)
{
  g_autoptr (SoupSession) s = new_session ();
  GError *error = NULL;
  GdlProfile *p = fetch_profile (s, data, c, &error);
  if (p)
    g_task_return_pointer (task, p, (GDestroyNotify) gdl_profile_free);
  else
    g_task_return_error (task, error ? error : g_error_new_literal (G_IO_ERROR, G_IO_ERROR_FAILED, "Invalid token"));
}

void
gdl_token_validate_async (const char *token, GCancellable *c, GAsyncReadyCallback cb, gpointer user_data)
{
  g_autoptr (GTask) task = g_task_new (NULL, c, cb, user_data);
  g_task_set_task_data (task, g_strdup (token), g_free);
  g_task_run_in_thread (task, validate_thread);
}

GdlProfile *
gdl_token_validate_finish (GAsyncResult *res, GError **error)
{
  return g_task_propagate_pointer (G_TASK (res), error);
}

static void
avatar_thread (GTask *task, gpointer src, gpointer data, GCancellable *c)
{
  g_autoptr (SoupSession) s = new_session ();
  const char *base = data;
  g_autofree char *url = g_strdup_printf ("%s%ss=96", base, strchr (base, '?') ? "&" : "?");
  GError *error = NULL;
  GBytes *body = http_get (s, url, NULL, NULL, c, &error);
  if (body)
    g_task_return_pointer (task, body, (GDestroyNotify) g_bytes_unref);
  else
    g_task_return_error (task, error);
}

void
gdl_avatar_load_async (const char *url, GCancellable *c, GAsyncReadyCallback cb, gpointer user_data)
{
  g_autoptr (GTask) task = g_task_new (NULL, c, cb, user_data);
  g_task_set_task_data (task, g_strdup (url), g_free);
  g_task_run_in_thread (task, avatar_thread);
}

GBytes *
gdl_avatar_load_finish (GAsyncResult *res, GError **error)
{
  return g_task_propagate_pointer (G_TASK (res), error);
}
