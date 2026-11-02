/* Unit tests for the git layer and the diff parser.
 *
 * Every test works in a fresh temporary repository. HOME and the git config
 * point into a sandbox, so the user's real ~/.gitconfig is never touched.
 */
#include "diffparse.h"
#include "git.h"
#include "net.h"
#include "util.h"

#include <gio/gio.h>
#include <glib/gstdio.h>
#include <stdlib.h>
#include <string.h>

static char *sandbox;

typedef struct {
  char    *dir;
  GdlRepo *repo;
} Fixture;

static void
write_file (Fixture *fx, const char *rel, const char *content)
{
  g_autofree char *path = g_build_filename (fx->dir, rel, NULL);
  g_autofree char *parent = g_path_get_dirname (path);
  g_mkdir_with_parents (parent, 0755);
  g_assert_true (g_file_set_contents (path, content, -1, NULL));
}

static void
sh (const char *cwd, const char *cmd)
{
  g_autofree char *full = g_strdup_printf ("cd '%s' && %s >/dev/null 2>&1", cwd, cmd);
  g_assert_cmpint (system (full), ==, 0);
}

static GPtrArray *
status (Fixture *fx)
{
  g_autoptr (GError) error = NULL;
  GPtrArray *files = gdl_repo_status (fx->repo, &error);
  g_assert_no_error (error);
  return files;
}

static GdlFile *
find (GPtrArray *files, const char *path)
{
  for (guint i = 0; i < files->len; i++) {
    GdlFile *f = g_ptr_array_index (files, i);
    if (g_str_equal (f->path, path))
      return f;
  }
  return NULL;
}

/* Commit every changed file */
static void
commit_all (Fixture *fx, const char *summary)
{
  g_autoptr (GPtrArray) files = status (fx);
  g_autoptr (GHashTable) checked = g_hash_table_new (g_str_hash, g_str_equal);
  for (guint i = 0; i < files->len; i++)
    g_hash_table_add (checked, ((GdlFile *) g_ptr_array_index (files, i))->path);
  g_autoptr (GError) error = NULL;
  g_assert_true (gdl_repo_commit (fx->repo, files, checked, summary, NULL, &error));
  g_assert_no_error (error);
}

static void
setup (Fixture *fx, gconstpointer data)
{
  g_autofree char *tmpl = g_build_filename (sandbox, "repo-XXXXXX", NULL);
  fx->dir = g_mkdtemp (g_steal_pointer (&tmpl));
  g_autoptr (GError) error = NULL;
  g_assert_true (gdl_repo_init (fx->dir, &error));
  fx->repo = gdl_repo_open (fx->dir, &error);
  g_assert_no_error (error);
}

static void
teardown (Fixture *fx, gconstpointer data)
{
  gdl_repo_free (fx->repo);
  g_free (fx->dir);
}

/* ------------------------------------------------------------------ */

static void
test_status_turkish_and_new (Fixture *fx, gconstpointer d)
{
  write_file (fx, "özet şablonu.txt", "x\n");
  g_autoptr (GPtrArray) files = status (fx);
  g_assert_cmpuint (files->len, ==, 1);
  GdlFile *f = g_ptr_array_index (files, 0);
  g_assert_cmpstr (f->path, ==, "özet şablonu.txt");
  g_assert_cmpint (f->status, ==, GDL_ST_NEW);
  g_assert_false (f->staged);
}

static void
test_commit_only_checked (Fixture *fx, gconstpointer d)
{
  write_file (fx, "base.txt", "1\n");
  commit_all (fx, "ilk");
  write_file (fx, "seç.txt", "a\n");
  write_file (fx, "atla.txt", "b\n");
  sh (fx->dir, "git add atla.txt");  /* staged outside the app, but unchecked in the UI */

  g_autoptr (GPtrArray) files = status (fx);
  g_autoptr (GHashTable) checked = g_hash_table_new (g_str_hash, g_str_equal);
  g_hash_table_add (checked, (gpointer) "seç.txt");
  g_autoptr (GError) error = NULL;
  g_assert_true (gdl_repo_commit (fx->repo, files, checked, "Sadece seç", "Açıklama", &error));
  g_assert_no_error (error);

  g_autoptr (GPtrArray) after = status (fx);
  g_assert_cmpuint (after->len, ==, 1);
  GdlFile *left = g_ptr_array_index (after, 0);
  g_assert_cmpstr (left->path, ==, "atla.txt");
  g_assert_false (left->staged);  /* unchecked files are not committed, and unstaged */

  g_autoptr (GPtrArray) hist = gdl_repo_history (fx->repo, 0, 1);
  GdlCommit *c = g_ptr_array_index (hist, 0);
  g_assert_cmpstr (c->summary, ==, "Sadece seç");
  g_assert_cmpstr (c->body, ==, "Açıklama");
}

