/* Network git operations: run the git CLI asynchronously (fetch/pull/push/clone).
 *
 * Like GitHub Desktop, this uses git itself, so SSH keys, ~/.gitconfig and
 * credential helpers work as in a terminal. When signed in to GitHub, the
 * token is handed to git through a credential helper that reads it from the
 * environment — it never appears on a command line.
 */
#pragma once

#include <gio/gio.h>

G_BEGIN_DECLS

/* ok: git exited with 0. output: git's merged stdout+stderr. */
typedef void (*GdlNetCallback) (gboolean ok, const char *output, gpointer user_data);

void gdl_net_run   (const char *cwd, const char *const *args, const char *token,
                    GCancellable *cancellable, GdlNetCallback callback, gpointer user_data);

void gdl_net_fetch (const char *repo, const char *token, GdlNetCallback cb, gpointer user_data);
/* merge_by_default: add --no-rebase when the user has no pull.rebase/pull.ff config */
void gdl_net_pull  (const char *repo, const char *token, gboolean merge_by_default,
                    GdlNetCallback cb, gpointer user_data);
/* branch != NULL: first push of a branch (git push --set-upstream origin <branch>) */
void gdl_net_push  (const char *repo, const char *token, const char *branch,
                    GdlNetCallback cb, gpointer user_data);
void gdl_net_clone (const char *url, const char *dest, const char *token,
                    GdlNetCallback cb, gpointer user_data);

/* Adds advice to auth failures ("could not read Username" → how to sign in). */
char *gdl_net_explain_error (const char *output);

G_END_DECLS
