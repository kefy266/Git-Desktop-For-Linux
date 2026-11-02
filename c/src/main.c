/* Git Desktop For Linux — native C / GTK4 / libadwaita edition. */
#include <adwaita.h>

#include "settings.h"
#include "style.h"
#include "window.h"

/* Accelerators, mirroring GitHub Desktop */
static const struct { const char *action; const char *accels[3]; const char *title; } SHORTCUTS[] = {
  { "win.show-changes",  { "<Control>1", NULL }, "Show changes" },
  { "win.show-history",  { "<Control>2", NULL }, "Show history" },
  { "win.repo-list",     { "<Control>t", NULL }, "Repository list" },
  { "win.branch-list",   { "<Control>b", NULL }, "Branch list" },
  { "win.commit",        { "<Control>Return", "<Control>KP_Enter", NULL }, "Commit" },
  { "win.push",          { "<Control>p", NULL }, "Push" },
  { "win.pull",          { "<Control><Shift>p", NULL }, "Pull" },
  { "win.fetch",         { "<Control><Shift>t", NULL }, "Fetch" },
  { "win.new-branch",    { "<Control><Shift>n", NULL }, "New branch" },
  { "win.merge",         { "<Control><Shift>m", NULL }, "Merge into current branch" },
  { "win.stash",         { "<Control><Shift>s", NULL }, "Stash all changes" },
  { "win.discard-all",   { "<Control><Shift>BackSpace", NULL }, "Discard all changes" },
  { "win.new-repo",      { "<Control>n", NULL }, "New repository" },
  { "win.add-repo",      { "<Control>o", NULL }, "Add local repository" },
  { "win.clone",         { "<Control><Shift>o", NULL }, "Clone repository" },
  { "win.open-editor",   { "<Control><Shift>a", NULL }, "Open in external editor" },
  { "win.open-terminal", { "<Control>grave", NULL }, "Open in terminal" },
  { "win.file-manager",  { "<Control><Shift>f", NULL }, "Show in file manager" },
  { "win.refresh",       { "F5", NULL }, "Refresh" },
  { "win.preferences",   { "<Control>comma", NULL }, "Preferences" },
  { "app.quit",          { "<Control>q", NULL }, "Quit" },
};

static char *screenshot_path;
static char *screenshot_view;

static void
act_quit (GSimpleAction *a, GVariant *p, gpointer app)
{
  g_application_quit (G_APPLICATION (app));
}

static void
act_about (GSimpleAction *a, GVariant *p, gpointer app)
{
  AdwDialog *d = adw_about_dialog_new ();
  AdwAboutDialog *about = ADW_ABOUT_DIALOG (d);
  adw_about_dialog_set_application_name (about, "Git Desktop For Linux");
  adw_about_dialog_set_application_icon (about, APP_ID);
  adw_about_dialog_set_version (about, "1.0");
  adw_about_dialog_set_developer_name (about, "Kağan Efe TOPÇU");
  adw_about_dialog_set_website (about, "https://github.com/kefy266/Git-Desktop-For-Linux");
  adw_about_dialog_set_comments (about, "A simple Git client for Linux, modeled on GitHub Desktop.");
  adw_about_dialog_set_license_type (about, GTK_LICENSE_UNKNOWN);
  adw_dialog_present (d, GTK_WIDGET (gtk_application_get_active_window (GTK_APPLICATION (app))));
}

static void
act_shortcuts (GSimpleAction *a, GVariant *p, gpointer app)
{
  AdwDialog *d = adw_shortcuts_dialog_new ();
  AdwShortcutsSection *section = adw_shortcuts_section_new (NULL);
  for (guint i = 0; i < G_N_ELEMENTS (SHORTCUTS); i++)
    adw_shortcuts_section_add (section, adw_shortcuts_item_new (SHORTCUTS[i].title, SHORTCUTS[i].accels[0]));
  adw_shortcuts_dialog_add (ADW_SHORTCUTS_DIALOG (d), section);
  adw_dialog_present (d, GTK_WIDGET (gtk_application_get_active_window (GTK_APPLICATION (app))));
}

static void
on_startup (GApplication *app)
{
  gdl_style_load ();
  gdl_window_apply_theme ();
  static const GActionEntry entries[] = {
    { "quit", act_quit }, { "about", act_about }, { "shortcuts", act_shortcuts },
  };
  g_action_map_add_action_entries (G_ACTION_MAP (app), entries, G_N_ELEMENTS (entries), app);
  for (guint i = 0; i < G_N_ELEMENTS (SHORTCUTS); i++)
    gtk_application_set_accels_for_action (GTK_APPLICATION (app), SHORTCUTS[i].action, SHORTCUTS[i].accels);
}

static void
open_window (GApplication *app, const char *repo)
{
  GtkWindow *existing = gtk_application_get_active_window (GTK_APPLICATION (app));
  if (existing && !screenshot_path) {
    if (repo)
      gdl_window_open_repository (GDL_WINDOW (existing), repo);
    gtk_window_present (existing);
    return;
  }
  GdlWindow *win = gdl_window_new (ADW_APPLICATION (app), repo);
  gtk_window_present (GTK_WINDOW (win));
  if (screenshot_path)
    gdl_window_screenshot (win, screenshot_path, screenshot_view);
}

static void
on_activate (GApplication *app)
{
  open_window (app, NULL);
}

static void
on_open (GApplication *app, GFile **files, int n, const char *hint)
{
  g_autofree char *path = n > 0 ? g_file_get_path (files[0]) : NULL;
  open_window (app, path);
}

int
main (int argc, char **argv)
{
  g_autoptr (AdwApplication) app = adw_application_new (APP_ID, G_APPLICATION_HANDLES_OPEN);
  const GOptionEntry options[] = {
    /* development aid: render the window to a PNG, then quit */
    { "screenshot", 0, 0, G_OPTION_ARG_FILENAME, &screenshot_path, "Save a screenshot and quit", "PNG" },
    { "view", 0, 0, G_OPTION_ARG_STRING, &screenshot_view, "changes|history|branches|repos|account|clone|prefs|signin|newbranch", "VIEW" },
    { NULL },
  };
  g_application_add_main_option_entries (G_APPLICATION (app), options);
  g_signal_connect (app, "startup", G_CALLBACK (on_startup), NULL);
  g_signal_connect (app, "activate", G_CALLBACK (on_activate), NULL);
  g_signal_connect (app, "open", G_CALLBACK (on_open), NULL);
  int status = g_application_run (G_APPLICATION (app), argc, argv);
  g_free (screenshot_path);
  g_free (screenshot_view);
  return status;
}