static void
test_commit_requires_summary_and_changes (Fixture *fx, gconstpointer d)
{
  write_file (fx, "a.txt", "1\n");
  commit_all (fx, "ilk");
  g_autoptr (GPtrArray) files = status (fx);
  g_autoptr (GHashTable) checked = g_hash_table_new (g_str_hash, g_str_equal);
  g_autoptr (GError) e1 = NULL, e2 = NULL;
  g_assert_false (gdl_repo_commit (fx->repo, files, checked, "   ", NULL, &e1));
  g_assert_false (gdl_repo_commit (fx->repo, files, checked, "boş", NULL, &e2));
  g_assert_error (e2, GDL_GIT_ERROR, GDL_GIT_ERROR_NOTHING_TO_COMMIT);
}

static void
test_undo_root_and_normal_commit (Fixture *fx, gconstpointer d)
{
  write_file (fx, "a.txt", "1\n");
  commit_all (fx, "ilk");
  g_autofree char *summary = NULL, *body = NULL;
  g_autoptr (GError) error = NULL;
  g_assert_true (gdl_repo_undo_commit (fx->repo, &summary, &body, &error));
  g_assert_cmpstr (summary, ==, "ilk");
  g_assert_false (gdl_repo_has_commits (fx->repo));
  g_autoptr (GPtrArray) files = status (fx);
  g_assert_true (((GdlFile *) g_ptr_array_index (files, 0))->staged);  /* changes kept */

  commit_all (fx, "tekrar");
  write_file (fx, "a.txt", "2\n");
  commit_all (fx, "ikinci");
  g_assert_true (gdl_repo_undo_commit (fx->repo, NULL, NULL, &error));
  g_autoptr (GPtrArray) hist = gdl_repo_history (fx->repo, 0, 10);
  g_assert_cmpuint (hist->len, ==, 1);
}

static void
test_rename_and_commit_files (Fixture *fx, gconstpointer d)
{
  write_file (fx, "eski.txt", "satır 1\nsatır 2\nsatır 3\n");
  commit_all (fx, "ilk");
  sh (fx->dir, "git mv eski.txt yeni.txt");
  g_autoptr (GPtrArray) files = status (fx);
  g_assert_cmpuint (files->len, ==, 1);
  GdlFile *f = g_ptr_array_index (files, 0);
  g_assert_cmpint (f->status, ==, GDL_ST_RENAMED);
  g_assert_cmpstr (f->orig_path, ==, "eski.txt");
  commit_all (fx, "taşı");

  g_autofree char *head = gdl_repo_head_hash (fx->repo);
  g_autoptr (GPtrArray) cf = gdl_repo_commit_files (fx->repo, head);
  g_assert_cmpuint (cf->len, ==, 1);
  GdlFile *r = g_ptr_array_index (cf, 0);
  g_assert_cmpint (r->status, ==, GDL_ST_RENAMED);
  g_assert_cmpstr (r->path, ==, "yeni.txt");
}

