#include "include/desktop_multi_window/desktop_multi_window_plugin.h"

#include <flutter_linux/flutter_linux.h>
#include <gtk/gtk.h>

#include <map>
#include <memory>
#include <string>
#include <vector>

#define DESKTOP_MULTI_WINDOW_PLUGIN(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj), desktop_multi_window_plugin_get_type(), \
                              DesktopMultiWindowPlugin))

struct WindowRecord {
  std::string id;
  std::string argument;
  GtkWidget* window;
  bool focusable;
};

static std::map<std::string, WindowRecord> g_windows;
static int g_window_counter = 1;

struct _DesktopMultiWindowPlugin {
  GObject parent_instance;
  FlPluginRegistrar* registrar;
  FlMethodChannel* channel;
};

G_DEFINE_TYPE(DesktopMultiWindowPlugin, desktop_multi_window_plugin, g_object_get_type())

static void desktop_multi_window_plugin_dispose(GObject* object) {
  DesktopMultiWindowPlugin* self = DESKTOP_MULTI_WINDOW_PLUGIN(object);
  if (self->channel != nullptr) {
    g_clear_object(&self->channel);
  }
  G_OBJECT_CLASS(desktop_multi_window_plugin_parent_class)->dispose(object);
}

static void desktop_multi_window_plugin_class_init(DesktopMultiWindowPluginClass* klass) {
  G_OBJECT_CLASS(klass)->dispose = desktop_multi_window_plugin_dispose;
}

static void desktop_multi_window_plugin_init(DesktopMultiWindowPlugin* self) {
  self->registrar = nullptr;
  self->channel = nullptr;
}

