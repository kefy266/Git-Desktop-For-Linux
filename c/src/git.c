/* Git layer on libgit2. See git.h. */
#include "git.h"

#include <gio/gio.h>
#include <git2.h>
#include <string.h>
#include <sys/stat.h>

struct _GdlRepo {
  git_repository *repo;
  char           *workdir;   /* no trailing slash */
};

G_DEFINE_QUARK (gdl-git-error-quark, gdl_git_error)

static void
ensure_libgit2 (void)
{
  static gsize once = 0;
  if (g_once_init_enter (&once)) {
    git_libgit2_init ();
    g_once_init_leave (&once, 1);
  }
}

/* Turns the last libgit2 error into a GError. Always returns FALSE. */
static gboolean
fail (GError **error, int code, const char *prefix)
{
  const git_error *e = git_error_last ();
  const char *msg = (e && e->message) ? e->message : "unknown error";
  if (prefix)
    g_set_error (error, GDL_GIT_ERROR, code, "%s: %s", prefix, msg);
  else
    g_set_error_literal (error, GDL_GIT_ERROR, code, msg);
  return FALSE;
}

void
gdl_file_free (GdlFile *f)
{
  if (!f) return;
  g_free (f->path);
  g_free (f->orig_path);
  g_free (f);
}

void
gdl_commit_free (GdlCommit *c)
{
  if (!c) return;
  g_free (c->hash);
  g_free (c->author);
  g_free (c->email);
  g_free (c->summary);
  g_free (c->body);
  g_free (c);
}

void
gdl_sync_clear (GdlSync *s)
{
  g_clear_pointer (&s->upstream, g_free);
}

/* ------------------------------------------------------------------ */
/* Open / init                                                         */
/* ------------------------------------------------------------------ */

GdlRepo *
gdl_repo_open (const char *path, GError **error)
{
  ensure_libgit2 ();
  git_repository *repo = NULL;
  if (git_repository_open_ext (&repo, path, 0, NULL) < 0) {
    fail (error, GDL_GIT_ERROR_FAILED, NULL);
    return NULL;
  }
  if (git_repository_is_bare (repo)) {
    git_repository_free (repo);
    g_set_error_literal (error, GDL_GIT_ERROR, GDL_GIT_ERROR_FAILED, "Bare repositories are not supported");
    return NULL;
  }
  GdlRepo *self = g_new0 (GdlRepo, 1);
  self->repo = repo;
  self->workdir = g_strdup (git_repository_workdir (repo));
  gsize len = strlen (self->workdir);
  if (len > 1 && self->workdir[len - 1] == '/')
    self->workdir[len - 1] = '\0';
  return self;
}

void
gdl_repo_free (GdlRepo *self)
{
  if (!self) return;
  git_repository_free (self->repo);
  g_free (self->workdir);
  g_free (self);
}

gboolean
gdl_repo_init (const char *path, GError **error)
{
  ensure_libgit2 ();
  git_repository *repo = NULL;
  git_repository_init_options opts = GIT_REPOSITORY_INIT_OPTIONS_INIT;
  opts.flags = GIT_REPOSITORY_INIT_MKPATH;
  if (git_repository_init_ext (&repo, path, &opts) < 0)
    return fail (error, GDL_GIT_ERROR_FAILED, "Could not create repository");
  git_repository_free (repo);
  return TRUE;
}

const char *
gdl_repo_path (GdlRepo *self)
{
  return self->workdir;
}

char *
gdl_repo_name (GdlRepo *self)
{
  return g_path_get_basename (self->workdir);
}

gboolean
gdl_repo_has_commits (GdlRepo *self)
{
  return git_repository_head_unborn (self->repo) == 0;
}

gboolean
gdl_repo_is_merging (GdlRepo *self)
{
  return git_repository_state (self->repo) == GIT_REPOSITORY_STATE_MERGE;
}

char *
gdl_repo_branch (GdlRepo *self)
{
  git_reference *head = NULL;
  if (git_repository_head_unborn (self->repo) == 1) {
    /* unborn: HEAD still names the branch, e.g. refs/heads/main */
    if (git_reference_lookup (&head, self->repo, "HEAD") == 0) {
      const char *target = git_reference_symbolic_target (head);
      char *name = g_strdup (target && g_str_has_prefix (target, "refs/heads/") ? target + 11 : "main");
      git_reference_free (head);
      return name;
    }
    return g_strdup ("main");
  }
  if (git_repository_head (&head, self->repo) < 0)
    return g_strdup ("No branch");
  char *name;
  if (git_repository_head_detached (self->repo) == 1) {
    char sha[8];
    git_oid_tostr (sha, sizeof sha, git_reference_target (head));
    name = g_strdup_printf ("HEAD (%s)", sha);
  } else {
    name = g_strdup (git_reference_shorthand (head));
  }
  git_reference_free (head);
  return name;
}

char *
gdl_repo_head_hash (GdlRepo *self)
{
  git_oid oid;
  if (git_reference_name_to_id (&oid, self->repo, "HEAD") < 0)
    return NULL;
  return g_strdup (git_oid_tostr_s (&oid));
}

void
gdl_repo_identity (GdlRepo *self, char **name, char **email)
{
  git_signature *sig = NULL;
  *name = *email = NULL;
  if (git_signature_default (&sig, self->repo) == 0) {
    *name = g_strdup (sig->name);
    *email = g_strdup (sig->email);
    git_signature_free (sig);
  }
}

/* HEAD commit, or NULL on an unborn branch */
static git_commit *
head_commit (GdlRepo *self)
{
  git_object *obj = NULL;
  if (git_revparse_single (&obj, self->repo, "HEAD^{commit}") < 0)
    return NULL;
  return (git_commit *) obj;
}

