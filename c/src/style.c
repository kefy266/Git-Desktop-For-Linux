#include "style.h"

/* libadwaita already gives rounded, modern widgets and light/dark palettes.
 * This adds the GitHub Desktop-specific pieces on top, using Adwaita's
 * named colors so both themes work. */
static const char CSS[] =
  /* toolbar buttons: icon · caption over title · chevron */
  ".toolbar-button { padding: 4px 10px; border-radius: 10px; min-height: 40px; }\n"
  ".toolbar-button .caption-label { font-size: 0.78em; opacity: 0.65; }\n"
  ".toolbar-button .title-label { font-weight: 700; }\n"
  ".toolbar-divider { min-width: 1px; margin: 10px 4px; background: alpha(currentColor, 0.15); }\n"

  /* sidebar */
  ".gdl-sidebar { background: var(--sidebar-bg-color, @sidebar_bg_color); }\n"
  ".gdl-sidebar list { background: transparent; }\n"
  ".gdl-sidebar list > row { border-radius: 8px; margin: 1px 6px; }\n"
  ".file-row { padding: 6px 4px; }\n"
  ".file-name { font-weight: 600; }\n"
  ".file-dir { opacity: 0.55; }\n"
  ".commit-row { padding: 8px 6px; }\n"
  ".commit-summary { font-weight: 600; }\n"
  ".commit-meta { opacity: 0.6; font-size: 0.9em; }\n"
  ".section-row { padding: 10px 12px 4px 12px; }\n"
  ".section-label { font-size: 0.78em; font-weight: 800; opacity: 0.55; letter-spacing: 0.04em; }\n"

  /* status badges M / A / D / R / U */
  ".badge { font-weight: 800; font-size: 0.8em; border-radius: 5px; padding: 1px 6px; min-width: 10px; }\n"
  ".badge.modified { color: var(--warning-color, @warning_color); background: alpha(var(--warning-color, @warning_color), 0.16); }\n"
  ".badge.added { color: var(--success-color, @success_color); background: alpha(var(--success-color, @success_color), 0.16); }\n"
  ".badge.deleted, .badge.conflicted { color: var(--error-color, @error_color); background: alpha(var(--error-color, @error_color), 0.16); }\n"
  ".badge.renamed { color: var(--accent-color, @accent_color); background: alpha(var(--accent-color, @accent_color), 0.16); }\n"
  ".tag { font-size: 0.78em; font-weight: 700; border-radius: 99px; padding: 1px 8px; "
  "  border: 1px solid alpha(currentColor, 0.2); opacity: 0.75; }\n"

  /* commit box & banners */
  ".commit-box { padding: 12px; border-top: 1px solid alpha(currentColor, 0.1); }\n"
  ".commit-box textview { background: transparent; }\n"
  ".description-frame { border-radius: 8px; background: alpha(currentColor, 0.06); padding: 6px 8px; }\n"
  ".banner-card { padding: 8px 10px; border-radius: 10px; background: alpha(var(--accent-bg-color, @accent_bg_color), 0.14); }\n"
  ".banner-card.warn { background: alpha(var(--warning-color, @warning_color), 0.14); }\n"

  /* header of the diff & commit panes */
  ".pane-header { padding: 10px 14px; border-bottom: 1px solid alpha(currentColor, 0.1); }\n"
  ".commit-title { font-size: 1.15em; font-weight: 700; }\n"
  ".diff-view { font-size: 0.95em; }\n"

  /* empty-state action cards */
  ".action-card { padding: 14px 16px; min-width: 400px; }\n"
  ".action-card .hint { opacity: 0.55; }\n"

  /* popovers */
  ".gdl-popover > contents { padding: 0; }\n"
  ".gdl-popover list { background: transparent; }\n"
  ".gdl-popover list > row { border-radius: 8px; margin: 1px 6px; padding: 6px 8px; }\n"
  ".account-card { padding: 16px; min-width: 280px; }\n"
  ".menu-button-row { padding: 6px 8px; border-radius: 8px; }\n";

void
gdl_style_load (void)
{
  GtkCssProvider *provider = gtk_css_provider_new ();
  gtk_css_provider_load_from_string (provider, CSS);
  gtk_style_context_add_provider_for_display (gdk_display_get_default (), GTK_STYLE_PROVIDER (provider),
                                              GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
  g_object_unref (provider);
}
