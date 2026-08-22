#include "include/desktop_multi_window/desktop_multi_window_plugin.h"

#include <flutter_linux/flutter_linux.h>
#include <gdk/gdkx.h>
#include <gtk/gtk.h>
#include <libgen.h>
#include <unistd.h>
#include <X11/Xatom.h>
#include <linux/limits.h>

#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#define DESKTOP_MULTI_WINDOW_PLUGIN(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj), desktop_multi_window_plugin_get_type(), \
                              DesktopMultiWindowPlugin))

// GTK3 nao grava a propriedade que o WM le; so XChangeProperty serve. Ver armadilhas.md 4.8.
static void SetOpacityZero(GtkWidget* win) {
  GdkWindow* gdk_win = gtk_widget_get_window(win);
  if (!gdk_win || !GDK_IS_X11_WINDOW(gdk_win)) return;
  Display* display = GDK_DISPLAY_XDISPLAY(gdk_window_get_display(gdk_win));
  Atom prop = XInternAtom(display, "_NET_WM_WINDOW_OPACITY", False);
  if (prop == None) return;
  unsigned long value = 0ul;
  XChangeProperty(display, GDK_WINDOW_XID(gdk_win), prop, XA_CARDINAL, 32,
                  PropModeReplace, reinterpret_cast<unsigned char*>(&value), 1);
  XFlush(display);
}

struct WindowRecord {
  std::string id;
  std::string argument;
  GtkWidget* window;
  FlView* view;
  bool focusable;
};

static std::mutex g_plugin_mutex;
static std::map<std::string, WindowRecord> g_windows;
static int g_window_counter = 1;
static DesktopMultiWindowSetWindowCreatedCallback g_window_created_callback = nullptr;

void desktop_multi_window_plugin_set_window_created_callback(
    DesktopMultiWindowSetWindowCreatedCallback callback) {
  g_window_created_callback = callback;
}

static std::string GetExecutableDir() {
  char path[PATH_MAX];
  ssize_t count = readlink("/proc/self/exe", path, PATH_MAX);
  if (count <= 0) return ".";
  path[count] = '\0';
  char* dir = dirname(path);
  return std::string(dir);
}

// Channels registry
static std::map<std::string, FlMethodChannel*> g_registered_channels;

struct _DesktopMultiWindowPlugin {
  GObject parent_instance;
  FlPluginRegistrar* registrar;
  FlMethodChannel* channel;
  FlMethodChannel* channels_channel;
};

G_DEFINE_TYPE(DesktopMultiWindowPlugin, desktop_multi_window_plugin, g_object_get_type())

static void desktop_multi_window_plugin_dispose(GObject* object) {
  DesktopMultiWindowPlugin* self = DESKTOP_MULTI_WINDOW_PLUGIN(object);
  if (self->channel != nullptr) {
    g_clear_object(&self->channel);
  }
  if (self->channels_channel != nullptr) {
    g_clear_object(&self->channels_channel);
  }
  if (self->registrar != nullptr) {
    g_clear_object(&self->registrar);
  }
  G_OBJECT_CLASS(desktop_multi_window_plugin_parent_class)->dispose(object);
}

static void desktop_multi_window_plugin_class_init(DesktopMultiWindowPluginClass* klass) {
  G_OBJECT_CLASS(klass)->dispose = desktop_multi_window_plugin_dispose;
}

static void desktop_multi_window_plugin_init(DesktopMultiWindowPlugin* self) {
  self->registrar = nullptr;
  self->channel = nullptr;
  self->channels_channel = nullptr;
}