static FlMethodResponse* handle_method_call(DesktopMultiWindowPlugin* self,
                                           FlMethodCall* method_call) {
  const gchar* method = fl_method_call_get_name(method_call);
  FlValue* args = fl_method_call_get_args(method_call);

  if (g_str_has_prefix(method, "window_")) {
    if (fl_value_get_type(args) != FL_VALUE_TYPE_MAP) {
      return FL_METHOD_RESPONSE(fl_method_error_response_new("INVALID_ARGS", "Expected map", nullptr));
    }
    FlValue* id_val = fl_value_lookup_string(args, "windowId");
    if (!id_val || fl_value_get_type(id_val) != FL_VALUE_TYPE_STRING) {
      return FL_METHOD_RESPONSE(fl_method_error_response_new("INVALID_ARGS", "Missing windowId", nullptr));
    }
    std::string win_id = fl_value_get_string(id_val);
    auto it = g_windows.find(win_id);
    if (it == g_windows.end() || !it->second.window) {
      return FL_METHOD_RESPONSE(fl_method_error_response_new("NOT_FOUND", "Window not found", nullptr));
    }

    GtkWidget* win = it->second.window;

    if (g_strcmp0(method, "window_show") == 0) {
      gtk_widget_show_all(win);
      return FL_METHOD_RESPONSE(fl_method_success_response_new(nullptr));
    } else if (g_strcmp0(method, "window_hide") == 0) {
      gtk_widget_hide(win);
      return FL_METHOD_RESPONSE(fl_method_success_response_new(nullptr));
    } else if (g_strcmp0(method, "window_close") == 0) {
      gtk_widget_destroy(win);
      g_windows.erase(it);
      return FL_METHOD_RESPONSE(fl_method_success_response_new(nullptr));
    } else if (g_strcmp0(method, "window_set_bounds") == 0) {
      FlValue* x_v = fl_value_lookup_string(args, "x");
      FlValue* y_v = fl_value_lookup_string(args, "y");
      FlValue* w_v = fl_value_lookup_string(args, "width");
      FlValue* h_v = fl_value_lookup_string(args, "height");
      int x = (x_v && fl_value_get_type(x_v) == FL_VALUE_TYPE_INT) ? fl_value_get_int(x_v) : 0;
      int y = (y_v && fl_value_get_type(y_v) == FL_VALUE_TYPE_INT) ? fl_value_get_int(y_v) : 0;
      int w = (w_v && fl_value_get_type(w_v) == FL_VALUE_TYPE_INT) ? fl_value_get_int(w_v) : 400;
      int h = (h_v && fl_value_get_type(h_v) == FL_VALUE_TYPE_INT) ? fl_value_get_int(h_v) : 300;
      gtk_window_move(GTK_WINDOW(win), x, y);
      gtk_window_resize(GTK_WINDOW(win), w, h);
      return FL_METHOD_RESPONSE(fl_method_success_response_new(nullptr));
    } else if (g_strcmp0(method, "window_get_bounds") == 0) {
      int x = 0, y = 0, w = 0, h = 0;
      gtk_window_get_position(GTK_WINDOW(win), &x, &y);
      gtk_window_get_size(GTK_WINDOW(win), &w, &h);
      g_autoptr(FlValue) map = fl_value_new_map();
      fl_value_set_string_take(map, "x", fl_value_new_int(x));
      fl_value_set_string_take(map, "y", fl_value_new_int(y));
      fl_value_set_string_take(map, "width", fl_value_new_int(w));
      fl_value_set_string_take(map, "height", fl_value_new_int(h));
      return FL_METHOD_RESPONSE(fl_method_success_response_new(map));
    } else if (g_strcmp0(method, "window_set_title") == 0) {
      FlValue* title_v = fl_value_lookup_string(args, "title");
      if (title_v && fl_value_get_type(title_v) == FL_VALUE_TYPE_STRING) {
        gtk_window_set_title(GTK_WINDOW(win), fl_value_get_string(title_v));
      }
      return FL_METHOD_RESPONSE(fl_method_success_response_new(nullptr));
    }
    return FL_METHOD_RESPONSE(fl_method_success_response_new(nullptr));
  }

  if (g_strcmp0(method, "createWindow") == 0) {
    std::string arg_str = "";
    bool focusable = true;
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* a_v = fl_value_lookup_string(args, "arguments");
      if (a_v && fl_value_get_type(a_v) == FL_VALUE_TYPE_STRING) {
        arg_str = fl_value_get_string(a_v);
      }
      FlValue* f_v = fl_value_lookup_string(args, "focusable");
      if (f_v && fl_value_get_type(f_v) == FL_VALUE_TYPE_BOOL) {
        focusable = fl_value_get_bool(f_v);
      }
    }

    std::string id = std::to_string(g_window_counter++);
    GtkWidget* win = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_default_size(GTK_WINDOW(win), 400, 300);

    if (!focusable) {
      // O HUD nunca rouba o foco no Linux
      gtk_window_set_accept_focus(GTK_WINDOW(win), FALSE);
      gtk_window_set_focus_on_map(GTK_WINDOW(win), FALSE);
      gtk_window_set_keep_above(GTK_WINDOW(win), TRUE);
      gtk_window_set_decorated(GTK_WINDOW(win), FALSE);
      gtk_window_set_skip_taskbar_hint(GTK_WINDOW(win), TRUE);
    }

    WindowRecord rec;
    rec.id = id;
    rec.argument = arg_str;
    rec.window = win;
    rec.focusable = focusable;
    g_windows[id] = rec;

    g_autoptr(FlValue) res = fl_value_new_string(id.c_str());
    return FL_METHOD_RESPONSE(fl_method_success_response_new(res));
  } else if (g_strcmp0(method, "getWindowDefinition") == 0) {
    g_autoptr(FlValue) map = fl_value_new_map();
    fl_value_set_string_take(map, "windowId", fl_value_new_string("main"));
    fl_value_set_string_take(map, "windowArgument", fl_value_new_string(""));
    return FL_METHOD_RESPONSE(fl_method_success_response_new(map));
  } else if (g_strcmp0(method, "getAllWindows") == 0) {
    g_autoptr(FlValue) list = fl_value_new_list();
    for (const auto& kv : g_windows) {
      FlValue* m = fl_value_new_map();
      fl_value_set_string_take(m, "windowId", fl_value_new_string(kv.first.c_str()));
      fl_value_set_string_take(m, "windowArgument", fl_value_new_string(kv.second.argument.c_str()));
      fl_value_append_take(list, m);
    }
    return FL_METHOD_RESPONSE(fl_method_success_response_new(list));
  }

  return FL_METHOD_RESPONSE(fl_method_not_implemented_response_new());
}

static void method_call_cb(FlMethodChannel* channel,
                           FlMethodCall* method_call,
                           gpointer user_data) {
  DesktopMultiWindowPlugin* self = DESKTOP_MULTI_WINDOW_PLUGIN(user_data);
  g_autoptr(FlMethodResponse) response = handle_method_call(self, method_call);
  fl_method_call_respond(method_call, response, nullptr);
}

void desktop_multi_window_plugin_register_with_registrar(
    FlPluginRegistrar* registrar) {
  DesktopMultiWindowPlugin* plugin = DESKTOP_MULTI_WINDOW_PLUGIN(
      g_object_new(desktop_multi_window_plugin_get_type(), nullptr));
  plugin->registrar = registrar;

  g_autoptr(FlStandardMethodCodec) codec = fl_standard_method_codec_new();
  plugin->channel = fl_method_channel_new(
      fl_plugin_registrar_get_messenger(registrar),
      "mixin.one/desktop_multi_window", FL_METHOD_CODEC(codec));
  fl_method_channel_set_method_call_handler(
      plugin->channel, method_call_cb, g_object_ref(plugin), g_object_unref);

  g_object_unref(plugin);
}