static void
test_diffs (Fixture *fx, gconstpointer d)
{
  write_file (fx, "a.txt", "bir\niki\nüç\n");
  commit_all (fx, "ilk");
  write_file (fx, "a.txt", "bir\nIKI\nüç\n");
  write_file (fx, "yeni.txt", "merhaba\n");
  g_autoptr (GPtrArray) files = status (fx);

  g_autofree char *mod = gdl_repo_file_diff (fx->repo, find (files, "a.txt"));
  g_autoptr (GdlDiff) dm = gdl_diff_parse (mod, 0);
  g_assert_false (dm->binary);
  g_assert_cmpuint (dm->rows->len, ==, 5);  /* hunk, ctx, del, add, ctx */
  GdlDiffRow *del = g_ptr_array_index (dm->rows, 2), *add = g_ptr_array_index (dm->rows, 3);
  g_assert_cmpint (del->kind, ==, GDL_ROW_DEL);
  g_assert_cmpint (del->old_no, ==, 2);
  g_assert_cmpint (add->kind, ==, GDL_ROW_ADD);
  g_assert_cmpint (add->new_no, ==, 2);

  g_autofree char *untracked = gdl_repo_file_diff (fx->repo, find (files, "yeni.txt"));
  g_assert_nonnull (strstr (untracked, "+merhaba"));

  g_autofree char *bin_path = g_build_filename (fx->dir, "resim.bin", NULL);
  const char bytes[] = { 0, 1, 2, 'P', 'N', 'G', 0, 9 };
  g_assert_true (g_file_set_contents (bin_path, bytes, sizeof bytes, NULL));
  g_autoptr (GPtrArray) files2 = status (fx);
  g_autofree char *bin = gdl_repo_file_diff (fx->repo, find (files2, "resim.bin"));
  g_autoptr (GdlDiff) db = gdl_diff_parse (bin, 0);
  g_assert_true (db->binary);
}

static void
test_branches_and_safe_checkout (Fixture *fx, gconstpointer d)
{
  write_file (fx, "a.txt", "1\n");
  commit_all (fx, "ilk");
  g_autofree char *main_branch = gdl_repo_branch (fx->repo);
  g_assert_false (gdl_branch_name_valid ("-f"));
  g_assert_false (gdl_branch_name_valid ("a..b"));
  g_assert_false (gdl_branch_name_valid ("boşluk var"));
  g_assert_true (gdl_branch_name_valid ("feature/özellik"));

  g_autoptr (GError) error = NULL;
  g_assert_true (gdl_repo_create_branch (fx->repo, "feature/özellik", &error));
  g_autofree char *b = gdl_repo_branch (fx->repo);
  g_assert_cmpstr (b, ==, "feature/özellik");
  write_file (fx, "a.txt", "dal\n");
  commit_all (fx, "dalda");

  /* an uncommitted change to a file that differs between branches blocks the switch */
  write_file (fx, "a.txt", "kirli\n");
  g_autoptr (GError) blocked = NULL;
  g_assert_false (gdl_repo_checkout_branch (fx->repo, main_branch, &blocked));
  g_assert_error (blocked, GDL_GIT_ERROR, GDL_GIT_ERROR_CONFLICT);
  write_file (fx, "a.txt", "dal\n");

  g_assert_true (gdl_repo_checkout_branch (fx->repo, main_branch, &error));
  g_assert_no_error (error);
  g_autofree char *now = gdl_repo_branch (fx->repo);
  g_assert_cmpstr (now, ==, main_branch);

  /* unmerged branch: refused unless forced */
  g_autoptr (GError) unmerged = NULL;
  g_assert_false (gdl_repo_delete_branch (fx->repo, "feature/özellik", FALSE, &unmerged));
  g_assert_error (unmerged, GDL_GIT_ERROR, GDL_GIT_ERROR_NOT_MERGED);
  g_assert_true (gdl_repo_delete_branch (fx->repo, "feature/özellik", TRUE, &error));
}