/* ------------------------------------------------------------------ */
/* Status                                                              */
/* ------------------------------------------------------------------ */

GPtrArray *
gdl_repo_status (GdlRepo *self, GError **error)
{
  git_status_options opts = GIT_STATUS_OPTIONS_INIT;
  opts.show = GIT_STATUS_SHOW_INDEX_AND_WORKDIR;
  opts.flags = GIT_STATUS_OPT_INCLUDE_UNTRACKED | GIT_STATUS_OPT_RECURSE_UNTRACKED_DIRS |
               GIT_STATUS_OPT_RENAMES_HEAD_TO_INDEX | GIT_STATUS_OPT_SORT_CASE_INSENSITIVELY;
  git_status_list *list = NULL;
  if (git_status_list_new (&list, self->repo, &opts) < 0) {
    fail (error, GDL_GIT_ERROR_FAILED, "Could not read status");
    return NULL;
  }

  GPtrArray *files = g_ptr_array_new_with_free_func ((GDestroyNotify) gdl_file_free);
  size_t n = git_status_list_entrycount (list);
  for (size_t i = 0; i < n; i++) {
    const git_status_entry *e = git_status_byindex (list, i);
    unsigned int s = e->status;
    if (s == GIT_STATUS_CURRENT || (s & GIT_STATUS_IGNORED))
      continue;
    const git_diff_delta *d = e->index_to_workdir ? e->index_to_workdir : e->head_to_index;
    if (!d)
      continue;

    GdlFile *f = g_new0 (GdlFile, 1);
    f->path = g_strdup (d->new_file.path);
    f->staged = (s & (GIT_STATUS_INDEX_NEW | GIT_STATUS_INDEX_MODIFIED | GIT_STATUS_INDEX_DELETED |
                      GIT_STATUS_INDEX_RENAMED | GIT_STATUS_INDEX_TYPECHANGE)) != 0;
    if (s & GIT_STATUS_CONFLICTED)
      f->status = GDL_ST_CONFLICTED;
    else if (s & GIT_STATUS_INDEX_RENAMED) {
      f->status = GDL_ST_RENAMED;
      f->orig_path = g_strdup (e->head_to_index->old_file.path);
      g_free (f->path);
      f->path = g_strdup (e->head_to_index->new_file.path);
    } else if ((s & GIT_STATUS_WT_NEW) && !(s & GIT_STATUS_INDEX_NEW))
      f->status = GDL_ST_NEW;
    else if (s & GIT_STATUS_INDEX_NEW)
      f->status = (s & GIT_STATUS_WT_DELETED) ? GDL_ST_DELETED : GDL_ST_ADDED;
    else if (s & (GIT_STATUS_INDEX_DELETED | GIT_STATUS_WT_DELETED))
      f->status = GDL_ST_DELETED;
    else
      f->status = GDL_ST_MODIFIED;
    g_ptr_array_add (files, f);
  }
  git_status_list_free (list);
  return files;
}

static char *
diff_to_string (git_diff *diff)
{
  git_buf buf = GIT_BUF_INIT;
  char *out;
  if (git_diff_to_buf (&buf, diff, GIT_DIFF_FORMAT_PATCH) < 0)
    out = g_strdup ("");
  else
    out = g_strndup (buf.ptr, buf.size);
  git_buf_dispose (&buf);
  return out;
}

char *
gdl_repo_file_diff (GdlRepo *self, const GdlFile *file)
{
  /* HEAD (or nothing) -> index+working tree, limited to this file */
  git_commit *head = head_commit (self);
  git_tree *tree = NULL;
  if (head)
    git_commit_tree (&tree, head);

  char *paths[2] = { file->path, file->orig_path };
  git_diff_options opts = GIT_DIFF_OPTIONS_INIT;
  opts.flags = GIT_DIFF_INCLUDE_UNTRACKED | GIT_DIFF_SHOW_UNTRACKED_CONTENT |
               GIT_DIFF_RECURSE_UNTRACKED_DIRS | GIT_DIFF_DISABLE_PATHSPEC_MATCH;
  opts.pathspec.strings = paths;
  opts.pathspec.count = file->orig_path ? 2 : 1;

  git_diff *diff = NULL;
  char *out;
  if (git_diff_tree_to_workdir_with_index (&diff, self->repo, tree, &opts) < 0) {
    out = g_strdup ("");
  } else {
    git_diff_find_options find = GIT_DIFF_FIND_OPTIONS_INIT;
    find.flags = GIT_DIFF_FIND_RENAMES;
    git_diff_find_similar (diff, &find);
    out = diff_to_string (diff);
  }
  git_diff_free (diff);
  git_tree_free (tree);
  git_commit_free (head);
  return out;
}

/* ------------------------------------------------------------------ */
/* Commit / undo / discard                                             */
/* ------------------------------------------------------------------ */

static gboolean
file_in_workdir (GdlRepo *self, const char *path)
{
  g_autofree char *full = g_build_filename (self->workdir, path, NULL);
  struct stat st;
  return lstat (full, &st) == 0;
}

/* Puts `path` back to its HEAD state in the index (or drops it when HEAD has none). */
static int
unstage_path (GdlRepo *self, git_index *index, git_commit *head, const char *path)
{
  if (!head)
    return git_index_remove_bypath (index, path);
  char *p = (char *) path;
  git_strarray spec = { &p, 1 };
  int rc = git_reset_default (self->repo, (git_object *) head, &spec);
  if (rc == 0)
    git_index_read (index, TRUE);  /* reset wrote the index behind our back */
  return rc;
}