// Handler for mixin.one/desktop_multi_window
static FlMethodResponse* handle_main_method_call(DesktopMultiWindowPlugin* self,
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
    std::lock_guard<std::mutex> lock(g_plugin_mutex);
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

    std::lock_guard<std::mutex> lock(g_plugin_mutex);
    std::string id = std::to_string(g_window_counter++);
    GtkWidget* win = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_default_size(GTK_WINDOW(win), 560, 180);

    // Without a real RGBA visual the compositor has nothing alpha to blend; "transparent" paints opaque.
    GdkScreen* screen = gtk_widget_get_screen(win);
    // Visual RGBA impede o FlView de obter contexto GL nesta pilha (NVIDIA/GLX): a janela nunca
    // chega a ser mapeada. Sem ele a janela aparece, e o recorte de forma (window.setHitRect)
    // e quem tira o retangulo opaco. Ver docs/armadilhas.md 4.3.
    // Visual RGBA da a transparencia; ele so funciona porque a sub-janela nunca e desmapeada
    // (esconder = recortar para nada). Desmapear e remapear quebrava o contexto GL nesta pilha
    // NVIDIA/GLX e a janela nunca mais subia. Ver docs/armadilhas.md 4.3.
    GdkVisual* rgba_visual = gdk_screen_get_rgba_visual(screen);
    if (rgba_visual) {
      gtk_widget_set_visual(win, rgba_visual);
    } else {
      g_warning("sub-window %s: compositor sem visual RGBA, transparencia vai pintar opaca", id.c_str());
    }
    gtk_widget_set_app_paintable(win, TRUE);

    if (!focusable) {
      // O HUD nunca rouba o foco no Linux
      gtk_window_set_accept_focus(GTK_WINDOW(win), FALSE);
      gtk_window_set_focus_on_map(GTK_WINDOW(win), FALSE);
      gtk_window_set_keep_above(GTK_WINDOW(win), TRUE);
      gtk_window_set_decorated(GTK_WINDOW(win), FALSE);
      gtk_window_set_skip_taskbar_hint(GTK_WINDOW(win), TRUE);
    }

    // UTILITY (never NOTIFICATION/DOCK) so this overlay stays focusable for review-card Enter/Tab.
    gtk_window_set_type_hint(GTK_WINDOW(win), GDK_WINDOW_TYPE_HINT_UTILITY);

    // A view so consegue contexto GL sobre uma janela REALMENTE mapeada: realizar nao basta.
    // A janela sobe invisivel (recorte vazio) e so aparece quando o Dart pede a forma.
    // Ver docs/armadilhas.md 4.4.
    gtk_widget_show_all(win);
    // Nasce escondida como o 4.8 exige: forma de 1 px (NUNCA vazia), clique nenhum, opacidade 0.
    // Mapeada com forma vazia, o Muffin para de repintar o monitor inteiro. Ver armadilhas.md 4.10.
    cairo_rectangle_int_t ponto = {0, 0, 1, 1};
    cairo_region_t* minima = cairo_region_create_rectangle(&ponto);
    cairo_region_t* vazio = cairo_region_create();
    gtk_widget_shape_combine_region(win, minima);
    gtk_widget_input_shape_combine_region(win, vazio);
    cairo_region_destroy(minima);
    cairo_region_destroy(vazio);
    SetOpacityZero(win);
    // Nada de reentrar o main loop aqui: este bloco segura g_plugin_mutex, e um gtk_main_iteration
    // que despache outra chamada deste mesmo canal trava o processo para sempre.
    // Ver docs/armadilhas.md 4.4.

    std::string exe_dir = GetExecutableDir();
    std::string assets_path = exe_dir + "/data/flutter_assets";
    std::string icu_path = exe_dir + "/data/icudtl.dat";
    std::string aot_path = exe_dir + "/lib/libapp.so";

    g_autoptr(FlDartProject) project = fl_dart_project_new();
    fl_dart_project_set_assets_path(project, const_cast<gchar*>(assets_path.c_str()));
    fl_dart_project_set_icu_data_path(project, const_cast<gchar*>(icu_path.c_str()));
    // Same Impeller/GLX compositor-shader failure as the main window; keep sub-windows on Skia too.
    fl_dart_project_set_enable_impeller(project, FALSE);
    if (g_file_test(aot_path.c_str(), G_FILE_TEST_EXISTS)) {
      fl_dart_project_set_aot_library_path(project, const_cast<gchar*>(aot_path.c_str()));
    }

    const gchar* entry_args[] = { arg_str.c_str(), nullptr };
    fl_dart_project_set_dart_entrypoint_arguments(project, const_cast<gchar**>(entry_args));

    FlView* view = fl_view_new(project);
    GdkRGBA bg;
    gdk_rgba_parse(&bg, "#00000000");
    fl_view_set_background_color(view, &bg);
    gtk_container_add(GTK_CONTAINER(win), GTK_WIDGET(view));
    gtk_widget_show(GTK_WIDGET(view));
    gtk_widget_realize(GTK_WIDGET(view));

    // O runner principal faz isso (my_application.cc); a sub-janela nao fazia, e sem isso o
    // teclado nao chega ao motor Flutter mesmo com a janela focada. Ver armadilhas 4.6.
    gtk_widget_grab_focus(GTK_WIDGET(view));

    if (g_window_created_callback != nullptr) {
      g_window_created_callback(FL_PLUGIN_REGISTRY(view));
    }

    WindowRecord rec;
    rec.id = id;
    rec.argument = arg_str;
    rec.window = win;
    rec.view = view;
    rec.focusable = focusable;
    g_windows[id] = rec;

    g_autoptr(FlValue) res = fl_value_new_string(id.c_str());
    return FL_METHOD_RESPONSE(fl_method_success_response_new(res));
  } else if (g_strcmp0(method, "getWindowDefinition") == 0) {
    std::string current_id = "main";
    std::string current_arg = "";
    if (self->registrar && FL_IS_PLUGIN_REGISTRAR(self->registrar)) {
      FlView* my_view = fl_plugin_registrar_get_view(self->registrar);
      if (my_view) {
        std::lock_guard<std::mutex> lock(g_plugin_mutex);
        for (const auto& kv : g_windows) {
          if (kv.second.view == my_view) {
            current_id = kv.second.id;
            current_arg = kv.second.argument;
            break;
          }
        }
      }
    }
    g_autoptr(FlValue) map = fl_value_new_map();
    fl_value_set_string_take(map, "windowId", fl_value_new_string(current_id.c_str()));
    fl_value_set_string_take(map, "windowArgument", fl_value_new_string(current_arg.c_str()));
    return FL_METHOD_RESPONSE(fl_method_success_response_new(map));
  } else if (g_strcmp0(method, "getAllWindows") == 0) {
    std::lock_guard<std::mutex> lock(g_plugin_mutex);
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

// Handler for mixin.one/desktop_multi_window/channels
static void handle_channels_method_call(DesktopMultiWindowPlugin* self,
                                       FlMethodCall* method_call) {
  const gchar* method = fl_method_call_get_name(method_call);
  FlValue* args = fl_method_call_get_args(method_call);

  if (g_strcmp0(method, "registerMethodHandler") == 0) {
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* ch_v = fl_value_lookup_string(args, "channel");
      if (ch_v && fl_value_get_type(ch_v) == FL_VALUE_TYPE_STRING) {
        std::string channel_name = fl_value_get_string(ch_v);
        std::lock_guard<std::mutex> lock(g_plugin_mutex);
        g_registered_channels[channel_name] = self->channels_channel;
      }
    }
    g_autoptr(FlValue) res = fl_value_new_null();
    fl_method_call_respond_success(method_call, res, nullptr);
    return;
  }

  if (g_strcmp0(method, "unregisterMethodHandler") == 0) {
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* ch_v = fl_value_lookup_string(args, "channel");
      if (ch_v && fl_value_get_type(ch_v) == FL_VALUE_TYPE_STRING) {
        std::string channel_name = fl_value_get_string(ch_v);
        std::lock_guard<std::mutex> lock(g_plugin_mutex);
        g_registered_channels.erase(channel_name);
      }
    }
    g_autoptr(FlValue) res = fl_value_new_null();
    fl_method_call_respond_success(method_call, res, nullptr);
    return;
  }

  if (g_strcmp0(method, "invokeMethod") == 0) {
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* ch_v = fl_value_lookup_string(args, "channel");
      FlValue* meth_v = fl_value_lookup_string(args, "method");
      FlValue* arg_v = fl_value_lookup_string(args, "arguments");

      if (ch_v && fl_value_get_type(ch_v) == FL_VALUE_TYPE_STRING &&
          meth_v && fl_value_get_type(meth_v) == FL_VALUE_TYPE_STRING) {
        std::string channel_name = fl_value_get_string(ch_v);
        std::string meth_name = fl_value_get_string(meth_v);

        FlMethodChannel* target_channel = nullptr;
        {
          std::lock_guard<std::mutex> lock(g_plugin_mutex);
          auto it = g_registered_channels.find(channel_name);
          if (it != g_registered_channels.end()) {
            target_channel = it->second;
          }
        }

        if (target_channel) {
          g_autoptr(FlValue) call_args = fl_value_new_map();
          fl_value_set_string_take(call_args, "channel", fl_value_new_string(channel_name.c_str()));
          fl_value_set_string_take(call_args, "method", fl_value_new_string(meth_name.c_str()));
          if (arg_v) {
            fl_value_set(call_args, fl_value_new_string("arguments"), fl_value_ref(arg_v));
          } else {
            fl_value_set_string_take(call_args, "arguments", fl_value_new_null());
          }

          // Forward methodCall and respond when done
          g_object_ref(method_call);
          fl_method_channel_invoke_method(
              target_channel, "methodCall", call_args, nullptr,
              [](GObject* src, GAsyncResult* res, gpointer user_data) {
                FlMethodCall* orig_call = FL_METHOD_CALL(user_data);
                g_autoptr(GError) error = nullptr;
                g_autoptr(FlMethodResponse) resp =
                    fl_method_channel_invoke_method_finish(FL_METHOD_CHANNEL(src), res, &error);
                if (resp && FL_IS_METHOD_SUCCESS_RESPONSE(resp)) {
                  FlValue* val = fl_method_success_response_get_result(FL_METHOD_SUCCESS_RESPONSE(resp));
                  fl_method_call_respond_success(orig_call, val ? fl_value_ref(val) : nullptr, nullptr);
                } else {
                  fl_method_call_respond_success(orig_call, nullptr, nullptr);
                }
                g_object_unref(orig_call);
              },
              method_call);
          return;
        }
      }
    }
    g_autoptr(FlValue) res = fl_value_new_null();
    fl_method_call_respond_success(method_call, res, nullptr);
    return;
  }

  fl_method_call_respond_not_implemented(method_call, nullptr);
}