static void
test_merge_conflict_and_abort (Fixture *fx, gconstpointer d)
{
  write_file (fx, "a.txt", "taban\n");
  commit_all (fx, "ilk");
  g_autofree char *main_branch = gdl_repo_branch (fx->repo);
  g_autoptr (GError) error = NULL;
  g_assert_true (gdl_repo_create_branch (fx->repo, "dal", &error));
  write_file (fx, "a.txt", "dal\n");
  commit_all (fx, "dal tarafı");
  g_assert_true (gdl_repo_checkout_branch (fx->repo, main_branch, &error));
  write_file (fx, "a.txt", "ana\n");
  commit_all (fx, "ana tarafı");

  g_autoptr (GError) conflict = NULL;
  g_assert_false (gdl_repo_merge (fx->repo, "dal", &conflict));
  g_assert_error (conflict, GDL_GIT_ERROR, GDL_GIT_ERROR_CONFLICT);
  g_assert_true (gdl_repo_is_merging (fx->repo));
  g_autoptr (GPtrArray) files = status (fx);
  g_assert_cmpint (((GdlFile *) g_ptr_array_index (files, 0))->status, ==, GDL_ST_CONFLICTED);

  g_assert_true (gdl_repo_abort_merge (fx->repo, &error));
  g_assert_false (gdl_repo_is_merging (fx->repo));
  g_autoptr (GPtrArray) clean = status (fx);
  g_assert_cmpuint (clean->len, ==, 0);
}

static void
test_merge_clean_creates_commit (Fixture *fx, gconstpointer d)
{
  write_file (fx, "a.txt", "a\n");
  commit_all (fx, "ilk");
  g_autofree char *main_branch = gdl_repo_branch (fx->repo);
  g_autoptr (GError) error = NULL;
  gdl_repo_create_branch (fx->repo, "dal", &error);
  write_file (fx, "b.txt", "b\n");
  commit_all (fx, "dal");
  gdl_repo_checkout_branch (fx->repo, main_branch, &error);
  write_file (fx, "c.txt", "c\n");
  commit_all (fx, "ana");
  g_assert_true (gdl_repo_merge (fx->repo, "dal", &error));
  g_assert_no_error (error);
  g_autoptr (GPtrArray) hist = gdl_repo_history (fx->repo, 0, 1);
  g_assert_true (g_str_has_prefix (((GdlCommit *) g_ptr_array_index (hist, 0))->summary, "Merge branch 'dal'"));
  g_assert_false (gdl_repo_is_merging (fx->repo));
}

static void
test_stash_tagged_with_branch (Fixture *fx, gconstpointer d)
{
  write_file (fx, "a.txt", "1\n");
  commit_all (fx, "ilk");
  write_file (fx, "wip.txt", "yarım\n");
  g_autofree char *branch = gdl_repo_branch (fx->repo);
  g_autoptr (GError) error = NULL;
  g_assert_true (gdl_repo_stash_all (fx->repo, &error));
  g_autoptr (GPtrArray) empty = status (fx);
  g_assert_cmpuint (empty->len, ==, 0);
  int idx = gdl_repo_find_stash (fx->repo, branch);
  g_assert_cmpint (idx, ==, 0);
  g_assert_cmpint (gdl_repo_find_stash (fx->repo, "başka"), ==, -1);
  g_assert_true (gdl_repo_stash_pop (fx->repo, idx, &error));
  g_autoptr (GPtrArray) back = status (fx);
  g_assert_nonnull (find (back, "wip.txt"));
}

static void
test_discard_and_ignore (Fixture *fx, gconstpointer d)
{
  write_file (fx, "a.txt", "orijinal\n");
  commit_all (fx, "ilk");
  write_file (fx, "a.txt", "bozuk\n");
  write_file (fx, "çöp.log", "x\n");
  g_autoptr (GPtrArray) files = status (fx);
  g_autoptr (GError) error = NULL;
  g_assert_true (gdl_repo_discard (fx->repo, find (files, "a.txt"), &error));
  g_assert_true (gdl_repo_discard (fx->repo, find (files, "çöp.log"), &error));
  g_autoptr (GPtrArray) after = status (fx);
  g_assert_cmpuint (after->len, ==, 0);
  g_autofree char *path = g_build_filename (fx->dir, "a.txt", NULL);
  g_autofree char *content = NULL;
  g_file_get_contents (path, &content, NULL, NULL);
  g_assert_cmpstr (content, ==, "orijinal\n");

  g_assert_true (gdl_repo_add_ignore (fx->repo, "*.log", &error));
  g_assert_true (gdl_repo_add_ignore (fx->repo, "*.log", &error));  /* not duplicated */
  g_autofree char *ign_path = g_build_filename (fx->dir, ".gitignore", NULL);
  g_autofree char *ign = NULL;
  g_file_get_contents (ign_path, &ign, NULL, NULL);
  g_assert_cmpstr (ign, ==, "*.log\n");
}