static int
collect_merge_head (const git_oid *oid, void *payload)
{
  g_array_append_val ((GArray *) payload, *oid);
  return 0;
}

gboolean
gdl_repo_commit (GdlRepo *self, GPtrArray *all_files, GHashTable *checked_paths,
                 const char *summary, const char *description, GError **error)
{
  g_autofree char *trimmed = g_strstrip (g_strdup (summary ? summary : ""));
  if (!*trimmed) {
    g_set_error_literal (error, GDL_GIT_ERROR, GDL_GIT_ERROR_FAILED, "The commit summary is required.");
    return FALSE;
  }

  git_signature *sig = NULL;
  if (git_signature_default (&sig, self->repo) < 0) {
    g_set_error_literal (error, GDL_GIT_ERROR, GDL_GIT_ERROR_NO_IDENTITY,
                         "Set your name and email first (Preferences → Git).");
    return FALSE;
  }

  gboolean ok = FALSE;
  git_index *index = NULL;
  git_commit *head = head_commit (self);
  git_tree *tree = NULL, *parent_tree = NULL;
  GArray *parents_oid = g_array_new (FALSE, FALSE, sizeof (git_oid));
  GPtrArray *parents = g_ptr_array_new_with_free_func ((GDestroyNotify) git_commit_free);
  gboolean merging = gdl_repo_is_merging (self);
  char *message = NULL;  /* freed at `out`: must be initialised before any goto */

  if (git_repository_index (&index, self->repo) < 0) {
    fail (error, GDL_GIT_ERROR_FAILED, "Could not open the index");
    goto out;
  }

  /* Stage exactly the checked files; put unchecked ones back to HEAD */
  for (guint i = 0; i < all_files->len; i++) {
    GdlFile *f = g_ptr_array_index (all_files, i);
    int rc;
    if (g_hash_table_contains (checked_paths, f->path)) {
      rc = file_in_workdir (self, f->path) ? git_index_add_bypath (index, f->path)
                                           : git_index_remove_bypath (index, f->path);
      if (rc == 0 && f->orig_path)
        rc = git_index_remove_bypath (index, f->orig_path);
    } else if (f->staged) {
      rc = unstage_path (self, index, head, f->path);
      if (rc == 0 && f->orig_path)
        rc = unstage_path (self, index, head, f->orig_path);
    } else {
      rc = 0;
    }
    if (rc < 0) {
      fail (error, GDL_GIT_ERROR_FAILED, f->path);
      goto out;
    }
  }

  if (git_index_has_conflicts (index)) {
    g_set_error_literal (error, GDL_GIT_ERROR, GDL_GIT_ERROR_CONFLICT,
                         "Resolve all conflicts and include the conflicted files before committing.");
    goto out;
  }
  git_oid tree_oid, commit_oid;
  if (git_index_write (index) < 0 || git_index_write_tree (&tree_oid, index) < 0 ||
      git_tree_lookup (&tree, self->repo, &tree_oid) < 0) {
    fail (error, GDL_GIT_ERROR_FAILED, "Could not write the tree");
    goto out;
  }

  if (head) {
    g_ptr_array_add (parents, head);
    git_commit_tree (&parent_tree, head);
    head = NULL;  /* owned by `parents` now */
  }
  if (merging) {
    git_repository_mergehead_foreach (self->repo, collect_merge_head, parents_oid);
    for (guint i = 0; i < parents_oid->len; i++) {
      git_commit *c = NULL;
      if (git_commit_lookup (&c, self->repo, &g_array_index (parents_oid, git_oid, i)) == 0)
        g_ptr_array_add (parents, c);
    }
  }
  if (!merging && parent_tree && git_oid_equal (git_tree_id (parent_tree), &tree_oid)) {
    g_set_error_literal (error, GDL_GIT_ERROR, GDL_GIT_ERROR_NOTHING_TO_COMMIT, "There is nothing to commit.");
    goto out;
  }

  {
    g_autofree char *s = g_strstrip (g_strdup (summary));
    g_autofree char *d = description ? g_strstrip (g_strdup (description)) : g_strdup ("");
    message = *d ? g_strdup_printf ("%s\n\n%s\n", s, d) : g_strdup_printf ("%s\n", s);
  }
  if (git_commit_create (&commit_oid, self->repo, "HEAD", sig, sig, NULL, message, tree,
                         parents->len, (const git_commit **) parents->pdata) < 0) {
    fail (error, GDL_GIT_ERROR_FAILED, "Commit failed");
    goto out;
  }
  if (merging)
    git_repository_state_cleanup (self->repo);
  ok = TRUE;

out:
  g_free (message);
  g_ptr_array_unref (parents);
  g_array_unref (parents_oid);
  git_tree_free (tree);
  git_tree_free (parent_tree);
  git_commit_free (head);
  git_index_free (index);
  git_signature_free (sig);
  return ok;
}

gboolean
gdl_repo_undo_commit (GdlRepo *self, char **summary, char **description, GError **error)
{
  git_commit *head = head_commit (self);
  if (!head) {
    g_set_error_literal (error, GDL_GIT_ERROR, GDL_GIT_ERROR_FAILED, "There is no commit to undo.");
    return FALSE;
  }
  if (summary)
    *summary = g_strdup (git_commit_summary (head));
  if (description)
    *description = g_strdup (git_commit_body (head) ? git_commit_body (head) : "");

  gboolean ok = TRUE;
  if (git_commit_parentcount (head) == 0) {
    /* first commit: delete the branch ref so HEAD is unborn again; the index keeps the files */
    git_reference *ref = NULL;
    if (git_repository_head (&ref, self->repo) < 0 || git_reference_delete (ref) < 0)
      ok = fail (error, GDL_GIT_ERROR_FAILED, "Could not undo the commit");
    git_reference_free (ref);
  } else {
    git_commit *parent = NULL;
    if (git_commit_parent (&parent, head, 0) < 0 ||
        git_reset (self->repo, (git_object *) parent, GIT_RESET_SOFT, NULL) < 0)
      ok = fail (error, GDL_GIT_ERROR_FAILED, "Could not undo the commit");
    git_commit_free (parent);
  }
  git_commit_free (head);
  return ok;
}

