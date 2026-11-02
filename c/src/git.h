/* Git layer: local repository operations on top of libgit2.
 *
 * Network operations (fetch/pull/push/clone) live in net.h and run the git
 * CLI asynchronously, like GitHub Desktop does, so the user's SSH setup and
 * git config (pull.rebase, credential helpers…) apply unchanged.
 */
#pragma once

#include <glib.h>

G_BEGIN_DECLS

#define GDL_GIT_ERROR (gdl_git_error_quark ())
GQuark gdl_git_error_quark (void);

typedef enum {
  GDL_GIT_ERROR_FAILED,
  GDL_GIT_ERROR_CONFLICT,          /* merge stopped with conflicts */
  GDL_GIT_ERROR_NOT_MERGED,        /* branch delete refused: unmerged commits */
  GDL_GIT_ERROR_NOTHING_TO_COMMIT,
  GDL_GIT_ERROR_NO_IDENTITY,       /* user.name / user.email missing */
  GDL_GIT_ERROR_INVALID_NAME,
} GdlGitError;

/* File status letters, as shown in the UI badges */
#define GDL_ST_NEW        '?'
#define GDL_ST_ADDED      'A'
#define GDL_ST_MODIFIED   'M'
#define GDL_ST_DELETED    'D'
#define GDL_ST_RENAMED    'R'
#define GDL_ST_COPIED     'C'
#define GDL_ST_CONFLICTED 'U'

typedef struct {
  char    *path;
  char    *orig_path;   /* renames: previous path, else NULL */
  char     status;
  gboolean staged;
} GdlFile;

typedef struct {
  char   *hash;
  char    short_hash[8];
  char   *author;
  char   *email;
  char   *summary;
  char   *body;
  gint64  time;         /* unix seconds */
} GdlCommit;

typedef struct {
  gboolean has_upstream;
  int      ahead;
  int      behind;
  char    *upstream;    /* e.g. "origin/main" */
} GdlSync;

typedef struct _GdlRepo GdlRepo;

void        gdl_file_free   (GdlFile *f);
void        gdl_commit_free (GdlCommit *c);
void        gdl_sync_clear  (GdlSync *s);

/* Opens the repository containing `path` (any subfolder works). */
GdlRepo    *gdl_repo_open   (const char *path, GError **error);
void        gdl_repo_free   (GdlRepo *repo);
gboolean    gdl_repo_init   (const char *path, GError **error);
G_DEFINE_AUTOPTR_CLEANUP_FUNC (GdlRepo, gdl_repo_free)

const char *gdl_repo_path        (GdlRepo *repo);   /* working directory, no trailing slash */
char       *gdl_repo_name        (GdlRepo *repo);
char       *gdl_repo_branch      (GdlRepo *repo);   /* "main", or "HEAD (abc1234)" when detached */
gboolean    gdl_repo_has_commits (GdlRepo *repo);
gboolean    gdl_repo_is_merging  (GdlRepo *repo);
char       *gdl_repo_head_hash   (GdlRepo *repo);   /* NULL on an unborn branch */
void        gdl_repo_identity    (GdlRepo *repo, char **name, char **email);

/* Working tree */
GPtrArray  *gdl_repo_status      (GdlRepo *repo, GError **error);   /* of GdlFile* */
char       *gdl_repo_file_diff   (GdlRepo *repo, const GdlFile *file);
gboolean    gdl_repo_commit      (GdlRepo *repo, GPtrArray *all_files, GHashTable *checked_paths,
                                  const char *summary, const char *description, GError **error);
gboolean    gdl_repo_undo_commit (GdlRepo *repo, char **summary, char **description, GError **error);
gboolean    gdl_repo_discard     (GdlRepo *repo, const GdlFile *file, GError **error);
gboolean    gdl_repo_add_ignore  (GdlRepo *repo, const char *pattern, GError **error);

/* History */
GPtrArray  *gdl_repo_history          (GdlRepo *repo, guint skip, guint limit);   /* of GdlCommit* */
GdlCommit  *gdl_repo_commit_details   (GdlRepo *repo, const char *hash);
GPtrArray  *gdl_repo_commit_files     (GdlRepo *repo, const char *hash);        /* of GdlFile* */
char       *gdl_repo_commit_file_diff (GdlRepo *repo, const char *hash, const char *path, const char *orig_path);

/* Branches */
gboolean    gdl_branch_name_valid      (const char *name);
GPtrArray  *gdl_repo_branches          (GdlRepo *repo, gboolean remote);   /* of char*; remote: "origin/x" */
gboolean    gdl_repo_checkout_branch   (GdlRepo *repo, const char *name, GError **error);
gboolean    gdl_repo_checkout_remote   (GdlRepo *repo, const char *remote_branch, GError **error);
gboolean    gdl_repo_create_branch     (GdlRepo *repo, const char *name, GError **error);   /* and switch to it */
gboolean    gdl_repo_rename_branch     (GdlRepo *repo, const char *old_name, const char *new_name, GError **error);
gboolean    gdl_repo_delete_branch     (GdlRepo *repo, const char *name, gboolean force, GError **error);
gboolean    gdl_repo_merge             (GdlRepo *repo, const char *branch, GError **error);
gboolean    gdl_repo_abort_merge       (GdlRepo *repo, GError **error);

/* Remotes & sync */
GPtrArray  *gdl_repo_remotes        (GdlRepo *repo);                      /* of char* */
char       *gdl_repo_remote_url     (GdlRepo *repo, const char *remote);
void        gdl_repo_sync_status    (GdlRepo *repo, GdlSync *out);
gint64      gdl_repo_last_fetch     (GdlRepo *repo);                      /* unix time, 0 = never */
gboolean    gdl_repo_add_remote     (GdlRepo *repo, const char *name, const char *url, GError **error);
char       *gdl_repo_config_string  (GdlRepo *repo, const char *key);

/* Global identity (~/.gitconfig user.name / user.email) */
void        gdl_global_identity     (char **name, char **email);
gboolean    gdl_set_global_identity (const char *name, const char *email, GError **error);

/* Stash, tagged with the branch like GitHub Desktop */
gboolean    gdl_repo_stash_all      (GdlRepo *repo, GError **error);
int         gdl_repo_find_stash     (GdlRepo *repo, const char *branch);    /* index or -1 */
gboolean    gdl_repo_stash_pop      (GdlRepo *repo, int index, GError **error);
gboolean    gdl_repo_stash_drop     (GdlRepo *repo, int index, GError **error);

G_END_DECLS