/* ---- network: publish, divergent pull (local bare remote) ---- */

typedef struct {
  GMainLoop *loop;
  gboolean   ok;
  char      *output;
} Wait;

static void
on_net_done (gboolean ok, const char *output, gpointer data)
{
  Wait *w = data;
  w->ok = ok;
  w->output = g_strdup (output);
  g_main_loop_quit (w->loop);
}

static gboolean
wait_net (Wait *w)
{
  g_main_loop_run (w->loop);
  if (!w->ok)
    g_printerr ("git output: %s\n", w->output);
  gboolean ok = w->ok;
  g_clear_pointer (&w->output, g_free);
  return ok;
}

static void
test_publish_and_divergent_pull (Fixture *fx, gconstpointer d)
{
  g_autofree char *tmpl = g_build_filename (sandbox, "remote-XXXXXX", NULL);
  g_autofree char *remote = g_mkdtemp (g_steal_pointer (&tmpl));
  sh (remote, "git init -q --bare");
  write_file (fx, "a.txt", "a\n");
  commit_all (fx, "ilk");
  g_autoptr (GError) error = NULL;
  g_assert_true (gdl_repo_add_remote (fx->repo, "origin", remote, &error));
  g_autofree char *branch = gdl_repo_branch (fx->repo);

  Wait w = { g_main_loop_new (NULL, FALSE), FALSE, NULL };
  gdl_net_push (fx->dir, NULL, branch, on_net_done, &w);  /* publish */
  g_assert_true (wait_net (&w));
  GdlSync s;
  gdl_repo_sync_status (fx->repo, &s);
  g_assert_true (s.has_upstream);
  gdl_sync_clear (&s);

  /* someone else pushes; we commit locally -> diverged */
  g_autofree char *other_tmpl = g_build_filename (sandbox, "other-XXXXXX", NULL);
  g_autofree char *other = g_mkdtemp (g_steal_pointer (&other_tmpl));
  g_autofree char *clone_cmd = g_strdup_printf ("git clone -q '%s' . && echo b > b.txt && git add . && "
                                                "git commit -qm uzak && git push -q", remote);
  sh (other, clone_cmd);
  write_file (fx, "c.txt", "c\n");
  commit_all (fx, "yerel");

  gdl_net_fetch (fx->dir, NULL, on_net_done, &w);
  g_assert_true (wait_net (&w));
  gdl_repo_sync_status (fx->repo, &s);
  g_assert_cmpint (s.ahead, ==, 1);
  g_assert_cmpint (s.behind, ==, 1);
  gdl_sync_clear (&s);
  g_assert_cmpint (gdl_repo_last_fetch (fx->repo), >, 0);

  gdl_net_pull (fx->dir, NULL, TRUE, on_net_done, &w);  /* --no-rebase: merges */
  g_assert_true (wait_net (&w));
  gdl_net_push (fx->dir, NULL, NULL, on_net_done, &w);
  g_assert_true (wait_net (&w));
  gdl_repo_sync_status (fx->repo, &s);
  g_assert_cmpint (s.ahead, ==, 0);
  g_assert_cmpint (s.behind, ==, 0);
  gdl_sync_clear (&s);
  g_main_loop_unref (w.loop);
}

static void
test_auth_failure_is_explained (void)
{
  g_autofree char *msg = gdl_net_explain_error ("fatal: could not read Username for 'https://github.com'");
  g_assert_nonnull (strstr (msg, "Sign in"));
}

static void
test_diff_parser_numbers (void)
{
  const char *text = "diff --git a/f b/f\nindex 1..2 100644\n--- a/f\n+++ b/f\n"
                     "@@ -10,3 +10,3 @@ ctx\n a\n-b\n+B\n c\n";
  g_autoptr (GdlDiff) d = gdl_diff_parse (text, 0);
  g_assert_cmpuint (d->rows->len, ==, 5);
  GdlDiffRow *last = g_ptr_array_index (d->rows, 4);
  g_assert_cmpint (last->old_no, ==, 12);
  g_assert_cmpint (last->new_no, ==, 12);
  g_assert_cmpint (d->max_line, ==, 12);
}