gboolean
gdl_repo_discard (GdlRepo *self, const GdlFile *file, GError **error)
{
  git_index *index = NULL;
  git_commit *head = head_commit (self);
  gboolean ok = TRUE;

  if (git_repository_index (&index, self->repo) < 0) {
    git_commit_free (head);
    return fail (error, GDL_GIT_ERROR_FAILED, "Could not open the index");
  }

  /* Files that do not exist in HEAD: remove from the index, move to the trash */
  gboolean new_file = file->status == GDL_ST_NEW || file->status == GDL_ST_ADDED || file->status == GDL_ST_RENAMED;
  if (new_file) {
    git_index_remove_bypath (index, file->path);
    git_index_write (index);
    g_autofree char *full = g_build_filename (self->workdir, file->path, NULL);
    g_autoptr (GFile) gf = g_file_new_for_path (full);
    g_autoptr (GError) trash_err = NULL;
    if (g_file_query_exists (gf, NULL) && !g_file_trash (gf, NULL, &trash_err)) {
      /* no trash available (e.g. other filesystem): delete instead */
      if (!g_file_delete (gf, NULL, error))
        ok = FALSE;
    }
  }

  /* Restore tracked content (and the old path of a rename) from HEAD */
  const char *restore = file->status == GDL_ST_RENAMED ? file->orig_path : (new_file ? NULL : file->path);
  if (ok && restore && head) {
    unstage_path (self, index, head, restore);
    char *p = (char *) restore;
    git_checkout_options co = GIT_CHECKOUT_OPTIONS_INIT;
    co.checkout_strategy = GIT_CHECKOUT_FORCE | GIT_CHECKOUT_DISABLE_PATHSPEC_MATCH;
    co.paths.strings = &p;
    co.paths.count = 1;
    if (git_checkout_head (self->repo, &co) < 0)
      ok = fail (error, GDL_GIT_ERROR_FAILED, "Could not restore the file");
  }
  git_index_free (index);
  git_commit_free (head);
  return ok;
}

gboolean
gdl_repo_add_ignore (GdlRepo *self, const char *pattern, GError **error)
{
  g_autofree char *path = g_build_filename (self->workdir, ".gitignore", NULL);
  g_autofree char *existing = NULL;
  gsize len = 0;
  g_file_get_contents (path, &existing, &len, NULL);
  if (existing) {
    g_auto (GStrv) lines = g_strsplit (existing, "\n", -1);
    if (g_strv_contains ((const char *const *) lines, pattern))
      return TRUE;
  }
  g_autoptr (GString) out = g_string_new (existing ? existing : "");
  if (out->len && out->str[out->len - 1] != '\n')
    g_string_append_c (out, '\n');
  g_string_append_printf (out, "%s\n", pattern);
  return g_file_set_contents (path, out->str, out->len, error);
}

/* ------------------------------------------------------------------ */
/* History                                                             */
/* ------------------------------------------------------------------ */

static GdlCommit *
commit_from (git_commit *c)
{
  GdlCommit *out = g_new0 (GdlCommit, 1);
  const git_signature *a = git_commit_author (c);
  out->hash = g_strdup (git_oid_tostr_s (git_commit_id (c)));
  g_strlcpy (out->short_hash, out->hash, sizeof out->short_hash);
  out->author = g_strdup (a->name);
  out->email = g_strdup (a->email);
  out->summary = g_strdup (git_commit_summary (c) ? git_commit_summary (c) : "");
  out->body = g_strdup (git_commit_body (c) ? git_commit_body (c) : "");
  g_strstrip (out->body);
  out->time = a->when.time;
  return out;
}

GPtrArray *
gdl_repo_history (GdlRepo *self, guint skip, guint limit)
{
  GPtrArray *out = g_ptr_array_new_with_free_func ((GDestroyNotify) gdl_commit_free);
  git_revwalk *walk = NULL;
  if (git_revwalk_new (&walk, self->repo) < 0)
    return out;
  git_revwalk_sorting (walk, GIT_SORT_TOPOLOGICAL | GIT_SORT_TIME);
  if (git_revwalk_push_head (walk) < 0) {  /* unborn branch: no history */
    git_revwalk_free (walk);
    return out;
  }
  git_oid oid;
  guint seen = 0;
  while (out->len < limit && git_revwalk_next (&oid, walk) == 0) {
    if (seen++ < skip)
      continue;
    git_commit *c = NULL;
    if (git_commit_lookup (&c, self->repo, &oid) == 0) {
      g_ptr_array_add (out, commit_from (c));
      git_commit_free (c);
    }
  }
  git_revwalk_free (walk);
  return out;
}

static git_commit *
lookup_commit (GdlRepo *self, const char *hash)
{
  git_oid oid;
  git_commit *c = NULL;
  if (git_oid_fromstrp (&oid, hash) < 0 || git_commit_lookup (&c, self->repo, &oid) < 0)
    return NULL;
  return c;
}

GdlCommit *
gdl_repo_commit_details (GdlRepo *self, const char *hash)
{
  git_commit *c = lookup_commit (self, hash);
  if (!c)
    return NULL;
  GdlCommit *out = commit_from (c);
  git_commit_free (c);
  return out;
}

