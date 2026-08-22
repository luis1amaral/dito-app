#include "my_application.h"

#include <flutter_linux/flutter_linux.h>
#ifdef GDK_WINDOWING_X11
#include <gdk/gdkx.h>
#endif

#include "flutter/generated_plugin_registrant.h"
#include <desktop_multi_window/desktop_multi_window_plugin.h>
#include <glib/gstdio.h>
#include <stdio.h>

struct _MyApplication {
  GtkApplication parent_instance;
  char** dart_entrypoint_arguments;
};

G_DEFINE_TYPE(MyApplication, my_application, GTK_TYPE_APPLICATION)

// Guards the file below since g_log handlers may run on any thread.
static GMutex native_log_mutex;

static gboolean native_log_env_is_blank(const gchar* value) {
  if (value == nullptr) return TRUE;
  for (const gchar* p = value; *p != '\0'; ++p) {
    if (!g_ascii_isspace(*p)) return FALSE;
  }
  return TRUE;
}

// Mirrors DitoPaths.dataDir/logsDir in lib/config/paths.dart: XDG_DATA_HOME, else $HOME/.local/share, then /dito/logs.
static gchar* native_log_directory() {
  const gchar* xdg_data_home = g_getenv("XDG_DATA_HOME");
  gchar* base;
  if (!native_log_env_is_blank(xdg_data_home)) {
    base = g_strdup(xdg_data_home);
  } else {
    const gchar* home = g_getenv("HOME");
    if (native_log_env_is_blank(home)) {
      home = g_get_home_dir();
    }
    base = g_build_filename(home, ".local", "share", nullptr);
  }
  gchar* dir = g_build_filename(base, "dito", "logs", nullptr);
  g_free(base);
  return dir;
}

static const gchar* native_log_level_name(GLogLevelFlags log_level) {
  if (log_level & G_LOG_LEVEL_ERROR) return "ERROR";
  if (log_level & G_LOG_LEVEL_CRITICAL) return "CRITICAL";
  if (log_level & G_LOG_LEVEL_WARNING) return "WARNING";
  if (log_level & G_LOG_LEVEL_MESSAGE) return "MESSAGE";
  if (log_level & G_LOG_LEVEL_INFO) return "INFO";
  if (log_level & G_LOG_LEVEL_DEBUG) return "DEBUG";
  return "LOG";
}

// Writes every g_log() message to disk too, since the tray/shortcut launch path has no visible stderr.
static void native_log_handler(const gchar* log_domain, GLogLevelFlags log_level,
                                const gchar* message, gpointer user_data) {
  g_log_default_handler(log_domain, log_level, message, user_data);

  g_mutex_lock(&native_log_mutex);

  gchar* dir = native_log_directory();
  g_mkdir_with_parents(dir, 0755);
  gchar* path = g_build_filename(dir, "native.log", nullptr);
  g_free(dir);

  g_autoptr(GDateTime) now = g_date_time_new_now_local();
  gchar* date_part = g_date_time_format(now, "%Y-%m-%dT%H:%M:%S");
  gchar* timestamp =
      g_strdup_printf("%s.%06d", date_part, g_date_time_get_microsecond(now));
  g_free(date_part);

  // Open/close per message: warnings are rare, so a held-open FILE* is not worth the extra state.
  FILE* file = g_fopen(path, "a");
  if (file != nullptr) {
    fprintf(file, "[%s] [native] [%s] %s\n", timestamp, native_log_level_name(log_level),
            message != nullptr ? message : "");
    fclose(file);
  }
  g_free(path);
  g_free(timestamp);

  g_mutex_unlock(&native_log_mutex);
}

// Called when first Flutter frame received.
static void first_frame_cb(MyApplication* self, FlView* view) {
  // Mesma regra do lib/main.dart, que le este mesmo vetor: no Linux so --janela mostra.
  gboolean start_hidden = TRUE;
  if (self->dart_entrypoint_arguments != nullptr) {
    for (char** arg = self->dart_entrypoint_arguments; *arg != nullptr; ++arg) {
      if (g_strcmp0(*arg, "--janela") == 0) {
        start_hidden = FALSE;
        break;
      }
    }
  }
  if (!start_hidden) {
    gtk_widget_show(gtk_widget_get_toplevel(GTK_WIDGET(view)));
  }
}