static void main_channel_cb(FlMethodChannel* channel,
                           FlMethodCall* method_call,
                           gpointer user_data) {
  DesktopMultiWindowPlugin* self = DESKTOP_MULTI_WINDOW_PLUGIN(user_data);
  g_autoptr(FlMethodResponse) response = handle_main_method_call(self, method_call);
  fl_method_call_respond(method_call, response, nullptr);
}

static void channels_channel_cb(FlMethodChannel* channel,
                               FlMethodCall* method_call,
                               gpointer user_data) {
  DesktopMultiWindowPlugin* self = DESKTOP_MULTI_WINDOW_PLUGIN(user_data);
  handle_channels_method_call(self, method_call);
}

void desktop_multi_window_plugin_register_with_registrar(
    FlPluginRegistrar* registrar) {
  DesktopMultiWindowPlugin* plugin = DESKTOP_MULTI_WINDOW_PLUGIN(
      g_object_new(desktop_multi_window_plugin_get_type(), nullptr));
  plugin->registrar = FL_PLUGIN_REGISTRAR(g_object_ref(registrar));

  g_autoptr(FlStandardMethodCodec) codec1 = fl_standard_method_codec_new();
  plugin->channel = fl_method_channel_new(
      fl_plugin_registrar_get_messenger(registrar),
      "mixin.one/desktop_multi_window", FL_METHOD_CODEC(codec1));
  fl_method_channel_set_method_call_handler(
      plugin->channel, main_channel_cb, g_object_ref(plugin), g_object_unref);

  g_autoptr(FlStandardMethodCodec) codec2 = fl_standard_method_codec_new();
  plugin->channels_channel = fl_method_channel_new(
      fl_plugin_registrar_get_messenger(registrar),
      "mixin.one/desktop_multi_window/channels", FL_METHOD_CODEC(codec2));
  fl_method_channel_set_method_call_handler(
      plugin->channels_channel, channels_channel_cb, g_object_ref(plugin), g_object_unref);

  g_object_unref(plugin);
}