/* Diff of a commit against its first parent (empty tree for the root commit) */
static git_diff *
commit_diff (GdlRepo *self, const char *hash, char **paths, size_t npaths)
{
  git_commit *c = lookup_commit (self, hash);
  if (!c)
    return NULL;
  git_tree *tree = NULL, *parent_tree = NULL;
  git_commit *parent = NULL;
  git_commit_tree (&tree, c);
  if (git_commit_parentcount (c) > 0 && git_commit_parent (&parent, c, 0) == 0)
    git_commit_tree (&parent_tree, parent);

  git_diff_options opts = GIT_DIFF_OPTIONS_INIT;
  if (npaths) {
    opts.flags |= GIT_DIFF_DISABLE_PATHSPEC_MATCH;
    opts.pathspec.strings = paths;
    opts.pathspec.count = npaths;
  }
  git_diff *diff = NULL;
  if (git_diff_tree_to_tree (&diff, self->repo, parent_tree, tree, &opts) == 0) {
    git_diff_find_options find = GIT_DIFF_FIND_OPTIONS_INIT;
    find.flags = GIT_DIFF_FIND_RENAMES;
    git_diff_find_similar (diff, &find);
  }
  git_tree_free (tree);
  git_tree_free (parent_tree);
  git_commit_free (parent);
  git_commit_free (c);
  return diff;
}

GPtrArray *
gdl_repo_commit_files (GdlRepo *self, const char *hash)
{
  GPtrArray *out = g_ptr_array_new_with_free_func ((GDestroyNotify) gdl_file_free);
  git_diff *diff = commit_diff (self, hash, NULL, 0);
  if (!diff)
    return out;
  size_t n = git_diff_num_deltas (diff);
  for (size_t i = 0; i < n; i++) {
    const git_diff_delta *d = git_diff_get_delta (diff, i);
    GdlFile *f = g_new0 (GdlFile, 1);
    f->path = g_strdup (d->new_file.path);
    switch (d->status) {
    case GIT_DELTA_ADDED:   f->status = GDL_ST_ADDED; break;
    case GIT_DELTA_DELETED: f->status = GDL_ST_DELETED; break;
    case GIT_DELTA_RENAMED: f->status = GDL_ST_RENAMED; f->orig_path = g_strdup (d->old_file.path); break;
    case GIT_DELTA_COPIED:  f->status = GDL_ST_COPIED; f->orig_path = g_strdup (d->old_file.path); break;
    default:                f->status = GDL_ST_MODIFIED; break;
    }
    g_ptr_array_add (out, f);
  }
  git_diff_free (diff);
  return out;
}

char *
gdl_repo_commit_file_diff (GdlRepo *self, const char *hash, const char *path, const char *orig_path)
{
  char *paths[2] = { (char *) path, (char *) orig_path };
  git_diff *diff = commit_diff (self, hash, paths, orig_path ? 2 : 1);
  if (!diff)
    return g_strdup ("");
  char *out = diff_to_string (diff);
  git_diff_free (diff);
  return out;
}

/* ------------------------------------------------------------------ */
/* Branches                                                            */
/* ------------------------------------------------------------------ */

gboolean
gdl_branch_name_valid (const char *name)
{
  ensure_libgit2 ();
  int valid = 0;
  if (!name || !*name || name[0] == '-' || strchr (name, ' '))
    return FALSE;
  git_branch_name_is_valid (&valid, name);
  return valid != 0;
}

static gint
compare_strings (gconstpointer a, gconstpointer b)
{
  return g_utf8_collate (*(const char **) a, *(const char **) b);
}

GPtrArray *
gdl_repo_branches (GdlRepo *self, gboolean remote)
{
  GPtrArray *out = g_ptr_array_new_with_free_func (g_free);
  git_branch_iterator *it = NULL;
  if (git_branch_iterator_new (&it, self->repo, remote ? GIT_BRANCH_REMOTE : GIT_BRANCH_LOCAL) < 0)
    return out;
  git_reference *ref;
  git_branch_t type;
  while (git_branch_next (&ref, &type, it) == 0) {
    const char *name = NULL;
    git_branch_name (&name, ref);
    if (name && !g_str_has_suffix (name, "/HEAD"))  /* skip origin/HEAD */
      g_ptr_array_add (out, g_strdup (name));
    git_reference_free (ref);
  }
  git_branch_iterator_free (it);
  g_ptr_array_sort (out, compare_strings);
  return out;
}

/* Safe checkout of `target` then point HEAD at `refname` */
static gboolean
switch_to (GdlRepo *self, git_commit *target, const char *refname, GError **error)
{
  git_checkout_options co = GIT_CHECKOUT_OPTIONS_INIT;
  co.checkout_strategy = GIT_CHECKOUT_SAFE;
  if (git_checkout_tree (self->repo, (git_object *) target, &co) < 0)
    return fail (error, GDL_GIT_ERROR_CONFLICT,
                 "Your changes would be overwritten. Commit or stash them first");
  if (git_repository_set_head (self->repo, refname) < 0)
    return fail (error, GDL_GIT_ERROR_FAILED, "Could not switch branch");
  return TRUE;
}

gboolean
gdl_repo_checkout_branch (GdlRepo *self, const char *name, GError **error)
{
  g_autofree char *refname = g_strdup_printf ("refs/heads/%s", name);
  git_object *obj = NULL;
  if (git_revparse_single (&obj, self->repo, refname) < 0)
    return fail (error, GDL_GIT_ERROR_FAILED, name);
  git_commit *target = NULL;
  git_object_peel ((git_object **) &target, obj, GIT_OBJECT_COMMIT);
  gboolean ok = switch_to (self, target, refname, error);
  git_commit_free (target);
  git_object_free (obj);
  return ok;
}