// Implements GApplication::activate.
static void my_application_activate(GApplication* application) {
  MyApplication* self = MY_APPLICATION(application);

  // Second launch must focus the running Dito, never start a rival that loses the X key grab.
  GList* existing = gtk_application_get_windows(GTK_APPLICATION(application));
  if (existing != nullptr) {
    gtk_window_present(GTK_WINDOW(existing->data));
    return;
  }

  GtkWindow* window =
      GTK_WINDOW(gtk_application_window_new(GTK_APPLICATION(application)));

  // Configure default icon and window icon
  gtk_window_set_default_icon_name("dito");
  gtk_window_set_icon_name(window, "dito");
  if (!gtk_window_set_icon_from_file(window, "/opt/dito/data/flutter_assets/assets/icons/icon.svg", nullptr)) {
    if (!gtk_window_set_icon_from_file(window, "/usr/share/pixmaps/dito.svg", nullptr)) {
      gtk_window_set_icon_from_file(window, "/usr/share/icons/hicolor/scalable/apps/dito.svg", nullptr);
    }
  }

  // Use a header bar when running in GNOME as this is the common style used
  // by applications and is the setup most users will be using (e.g. Ubuntu
  // desktop).
  // If running on X and not using GNOME then just use a traditional title bar
  // in case the window manager does more exotic layout, e.g. tiling.
  // If running on Wayland assume the header bar will work (may need changing
  // if future cases occur).
  gboolean use_header_bar = TRUE;
#ifdef GDK_WINDOWING_X11
  GdkScreen* screen = gtk_window_get_screen(window);
  if (GDK_IS_X11_SCREEN(screen)) {
    const gchar* wm_name = gdk_x11_screen_get_window_manager_name(screen);
    if (g_strcmp0(wm_name, "GNOME Shell") != 0) {
      use_header_bar = FALSE;
    }
  }
#endif
  if (use_header_bar) {
    GtkHeaderBar* header_bar = GTK_HEADER_BAR(gtk_header_bar_new());
    gtk_widget_show(GTK_WIDGET(header_bar));
    gtk_header_bar_set_title(header_bar, "Dito");
    gtk_header_bar_set_show_close_button(header_bar, TRUE);
    gtk_window_set_titlebar(window, GTK_WIDGET(header_bar));
  } else {
    gtk_window_set_title(window, "Dito");
  }

  gtk_window_set_default_size(window, 1280, 720);

  g_autoptr(FlDartProject) project = fl_dart_project_new();
  fl_dart_project_set_dart_entrypoint_arguments(
      project, self->dart_entrypoint_arguments);
  // Impeller's compositor shaders never come up on this NVIDIA/GLX setup, leaving windows blank; Skia works.
  fl_dart_project_set_enable_impeller(project, FALSE);

  FlView* view = fl_view_new(project);
  GdkRGBA background_color;
  // Background defaults to black, override it here if necessary, e.g. #00000000
  // for transparent.
  gdk_rgba_parse(&background_color, "#000000");
  fl_view_set_background_color(view, &background_color);
  gtk_widget_show(GTK_WIDGET(view));
  gtk_container_add(GTK_CONTAINER(window), GTK_WIDGET(view));

  // Show the window when Flutter renders.
  // Requires the view to be realized so we can start rendering.
  g_signal_connect_swapped(view, "first-frame", G_CALLBACK(first_frame_cb),
                           self);
  gtk_widget_realize(GTK_WIDGET(view));

  desktop_multi_window_plugin_set_window_created_callback(fl_register_plugins);
  fl_register_plugins(FL_PLUGIN_REGISTRY(view));

  gtk_widget_grab_focus(GTK_WIDGET(view));
}

// Implements GApplication::local_command_line.
static gboolean my_application_local_command_line(GApplication* application,
                                                  gchar*** arguments,
                                                  int* exit_status) {
  MyApplication* self = MY_APPLICATION(application);
  // Strip out the first argument as it is the binary name.
  self->dart_entrypoint_arguments = g_strdupv(*arguments + 1);

  g_autoptr(GError) error = nullptr;
  if (!g_application_register(application, nullptr, &error)) {
    g_warning("Failed to register: %s", error->message);
    *exit_status = 1;
    return TRUE;
  }

  g_application_activate(application);
  *exit_status = 0;

  return TRUE;
}

// Implements GApplication::startup.
static void my_application_startup(GApplication* application) {
  // MyApplication* self = MY_APPLICATION(object);

  // Perform any actions required at application startup.

  G_APPLICATION_CLASS(my_application_parent_class)->startup(application);
}

// Implements GApplication::shutdown.
static void my_application_shutdown(GApplication* application) {
  // MyApplication* self = MY_APPLICATION(object);

  // Perform any actions required at application shutdown.

  G_APPLICATION_CLASS(my_application_parent_class)->shutdown(application);
}

// Implements GObject::dispose.
static void my_application_dispose(GObject* object) {
  MyApplication* self = MY_APPLICATION(object);
  g_clear_pointer(&self->dart_entrypoint_arguments, g_strfreev);
  G_OBJECT_CLASS(my_application_parent_class)->dispose(object);
}

static void my_application_class_init(MyApplicationClass* klass) {
  G_APPLICATION_CLASS(klass)->activate = my_application_activate;
  G_APPLICATION_CLASS(klass)->local_command_line =
      my_application_local_command_line;
  G_APPLICATION_CLASS(klass)->startup = my_application_startup;
  G_APPLICATION_CLASS(klass)->shutdown = my_application_shutdown;
  G_OBJECT_CLASS(klass)->dispose = my_application_dispose;
}

static void my_application_init(MyApplication* self) {}

MyApplication* my_application_new() {
  // Installed before anything else so no early g_warning/g_critical is lost to an invisible stderr.
  g_log_set_default_handler(native_log_handler, nullptr);

  // Set the program name to the application ID, which helps various systems
  // like GTK and desktop environments map this running application to its
  // corresponding .desktop file. This ensures better integration by allowing
  // the application to be recognized beyond its binary name.
  g_set_prgname(APPLICATION_ID);

  // Single instance on purpose: XGrabKey is exclusive, so a second Dito would be deaf to F9/F10.
  return MY_APPLICATION(g_object_new(my_application_get_type(),
                                     "application-id", APPLICATION_ID, "flags",
                                     G_APPLICATION_DEFAULT_FLAGS, nullptr));
}