static void
test_util (void)
{
  g_autofree char *next = gdl_link_next ("<https://api.github.com/user/repos?page=2>; rel=\"next\", "
                                         "<https://api.github.com/user/repos?page=9>; rel=\"last\"");
  g_assert_cmpstr (next, ==, "https://api.github.com/user/repos?page=2");
  g_assert_null (gdl_link_next ("<https://x?page=1>; rel=\"prev\""));

  g_autofree char *s1 = gdl_github_slug ("https://github.com/kefy266/Git-Desktop-For-Linux.git");
  g_autofree char *s2 = gdl_github_slug ("git@github.com:kefy266/dotfiles.git");
  g_assert_cmpstr (s1, ==, "kefy266/Git-Desktop-For-Linux");
  g_assert_cmpstr (s2, ==, "kefy266/dotfiles");
  g_assert_null (gdl_github_slug ("https://gitlab.com/a/b.git"));

  g_autofree char *d1 = gdl_clone_dir_name ("https://github.com/desktop/desktop.git");
  g_autofree char *d2 = gdl_clone_dir_name ("git@github.com:me/okul-projesi.git/");
  g_assert_cmpstr (d1, ==, "desktop");
  g_assert_cmpstr (d2, ==, "okul-projesi");

  g_autofree char *u1 = gdl_expand_clone_url ("desktop/desktop");
  g_autofree char *u2 = gdl_expand_clone_url ("git@github.com:me/x.git");
  g_assert_cmpstr (u1, ==, "https://github.com/desktop/desktop.git");
  g_assert_cmpstr (u2, ==, "git@github.com:me/x.git");

  g_autofree char *ago = gdl_time_ago (g_get_real_time () / G_USEC_PER_SEC - 2 * 3600 - 5);
  g_assert_cmpstr (ago, ==, "2 hours ago");
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);

  sandbox = g_dir_make_tmp ("gdl-tests-XXXXXX", NULL);
  g_setenv ("HOME", sandbox, TRUE);
  g_setenv ("XDG_CONFIG_HOME", sandbox, TRUE);
  g_autofree char *gitconfig = g_build_filename (sandbox, ".gitconfig", NULL);
  g_file_set_contents (gitconfig, "[user]\n\tname = Test\n\temail = test@example.com\n"
                                  "[init]\n\tdefaultBranch = main\n", -1, NULL);
  g_setenv ("GIT_CONFIG_GLOBAL", gitconfig, TRUE);
  g_setenv ("GIT_CONFIG_NOSYSTEM", "1", TRUE);

#define REPO_TEST(name, fn) g_test_add (name, Fixture, NULL, setup, fn, teardown)
  REPO_TEST ("/status/turkish-and-new", test_status_turkish_and_new);
  REPO_TEST ("/commit/only-checked", test_commit_only_checked);
  REPO_TEST ("/commit/requires-summary-and-changes", test_commit_requires_summary_and_changes);
  REPO_TEST ("/commit/undo", test_undo_root_and_normal_commit);
  REPO_TEST ("/history/rename", test_rename_and_commit_files);
  REPO_TEST ("/diff/workdir", test_diffs);
  REPO_TEST ("/branch/create-checkout-delete", test_branches_and_safe_checkout);
  REPO_TEST ("/merge/conflict-abort", test_merge_conflict_and_abort);
  REPO_TEST ("/merge/clean", test_merge_clean_creates_commit);
  REPO_TEST ("/stash/branch-tag", test_stash_tagged_with_branch);
  REPO_TEST ("/discard/and-ignore", test_discard_and_ignore);
  REPO_TEST ("/net/publish-pull", test_publish_and_divergent_pull);
  g_test_add_func ("/net/explain-auth", test_auth_failure_is_explained);
  g_test_add_func ("/diff/parser", test_diff_parser_numbers);
  g_test_add_func ("/util/all", test_util);

  int rc = g_test_run ();
  g_autofree char *rm = g_strdup_printf ("rm -rf '%s'", sandbox);
  if (system (rm) != 0)
    g_printerr ("could not remove %s\n", sandbox);
  return rc;
}