gboolean
gdl_repo_checkout_remote (GdlRepo *self, const char *remote_branch, GError **error)
{
  const char *slash = strchr (remote_branch, '/');
  const char *local = slash ? slash + 1 : remote_branch;
  git_reference *existing = NULL;
  if (git_branch_lookup (&existing, self->repo, local, GIT_BRANCH_LOCAL) == 0) {
    git_reference_free (existing);
    return gdl_repo_checkout_branch (self, local, error);
  }

  g_autofree char *refname = g_strdup_printf ("refs/remotes/%s", remote_branch);
  git_object *obj = NULL;
  git_commit *target = NULL;
  git_reference *branch = NULL;
  gboolean ok = FALSE;
  if (git_revparse_single (&obj, self->repo, refname) < 0 ||
      git_object_peel ((git_object **) &target, obj, GIT_OBJECT_COMMIT) < 0 ||
      git_branch_create (&branch, self->repo, local, target, 0) < 0) {
    fail (error, GDL_GIT_ERROR_FAILED, remote_branch);
  } else {
    git_branch_set_upstream (branch, remote_branch);
    g_autofree char *local_ref = g_strdup_printf ("refs/heads/%s", local);
    ok = switch_to (self, target, local_ref, error);
    if (!ok)
      git_branch_delete (branch);  /* don't leave a half-made branch behind */
  }
  git_reference_free (branch);
  git_commit_free (target);
  git_object_free (obj);
  return ok;
}

gboolean
gdl_repo_create_branch (GdlRepo *self, const char *name, GError **error)
{
  if (!gdl_branch_name_valid (name)) {
    g_set_error (error, GDL_GIT_ERROR, GDL_GIT_ERROR_INVALID_NAME, "'%s' is not a valid branch name.", name);
    return FALSE;
  }
  g_autofree char *refname = g_strdup_printf ("refs/heads/%s", name);
  git_commit *head = head_commit (self);
  if (!head) {
    /* unborn branch: just rename what HEAD points to */
    if (git_repository_set_head (self->repo, refname) < 0)
      return fail (error, GDL_GIT_ERROR_FAILED, "Could not create branch");
    return TRUE;
  }
  git_reference *ref = NULL;
  gboolean ok = git_branch_create (&ref, self->repo, name, head, 0) == 0;
  if (!ok)
    fail (error, GDL_GIT_ERROR_FAILED, "Could not create branch");
  else if (git_repository_set_head (self->repo, refname) < 0)   /* same tree: no checkout needed */
    ok = fail (error, GDL_GIT_ERROR_FAILED, "Could not switch branch");
  git_reference_free (ref);
  git_commit_free (head);
  return ok;
}

gboolean
gdl_repo_rename_branch (GdlRepo *self, const char *old_name, const char *new_name, GError **error)
{
  if (!gdl_branch_name_valid (new_name)) {
    g_set_error (error, GDL_GIT_ERROR, GDL_GIT_ERROR_INVALID_NAME, "'%s' is not a valid branch name.", new_name);
    return FALSE;
  }
  git_reference *ref = NULL, *moved = NULL;
  gboolean ok = git_branch_lookup (&ref, self->repo, old_name, GIT_BRANCH_LOCAL) == 0 &&
                git_branch_move (&moved, ref, new_name, 0) == 0;
  if (!ok)
    fail (error, GDL_GIT_ERROR_FAILED, "Could not rename branch");
  git_reference_free (ref);
  git_reference_free (moved);
  return ok;
}

gboolean
gdl_repo_delete_branch (GdlRepo *self, const char *name, gboolean force, GError **error)
{
  git_reference *ref = NULL;
  if (git_branch_lookup (&ref, self->repo, name, GIT_BRANCH_LOCAL) < 0)
    return fail (error, GDL_GIT_ERROR_FAILED, name);
  if (git_branch_is_head (ref) == 1) {
    git_reference_free (ref);
    g_set_error (error, GDL_GIT_ERROR, GDL_GIT_ERROR_FAILED,
                 "'%s' is the current branch. Switch to another branch first.", name);
    return FALSE;
  }
  if (!force) {
    /* like `git branch -d`: refuse when the tip is not contained in HEAD */
    git_oid head;
    const git_oid *tip = git_reference_target (ref);
    if (git_reference_name_to_id (&head, self->repo, "HEAD") == 0 && tip &&
        !git_oid_equal (&head, tip) && git_graph_descendant_of (self->repo, &head, tip) != 1) {
      git_reference_free (ref);
      g_set_error (error, GDL_GIT_ERROR, GDL_GIT_ERROR_NOT_MERGED,
                   "'%s' has commits that are not merged into the current branch.", name);
      return FALSE;
    }
  }
  gboolean ok = git_branch_delete (ref) == 0;
  if (!ok)
    fail (error, GDL_GIT_ERROR_FAILED, "Could not delete branch");
  git_reference_free (ref);
  return ok;
}

