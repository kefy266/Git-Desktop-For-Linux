#include "net.h"

#include <string.h>

#define TOKEN_ENV "GDL_GITHUB_TOKEN"

/* Answers git's credential requests for https://github.com with the token from the environment */
static const char TOKEN_HELPER[] =
  "credential.https://github.com.helper=!f() { test \"$1\" = get || exit 0; "
  "echo username=x-access-token; echo \"password=$" TOKEN_ENV "\"; }; f";

typedef struct {
  GdlNetCallback callback;
  gpointer       user_data;
} NetJob;

static void
on_communicated (GObject *source, GAsyncResult *res, gpointer data)
{
  NetJob *job = data;
  GSubprocess *proc = G_SUBPROCESS (source);
  g_autofree char *out = NULL;
  g_autoptr (GError) error = NULL;
  gboolean ok = g_subprocess_communicate_utf8_finish (proc, res, &out, NULL, &error) &&
                g_subprocess_get_successful (proc);
  const char *text = out && *out ? out : (error ? error->message : "");
  if (job->callback)
    job->callback (ok, g_strstrip ((char *) text), job->user_data);
  g_object_unref (proc);
  g_free (job);
}

void
gdl_net_run (const char *cwd, const char *const *args, const char *token,
             GCancellable *cancellable, GdlNetCallback callback, gpointer user_data)
{
  g_autoptr (GSubprocessLauncher) launcher =
    g_subprocess_launcher_new (G_SUBPROCESS_FLAGS_STDIN_PIPE | G_SUBPROCESS_FLAGS_STDOUT_PIPE |
                               G_SUBPROCESS_FLAGS_STDERR_MERGE);
  if (cwd)
    g_subprocess_launcher_set_cwd (launcher, cwd);
  /* never wait for a password on an invisible terminal; English messages we can match on */
  g_subprocess_launcher_setenv (launcher, "GIT_TERMINAL_PROMPT", "0", TRUE);
  g_subprocess_launcher_setenv (launcher, "LC_ALL", "C.UTF-8", TRUE);

  g_autoptr (GPtrArray) argv = g_ptr_array_new ();
  g_ptr_array_add (argv, (gpointer) "git");
  if (token && *token) {
    g_subprocess_launcher_setenv (launcher, TOKEN_ENV, token, TRUE);
    /* empty value first: clear other helpers for github.com only */
    g_ptr_array_add (argv, (gpointer) "-c");
    g_ptr_array_add (argv, (gpointer) "credential.https://github.com.helper=");
    g_ptr_array_add (argv, (gpointer) "-c");
    g_ptr_array_add (argv, (gpointer) TOKEN_HELPER);
  }
  for (const char *const *a = args; *a; a++)
    g_ptr_array_add (argv, (gpointer) *a);
  g_ptr_array_add (argv, NULL);

  g_autoptr (GError) error = NULL;
  GSubprocess *proc = g_subprocess_launcher_spawnv (launcher, (const char *const *) argv->pdata, &error);
  if (!proc) {
    if (callback)
      callback (FALSE, error->message, user_data);
    return;
  }
  NetJob *job = g_new0 (NetJob, 1);
  job->callback = callback;
  job->user_data = user_data;
  /* NULL stdin buffer closes git's stdin right away */
  g_subprocess_communicate_utf8_async (proc, NULL, cancellable, on_communicated, job);
}

void
gdl_net_fetch (const char *repo, const char *token, GdlNetCallback cb, gpointer user_data)
{
  const char *args[] = { "fetch", "--prune", "origin", NULL };
  gdl_net_run (repo, args, token, NULL, cb, user_data);
}

void
gdl_net_pull (const char *repo, const char *token, gboolean merge_by_default, GdlNetCallback cb, gpointer user_data)
{
  const char *merge_args[] = { "pull", "--no-rebase", NULL };
  const char *args[] = { "pull", NULL };
  gdl_net_run (repo, merge_by_default ? merge_args : args, token, NULL, cb, user_data);
}

void
gdl_net_push (const char *repo, const char *token, const char *branch, GdlNetCallback cb, gpointer user_data)
{
  if (branch) {
    const char *args[] = { "push", "--set-upstream", "origin", branch, NULL };
    gdl_net_run (repo, args, token, NULL, cb, user_data);
  } else {
    const char *args[] = { "push", NULL };
    gdl_net_run (repo, args, token, NULL, cb, user_data);
  }
}

void
gdl_net_clone (const char *url, const char *dest, const char *token, GdlNetCallback cb, gpointer user_data)
{
  const char *args[] = { "clone", "--", url, dest, NULL };
  gdl_net_run (NULL, args, token, NULL, cb, user_data);
}

char *
gdl_net_explain_error (const char *output)
{
  if (strstr (output, "could not read Username") || strstr (output, "Authentication failed") ||
      strstr (output, "terminal prompts disabled") || strstr (output, "Permission denied (publickey)"))
    return g_strdup_printf ("%s\n\nGitHub asked for credentials. Sign in from the avatar menu at the top "
                            "right, or run “gh auth login” in a terminal.", output);
  return g_strdup (output);
}
