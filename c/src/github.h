/* GitHub account: token in the system keyring, profile, repositories, avatar.
 * All network work runs in a GTask thread; callbacks arrive on the main loop. */
#pragma once

#include <gio/gio.h>

G_BEGIN_DECLS

typedef struct {
  char *login;
  char *name;
  char *avatar_url;
  char *html_url;
} GdlProfile;

typedef struct {
  char    *name;
  char    *full_name;
  char    *owner;
  char    *description;
  char    *clone_url;
  char    *updated_at;   /* YYYY-MM-DD */
  gboolean is_private;
  gboolean is_fork;
  gboolean is_archived;
} GdlGhRepo;

typedef struct {
  char       *token;     /* NULL when signed out */
  GdlProfile *profile;   /* NULL when signed out or the token is invalid */
  GPtrArray  *repos;     /* of GdlGhRepo*, NULL when signed out */
} GdlAccount;

void        gdl_profile_free (GdlProfile *p);
void        gdl_gh_repo_free (GdlGhRepo *r);
void        gdl_account_free (GdlAccount *a);
GdlProfile *gdl_profile_copy (const GdlProfile *p);

/* Keyring (libsecret). Clearing also stops falling back to the gh CLI token. */
gboolean    gdl_token_store  (const char *token, GError **error);
void        gdl_token_clear  (void);

/* Token (keyring, then `gh auth token`) → profile → every repository */
void        gdl_account_load_async  (GCancellable *c, GAsyncReadyCallback cb, gpointer user_data);
GdlAccount *gdl_account_load_finish (GAsyncResult *res, GError **error);

/* Checks a token before it is saved; NULL profile = rejected */
void        gdl_token_validate_async  (const char *token, GCancellable *c, GAsyncReadyCallback cb, gpointer user_data);
GdlProfile *gdl_token_validate_finish (GAsyncResult *res, GError **error);

void        gdl_avatar_load_async  (const char *url, GCancellable *c, GAsyncReadyCallback cb, gpointer user_data);
GBytes     *gdl_avatar_load_finish (GAsyncResult *res, GError **error);

#define GDL_TOKEN_URL "https://github.com/settings/tokens/new?scopes=repo,read:org,workflow&description=Git%20Desktop%20For%20Linux"

G_END_DECLS