gboolean
gdl_repo_merge (GdlRepo *self, const char *branch, GError **error)
{
  git_annotated_commit *theirs = NULL;
  git_reference *their_ref = NULL;
  gboolean ok = FALSE;
  git_commit *head = head_commit (self);
  char *current = NULL, *message = NULL;  /* freed at `out` */

  if (git_branch_lookup (&their_ref, self->repo, branch, GIT_BRANCH_LOCAL) < 0 &&
      git_branch_lookup (&their_ref, self->repo, branch, GIT_BRANCH_REMOTE) < 0) {
    fail (error, GDL_GIT_ERROR_FAILED, branch);
    goto out;
  }
  if (git_annotated_commit_from_ref (&theirs, self->repo, their_ref) < 0) {
    fail (error, GDL_GIT_ERROR_FAILED, branch);
    goto out;
  }

  git_merge_analysis_t analysis;
  git_merge_preference_t pref;
  if (git_merge_analysis (&analysis, &pref, self->repo, (const git_annotated_commit **) &theirs, 1) < 0) {
    fail (error, GDL_GIT_ERROR_FAILED, "Merge failed");
    goto out;
  }
  if (analysis & GIT_MERGE_ANALYSIS_UP_TO_DATE) {
    ok = TRUE;
    goto out;
  }

  if ((analysis & GIT_MERGE_ANALYSIS_FASTFORWARD) && !(pref & GIT_MERGE_PREFERENCE_NO_FASTFORWARD)) {
    git_commit *target = NULL;
    git_reference *head_ref = NULL, *new_ref = NULL;
    if (git_commit_lookup (&target, self->repo, git_annotated_commit_id (theirs)) < 0) {
      fail (error, GDL_GIT_ERROR_FAILED, "Merge failed");
      goto out;
    }
    git_checkout_options co = GIT_CHECKOUT_OPTIONS_INIT;
    co.checkout_strategy = GIT_CHECKOUT_SAFE;
    if (git_checkout_tree (self->repo, (git_object *) target, &co) < 0)
      fail (error, GDL_GIT_ERROR_CONFLICT, "Your changes would be overwritten by the merge");
    else if (git_repository_head (&head_ref, self->repo) < 0 ||
             git_reference_set_target (&new_ref, head_ref, git_commit_id (target), "merge: fast-forward") < 0)
      fail (error, GDL_GIT_ERROR_FAILED, "Merge failed");
    else
      ok = TRUE;
    git_reference_free (new_ref);
    git_reference_free (head_ref);
    git_commit_free (target);
    goto out;
  }

  git_merge_options mo = GIT_MERGE_OPTIONS_INIT;
  git_checkout_options co = GIT_CHECKOUT_OPTIONS_INIT;
  co.checkout_strategy = GIT_CHECKOUT_SAFE | GIT_CHECKOUT_ALLOW_CONFLICTS;
  if (git_merge (self->repo, (const git_annotated_commit **) &theirs, 1, &mo, &co) < 0) {
    fail (error, GDL_GIT_ERROR_FAILED, "Merge failed");
    goto out;
  }

  git_index *index = NULL;
  git_repository_index (&index, self->repo);
  if (git_index_has_conflicts (index)) {
    git_index_free (index);
    g_set_error_literal (error, GDL_GIT_ERROR, GDL_GIT_ERROR_CONFLICT,
                         "There are conflicts. Resolve them, then commit the merge.");
    goto out;
  }

  /* clean merge: commit it right away, like `git merge` does */
  git_oid tree_oid, commit_oid;
  git_tree *tree = NULL;
  git_commit *other = NULL;
  git_signature *sig = NULL;
  current = gdl_repo_branch (self);
  message = g_strdup_printf ("Merge branch '%s' into %s\n", branch, current);
  if (git_signature_default (&sig, self->repo) < 0) {
    g_set_error_literal (error, GDL_GIT_ERROR, GDL_GIT_ERROR_NO_IDENTITY,
                         "Set your name and email first (Preferences → Git).");
  } else if (git_index_write_tree (&tree_oid, index) < 0 || git_tree_lookup (&tree, self->repo, &tree_oid) < 0 ||
             git_commit_lookup (&other, self->repo, git_annotated_commit_id (theirs)) < 0) {
    fail (error, GDL_GIT_ERROR_FAILED, "Merge failed");
  } else {
    const git_commit *parents[2] = { head, other };
    if (git_commit_create (&commit_oid, self->repo, "HEAD", sig, sig, NULL, message, tree, 2, parents) < 0)
      fail (error, GDL_GIT_ERROR_FAILED, "Merge commit failed");
    else {
      git_repository_state_cleanup (self->repo);
      ok = TRUE;
    }
  }
  git_signature_free (sig);
  git_commit_free (other);
  git_tree_free (tree);
  git_index_free (index);

out:
  g_free (current);
  g_free (message);
  git_annotated_commit_free (theirs);
  git_reference_free (their_ref);
  git_commit_free (head);
  return ok;
}

gboolean
gdl_repo_abort_merge (GdlRepo *self, GError **error)
{
  git_commit *head = head_commit (self);
  gboolean ok = head && git_reset (self->repo, (git_object *) head, GIT_RESET_HARD, NULL) == 0;
  if (!ok)
    fail (error, GDL_GIT_ERROR_FAILED, "Could not abort the merge");
  else
    git_repository_state_cleanup (self->repo);
  git_commit_free (head);
  return ok;
}

/* ------------------------------------------------------------------ */
/* Remotes & sync                                                      */
/* ------------------------------------------------------------------ */

GPtrArray *
gdl_repo_remotes (GdlRepo *self)
{
  GPtrArray *out = g_ptr_array_new_with_free_func (g_free);
  git_strarray names = { 0 };
  if (git_remote_list (&names, self->repo) == 0) {
    for (size_t i = 0; i < names.count; i++)
      g_ptr_array_add (out, g_strdup (names.strings[i]));
    git_strarray_dispose (&names);
  }
  return out;
}

char *
gdl_repo_remote_url (GdlRepo *self, const char *remote)
{
  git_remote *r = NULL;
  if (git_remote_lookup (&r, self->repo, remote) < 0)
    return NULL;
  char *url = g_strdup (git_remote_url (r));
  git_remote_free (r);
  return url;
}

gboolean
gdl_repo_add_remote (GdlRepo *self, const char *name, const char *url, GError **error)
{
  git_remote *r = NULL;
  if (git_remote_create (&r, self->repo, name, url) < 0)
    return fail (error, GDL_GIT_ERROR_FAILED, "Could not add remote");
  git_remote_free (r);
  return TRUE;
}

void
gdl_repo_sync_status (GdlRepo *self, GdlSync *out)
{
  memset (out, 0, sizeof *out);
  git_reference *head = NULL, *upstream = NULL;
  if (git_repository_head (&head, self->repo) < 0)
    return;
  if (git_branch_upstream (&upstream, head) == 0) {
    out->has_upstream = TRUE;
    out->upstream = g_strdup (git_reference_shorthand (upstream));
    size_t ahead = 0, behind = 0;
    if (git_graph_ahead_behind (&ahead, &behind, self->repo, git_reference_target (head),
                                git_reference_target (upstream)) == 0) {
      out->ahead = (int) ahead;
      out->behind = (int) behind;
    }
  }
  git_reference_free (upstream);
  git_reference_free (head);
}

gint64
gdl_repo_last_fetch (GdlRepo *self)
{
  g_autofree char *path = g_build_filename (git_repository_path (self->repo), "FETCH_HEAD", NULL);
  struct stat st;
  return stat (path, &st) == 0 ? (gint64) st.st_mtime : 0;
}

char *
gdl_repo_config_string (GdlRepo *self, const char *key)
{
  git_config *cfg = NULL;
  git_buf buf = GIT_BUF_INIT;
  char *out = NULL;
  if (git_repository_config_snapshot (&cfg, self->repo) == 0 && git_config_get_string_buf (&buf, cfg, key) == 0)
    out = g_strndup (buf.ptr, buf.size);
  git_buf_dispose (&buf);
  git_config_free (cfg);
  return out;
}

/* ------------------------------------------------------------------ */
/* Stash                                                               */
/* ------------------------------------------------------------------ */

gboolean
gdl_repo_stash_all (GdlRepo *self, GError **error)
{
  git_signature *sig = NULL;
  if (git_signature_default (&sig, self->repo) < 0 &&
      git_signature_now (&sig, "Git Desktop", "git-desktop@localhost") < 0)
    return fail (error, GDL_GIT_ERROR_FAILED, "Could not stash");
  g_autofree char *branch = gdl_repo_branch (self);
  g_autofree char *message = g_strdup_printf ("Git Desktop: %s", branch);
  git_oid oid;
  int rc = git_stash_save (&oid, self->repo, sig, message, GIT_STASH_INCLUDE_UNTRACKED);
  git_signature_free (sig);
  if (rc < 0)
    return fail (error, GDL_GIT_ERROR_FAILED, "Could not stash changes");
  return TRUE;
}

typedef struct {
  const char *suffix;
  int         found;
} StashFind;

static int
stash_find_cb (size_t index, const char *message, const git_oid *id, void *payload)
{
  StashFind *f = payload;
  if (message && g_str_has_suffix (message, f->suffix)) {
    f->found = (int) index;
    return 1;  /* stop */
  }
  return 0;
}

int
gdl_repo_find_stash (GdlRepo *self, const char *branch)
{
  g_autofree char *suffix = g_strdup_printf ("Git Desktop: %s", branch);
  StashFind f = { suffix, -1 };
  git_stash_foreach (self->repo, stash_find_cb, &f);
  return f.found;
}

gboolean
gdl_repo_stash_pop (GdlRepo *self, int index, GError **error)
{
  git_stash_apply_options opts = GIT_STASH_APPLY_OPTIONS_INIT;
  if (git_stash_pop (self->repo, (size_t) index, &opts) < 0)
    return fail (error, GDL_GIT_ERROR_CONFLICT, "Could not restore the stash");
  return TRUE;
}

gboolean
gdl_repo_stash_drop (GdlRepo *self, int index, GError **error)
{
  if (git_stash_drop (self->repo, (size_t) index) < 0)
    return fail (error, GDL_GIT_ERROR_FAILED, "Could not discard the stash");
  return TRUE;
}

/* ------------------------------------------------------------------ */
/* Global identity                                                     */
/* ------------------------------------------------------------------ */

void
gdl_global_identity (char **name, char **email)
{
  ensure_libgit2 ();
  *name = *email = NULL;
  git_config *cfg = NULL, *snap = NULL;
  if (git_config_open_default (&cfg) < 0)
    return;
  if (git_config_snapshot (&snap, cfg) == 0) {
    const char *v = NULL;
    if (git_config_get_string (&v, snap, "user.name") == 0)
      *name = g_strdup (v);
    if (git_config_get_string (&v, snap, "user.email") == 0)
      *email = g_strdup (v);
    git_config_free (snap);
  }
  git_config_free (cfg);
}

gboolean
gdl_set_global_identity (const char *name, const char *email, GError **error)
{
  ensure_libgit2 ();
  git_config *cfg = NULL, *global = NULL;
  gboolean ok = git_config_open_default (&cfg) == 0 &&
                git_config_open_level (&global, cfg, GIT_CONFIG_LEVEL_GLOBAL) == 0 &&
                git_config_set_string (global, "user.name", name) == 0 &&
                git_config_set_string (global, "user.email", email) == 0;
  if (!ok)
    fail (error, GDL_GIT_ERROR_FAILED, "Could not save your name and email");
  git_config_free (global);
  git_config_free (cfg);
  return ok;
}
