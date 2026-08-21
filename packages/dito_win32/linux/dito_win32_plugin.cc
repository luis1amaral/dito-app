#include "include/dito_win32/dito_win32_plugin.h"

#include <flutter_linux/flutter_linux.h>
#include <gtk/gtk.h>
#include <gdk/gdkx.h>
#include <sys/utsname.h>
#include <dlfcn.h>

#include <X11/Xlib.h>
#include <X11/XKBlib.h>
#include <X11/Xatom.h>
#include <X11/keysym.h>
#include <poll.h>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#define DITO_WIN32_PLUGIN(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj), dito_win32_plugin_get_type(), \
                              DitoWin32Plugin))

namespace {

int64_t NowMicros() {
  return std::chrono::duration_cast<std::chrono::microseconds>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}

KeySym KeySymFromName(std::string name) {
  for (auto& c : name) c = toupper(c);
  if (name == "F1") return XK_F1;
  if (name == "F2") return XK_F2;
  if (name == "F3") return XK_F3;
  if (name == "F4") return XK_F4;
  if (name == "F5") return XK_F5;
  if (name == "F6") return XK_F6;
  if (name == "F7") return XK_F7;
  if (name == "F8") return XK_F8;
  if (name == "F9") return XK_F9;
  if (name == "F10") return XK_F10;
  if (name == "F11") return XK_F11;
  if (name == "F12") return XK_F12;
  if (name == "ESCAPE" || name == "ESC") return XK_Escape;
  if (name == "SPACE") return XK_space;
  if (name == "ENTER" || name == "RETURN") return XK_Return;
  if (name == "TAB") return XK_Tab;
  if (name == "BACKSPACE") return XK_BackSpace;
  if (name == "CONTROL_L" || name == "CTRL_L" || name == "LCTRL") return XK_Control_L;
  if (name == "CONTROL_R" || name == "CTRL_R" || name == "RCTRL") return XK_Control_R;
  if (name == "ALT_L" || name == "LALT") return XK_Alt_L;
  if (name == "ALT_R" || name == "RALT") return XK_Alt_R;
  if (name == "SHIFT_L" || name == "LSHIFT") return XK_Shift_L;
  if (name == "SHIFT_R" || name == "RSHIFT") return XK_Shift_R;
  if (name == "CAPS_LOCK" || name == "CAPSLOCK") return XK_Caps_Lock;
  if (name == "SCROLL_LOCK") return XK_Scroll_Lock;
  if (name == "NUM_LOCK") return XK_Num_Lock;
  if (name == "PRINT") return XK_Print;
  if (name == "PAUSE") return XK_Pause;
  if (name == "INSERT") return XK_Insert;
  if (name == "DELETE" || name == "DEL") return XK_Delete;
  if (name == "HOME") return XK_Home;
  if (name == "END") return XK_End;
  if (name == "PAGE_UP" || name == "PAGEUP") return XK_Page_Up;
  if (name == "PAGE_DOWN" || name == "PAGEDOWN") return XK_Page_Down;
  if (name == "LEFT") return XK_Left;
  if (name == "UP") return XK_Up;
  if (name == "RIGHT") return XK_Right;
  if (name == "DOWN") return XK_Down;
  return XStringToKeysym(name.c_str());
}

struct X11Binding {
  std::string action;
  std::string key;
  KeyCode keycode;
  bool suppress;
};

// AppIndicator dynamic bindings
typedef void* (*fn_app_indicator_new)(const gchar*, const gchar*, int);
typedef void (*fn_app_indicator_set_status)(void*, int);
typedef void (*fn_app_indicator_set_icon_full)(void*, const gchar*, const gchar*);
typedef void (*fn_app_indicator_set_menu)(void*, GtkMenu*);
typedef void (*fn_app_indicator_set_title)(void*, const gchar*);
typedef void (*fn_app_indicator_set_icon_theme_path)(void*, const gchar*);

struct AppIndicatorLib {
  void* handle{nullptr};
  fn_app_indicator_new ind_new{nullptr};
  fn_app_indicator_set_status set_status{nullptr};
  fn_app_indicator_set_icon_full set_icon_full{nullptr};
  fn_app_indicator_set_menu set_menu{nullptr};
  fn_app_indicator_set_title set_title{nullptr};
  fn_app_indicator_set_icon_theme_path set_icon_theme_path{nullptr};

  bool Load() {
    if (handle) return true;
    handle = dlopen("libayatana-appindicator3.so.1", RTLD_LAZY);
    if (!handle) handle = dlopen("libappindicator3.so.1", RTLD_LAZY);
    if (!handle) return false;

    ind_new = (fn_app_indicator_new)dlsym(handle, "app_indicator_new");
    set_status = (fn_app_indicator_set_status)dlsym(handle, "app_indicator_set_status");
    set_icon_full = (fn_app_indicator_set_icon_full)dlsym(handle, "app_indicator_set_icon_full");
    set_menu = (fn_app_indicator_set_menu)dlsym(handle, "app_indicator_set_menu");
    set_title = (fn_app_indicator_set_title)dlsym(handle, "app_indicator_set_title");
    set_icon_theme_path = (fn_app_indicator_set_icon_theme_path)dlsym(handle, "app_indicator_set_icon_theme_path");

    return (ind_new && set_status && set_icon_full && set_menu);
  }
};

static AppIndicatorLib g_indicator_lib;

struct PluginState {
  std::mutex mutex;
  std::vector<X11Binding> bindings;
  std::map<std::string, bool> seen;
  std::atomic<bool> paused{false};
  std::atomic<int64_t> seen_count{0};
  std::atomic<int64_t> pump_count{0};
  std::atomic<int64_t> last_engaged_micros{0};

  Display* display{nullptr};
  Window root_window{0};
  std::thread thread;
  std::atomic<bool> running{false};

  // Mirrors GetForegroundWindow() bookkeeping on the Windows plugin (focus.take/giveBack).
  Window saved_focus_target{0};

  // Tray
  void* app_indicator{nullptr};
  GtkWidget* current_menu{nullptr};
};

}  // namespace

struct _DitoWin32Plugin {
  GObject parent_instance;
  FlPluginRegistrar* registrar;
  FlMethodChannel* method_channel;
  FlEventChannel* key_channel;
  FlEventChannel* tray_channel;
  gboolean key_channel_active;
  gboolean tray_channel_active;
  guint tick_timer_id;
  PluginState* state;
};

G_DEFINE_TYPE(DitoWin32Plugin, dito_win32_plugin, g_object_get_type())

static void SendKeyEdge(DitoWin32Plugin* self, const std::string& type,
                        const std::string& action, const std::string& key,
                        int64_t micros) {
  if (!self->key_channel_active || self->key_channel == nullptr) return;

  FlValue* map = fl_value_new_map();
  fl_value_set_string_take(map, "type", fl_value_new_string(type.c_str()));
  fl_value_set_string_take(map, "name", fl_value_new_string(action.c_str()));
  fl_value_set_string_take(map, "key", fl_value_new_string(key.c_str()));
  fl_value_set_string_take(map, "t", fl_value_new_int(micros));

  g_autoptr(GError) error = nullptr;
  fl_event_channel_send(self->key_channel, map, nullptr, &error);
  fl_value_unref(map);
}

static void SendKeyTick(DitoWin32Plugin* self,
                        const std::vector<std::string>& down_actions,
                        int64_t micros) {
  if (!self->key_channel_active || self->key_channel == nullptr) return;

  FlValue* map = fl_value_new_map();
  fl_value_set_string_take(map, "type", fl_value_new_string("tick"));
  fl_value_set_string_take(map, "t", fl_value_new_int(micros));

  FlValue* list = fl_value_new_list();
  for (const auto& a : down_actions) {
    fl_value_append_take(list, fl_value_new_string(a.c_str()));
  }
  fl_value_set_string_take(map, "down", list);

  g_autoptr(GError) error = nullptr;
  fl_event_channel_send(self->key_channel, map, nullptr, &error);
  fl_value_unref(map);
}

static void SendHookStatus(DitoWin32Plugin* self, bool installed) {
  if (!self->key_channel_active || self->key_channel == nullptr) return;

  FlValue* map = fl_value_new_map();
  fl_value_set_string_take(map, "type", fl_value_new_string("hook"));
  fl_value_set_string_take(
      map, "status", fl_value_new_string(installed ? "installed" : "lost"));

  g_autoptr(GError) error = nullptr;
  fl_event_channel_send(self->key_channel, map, nullptr, &error);
  fl_value_unref(map);
}

static void SendTrayEvent(DitoWin32Plugin* self, const std::string& event,
                          const std::string& menu_id) {
  if (!self->tray_channel_active || self->tray_channel == nullptr) return;

  FlValue* map = fl_value_new_map();
  fl_value_set_string_take(map, "event", fl_value_new_string(event.c_str()));
  if (!menu_id.empty()) {
    fl_value_set_string_take(map, "id", fl_value_new_string(menu_id.c_str()));
  }

  g_autoptr(GError) error = nullptr;
  fl_event_channel_send(self->tray_channel, map, nullptr, &error);
  fl_value_unref(map);
}

static gboolean on_tick_timer(gpointer user_data) {
  DitoWin32Plugin* self = DITO_WIN32_PLUGIN(user_data);
  if (!self->key_channel_active || self->key_channel == nullptr || self->state == nullptr) {
    return G_SOURCE_CONTINUE;
  }

  const int64_t now = NowMicros();
  std::vector<std::string> down_actions;

  {
    std::lock_guard<std::mutex> lock(self->state->mutex);
    for (const auto& [action, down] : self->state->seen) {
      if (down) {
        down_actions.push_back(action);
      }
    }
  }

  SendKeyTick(self, down_actions, now);

  return G_SOURCE_CONTINUE;
}

static int X11ErrorHandler(Display* d, XErrorEvent* e) {
  return 0;
}

static void X11ThreadMain(DitoWin32Plugin* self) {
  XSetErrorHandler(X11ErrorHandler);
  Display* display = XOpenDisplay(nullptr);
  if (!display) return;

  const unsigned int modifiers[] = {
      0,
      Mod2Mask,
      LockMask,
      Mod2Mask | LockMask,
  };

  {
    std::lock_guard<std::mutex> lock(self->state->mutex);
    self->state->display = display;
    self->state->root_window = DefaultRootWindow(display);
    for (const auto& b : self->state->bindings) {
      for (unsigned int mod : modifiers) {
        XGrabKey(display, b.keycode, mod, self->state->root_window, True,
                 GrabModeAsync, GrabModeAsync);
      }
    }
    XFlush(display);
  }

  Bool supp = False;
  XkbSetDetectableAutoRepeat(display, True, &supp);

  int x11_fd = ConnectionNumber(display);
  struct pollfd pfd;
  pfd.fd = x11_fd;
  pfd.events = POLLIN;

  while (self->state && self->state->running) {
    while (XPending(display) > 0) {
      XEvent event;
      XNextEvent(display, &event);
      if (!self->state) break;
      self->state->pump_count++;

      if (event.type == KeyPress || event.type == KeyRelease) {
        self->state->seen_count++;
        const bool down = (event.type == KeyPress);
        const KeyCode kc = event.xkey.keycode;

        std::string match_action;
        std::string match_key;
        {
          std::lock_guard<std::mutex> lock(self->state->mutex);
          for (const auto& b : self->state->bindings) {
            if (b.keycode == kc) {
              match_action = b.action;
              match_key = b.key;
              self->state->seen[b.action] = down;
              break;
            }
          }
        }

        if (!match_action.empty() && !self->state->paused) {
          struct EdgeData {
            DitoWin32Plugin* plugin;
            std::string type;
            std::string action;
            std::string key;
            int64_t micros;
          };
          auto* d = new EdgeData{
              self, down ? "down" : "up", match_action, match_key, NowMicros()};

          g_idle_add(
              [](gpointer data) -> gboolean {
                auto* edge = static_cast<EdgeData*>(data);
                SendKeyEdge(edge->plugin, edge->type, edge->action, edge->key,
                            edge->micros);
                delete edge;
                return G_SOURCE_REMOVE;
              },
              d);
        }
      }
    }
    poll(&pfd, 1, 10);
  }

  XCloseDisplay(display);
  if (self->state) {
    std::lock_guard<std::mutex> lock(self->state->mutex);
    self->state->display = nullptr;
  }
}

static void GrabX11Key(DitoWin32Plugin* self, KeyCode kc) {
  if (!self->state) return;
  std::lock_guard<std::mutex> lock(self->state->mutex);
  if (!self->state->display) return;

  const unsigned int modifiers[] = {
      0,
      Mod2Mask,                  // NumLock
      LockMask,                  // CapsLock
      Mod2Mask | LockMask,       // NumLock + CapsLock
  };

  for (unsigned int mod : modifiers) {
    XGrabKey(self->state->display, kc, mod, self->state->root_window, True,
             GrabModeAsync, GrabModeAsync);
  }
  XFlush(self->state->display);
}

static void UngrabX11Key(DitoWin32Plugin* self, KeyCode kc) {
  if (!self->state) return;
  std::lock_guard<std::mutex> lock(self->state->mutex);
  if (!self->state->display) return;

  const unsigned int modifiers[] = {
      0,
      Mod2Mask,
      LockMask,
      Mod2Mask | LockMask,
  };

  for (unsigned int mod : modifiers) {
    XUngrabKey(self->state->display, kc, mod, self->state->root_window);
  }
  XFlush(self->state->display);
}

static void StartKeyHook(DitoWin32Plugin* self) {
  if (!self->state || self->state->running) return;
  self->state->running = true;
  self->state->thread = std::thread(X11ThreadMain, self);

  if (self->tick_timer_id == 0) {
    self->tick_timer_id = g_timeout_add(50, on_tick_timer, self);
  }
}

static void StopKeyHook(DitoWin32Plugin* self) {
  if (!self->state || !self->state->running) return;
  self->state->running = false;
  if (self->state->thread.joinable()) {
    self->state->thread.join();
  }
  if (self->tick_timer_id != 0) {
    g_source_remove(self->tick_timer_id);
    self->tick_timer_id = 0;
  }
}

static void dito_win32_plugin_dispose(GObject* object) {
  DitoWin32Plugin* self = DITO_WIN32_PLUGIN(object);

  self->key_channel_active = FALSE;
  self->tray_channel_active = FALSE;
  StopKeyHook(self);

  if (self->registrar != nullptr) {
    g_clear_object(&self->registrar);
  }
  if (self->method_channel != nullptr) {
    g_clear_object(&self->method_channel);
  }
  if (self->key_channel != nullptr) {
    g_clear_object(&self->key_channel);
  }
  if (self->tray_channel != nullptr) {
    g_clear_object(&self->tray_channel);
  }
  if (self->state != nullptr) {
    if (self->state->app_indicator && g_indicator_lib.set_status) {
      g_indicator_lib.set_status(self->state->app_indicator, 0); // PASSIVE
    }
    delete self->state;
    self->state = nullptr;
  }

  G_OBJECT_CLASS(dito_win32_plugin_parent_class)->dispose(object);
}

static void dito_win32_plugin_class_init(DitoWin32PluginClass* klass) {
  G_OBJECT_CLASS(klass)->dispose = dito_win32_plugin_dispose;
}

static void dito_win32_plugin_init(DitoWin32Plugin* self) {
  self->registrar = nullptr;
  self->method_channel = nullptr;
  self->key_channel = nullptr;
  self->tray_channel = nullptr;
  self->key_channel_active = FALSE;
  self->tray_channel_active = FALSE;
  self->tick_timer_id = 0;
  self->state = new PluginState();
}

struct MenuCallbackData {
  DitoWin32Plugin* plugin;
  std::string id;
};

static void on_menu_item_activate(GtkMenuItem* item, gpointer user_data) {
  auto* data = static_cast<MenuCallbackData*>(user_data);
  if (data && data->plugin) {
    SendTrayEvent(data->plugin, "menu", data->id);
  }
}

static GtkWindow* GetToplevel(DitoWin32Plugin* self) {
  if (!self->registrar) return nullptr;
  FlView* view = fl_plugin_registrar_get_view(self->registrar);
  if (!view) return nullptr;
  GtkWidget* win = gtk_widget_get_toplevel(GTK_WIDGET(view));
  return (win && GTK_IS_WINDOW(win)) ? GTK_WINDOW(win) : nullptr;
}

// EWMH property is the WM's single "what has focus" concept, read cooperatively instead of raced.
static Window ReadNetActiveWindow(Display* display) {
  if (!display) return 0;
  Atom net_active = XInternAtom(display, "_NET_ACTIVE_WINDOW", True);
  if (net_active == None) return 0;

  Atom actual_type;
  int actual_format;
  unsigned long n_items, bytes_after;
  unsigned char* prop = nullptr;
  Window result = 0;

  if (XGetWindowProperty(display, DefaultRootWindow(display), net_active, 0, 1,
                         False, XA_WINDOW, &actual_type, &actual_format,
                         &n_items, &bytes_after, &prop) == Success &&
      prop != nullptr) {
    if (actual_type == XA_WINDOW && n_items == 1) {
      result = *reinterpret_cast<Window*>(prop);
    }
    XFree(prop);
  }
  return result;
}

static void RequestActivateWindow(Display* display, Window target) {
  if (!display || target == 0) return;
  Atom net_active = XInternAtom(display, "_NET_ACTIVE_WINDOW", False);

  XEvent event = {};
  event.xclient.type = ClientMessage;
  event.xclient.send_event = True;
  event.xclient.display = display;
  event.xclient.window = target;
  event.xclient.message_type = net_active;
  event.xclient.format = 32;
  event.xclient.data.l[0] = 1;  // source indication: normal application

  XSendEvent(display, DefaultRootWindow(display), False,
             SubstructureRedirectMask | SubstructureNotifyMask, &event);
  XFlush(display);
}

static void method_call_cb(FlMethodChannel* channel, FlMethodCall* method_call,
                           gpointer user_data) {
  DitoWin32Plugin* self = DITO_WIN32_PLUGIN(user_data);
  const gchar* method = fl_method_call_get_name(method_call);
  FlValue* args = fl_method_call_get_args(method_call);

  if (g_strcmp0(method, "keys.bind") == 0) {
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* name_val = fl_value_lookup_string(args, "name");
      FlValue* key_val = fl_value_lookup_string(args, "key");
      FlValue* sup_val = fl_value_lookup_string(args, "suppress");

      const std::string action = name_val ? fl_value_get_string(name_val) : "";
      const std::string key = key_val ? fl_value_get_string(key_val) : "";
      const bool suppress = sup_val ? fl_value_get_bool(sup_val) : false;

      if (!action.empty() && !key.empty() && self->state) {
        Display* d = XOpenDisplay(nullptr);
        if (d) {
          KeySym sym = KeySymFromName(key);
          if (sym != NoSymbol) {
            KeyCode kc = XKeysymToKeycode(d, sym);
            if (kc != 0) {
              {
                std::lock_guard<std::mutex> lock(self->state->mutex);
                self->state->bindings.push_back({action, key, kc, suppress});
              }
              GrabX11Key(self, kc);
            }
          }
          XCloseDisplay(d);
        }
      }
    }
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "keys.unbind") == 0) {
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP && self->state) {
      FlValue* name_val = fl_value_lookup_string(args, "name");
      const std::string action = name_val ? fl_value_get_string(name_val) : "";
      if (!action.empty()) {
        std::lock_guard<std::mutex> lock(self->state->mutex);
        for (auto it = self->state->bindings.begin(); it != self->state->bindings.end();) {
          if (it->action == action) {
            UngrabX11Key(self, it->keycode);
            it = self->state->bindings.erase(it);
          } else {
            ++it;
          }
        }
      }
    }
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "keys.unbindAll") == 0) {
    if (self->state) {
      std::lock_guard<std::mutex> lock(self->state->mutex);
      for (const auto& b : self->state->bindings) {
        UngrabX11Key(self, b.keycode);
      }
      self->state->bindings.clear();
      self->state->seen.clear();
    }
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "keys.pause") == 0) {
    if (self->state) self->state->paused = true;
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "keys.resume") == 0) {
    if (self->state) self->state->paused = false;
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "keys.snapshot") == 0) {
    g_autoptr(FlValue) result = fl_value_new_map();
    if (self->state) {
      std::lock_guard<std::mutex> lock(self->state->mutex);
      fl_value_set_string_take(result, "_installed",
                               fl_value_new_bool(self->state->running));
      fl_value_set_string_take(result, "_seen",
                               fl_value_new_int(self->state->seen_count));
      fl_value_set_string_take(result, "_pump",
                               fl_value_new_int(self->state->pump_count));
      fl_value_set_string_take(result, "_paused",
                               fl_value_new_bool(self->state->paused));
      for (const auto& [action, down] : self->state->seen) {
        fl_value_set_string_take(result, action.c_str(), fl_value_new_bool(down));
      }
    } else {
      fl_value_set_string_take(result, "_installed", fl_value_new_bool(FALSE));
    }
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "keys.stats") == 0) {
    g_autoptr(FlValue) result = fl_value_new_map();
    if (self->state) {
      fl_value_set_string_take(result, "hookInstalled",
                               fl_value_new_bool(self->state->running));
      fl_value_set_string_take(result, "paused",
                               fl_value_new_bool(self->state->paused));
      fl_value_set_string_take(result, "seenEvents",
                               fl_value_new_int(self->state->seen_count));
      fl_value_set_string_take(result, "pumpEvents",
                               fl_value_new_int(self->state->pump_count));
    }
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "clipboard.get") == 0) {
    GtkClipboard* clip = gtk_clipboard_get(GDK_SELECTION_CLIPBOARD);
    gchar* text = gtk_clipboard_wait_for_text(clip);
    g_autoptr(FlValue) result =
        text ? fl_value_new_string(text) : fl_value_new_null();
    if (text) g_free(text);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "clipboard.set") == 0) {
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* text_val = fl_value_lookup_string(args, "text");
      if (text_val && fl_value_get_type(text_val) == FL_VALUE_TYPE_STRING) {
        const gchar* text = fl_value_get_string(text_val);
        GtkClipboard* clip = gtk_clipboard_get(GDK_SELECTION_CLIPBOARD);
        gtk_clipboard_set_text(clip, text, -1);
      }
    }
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "input.sendCtrlV") == 0 ||
      g_strcmp0(method, "paste.ctrl_v") == 0) {
    g_spawn_command_line_async("xdotool key --clearmodifiers ctrl+v", nullptr);
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "input.sendEnter") == 0 ||
      g_strcmp0(method, "paste.enter") == 0) {
    g_spawn_command_line_async("xdotool key --clearmodifiers Return", nullptr);
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "input.sendChord") == 0) {
    std::string key;
    bool ctrl = true;
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* key_val = fl_value_lookup_string(args, "key");
      FlValue* ctrl_val = fl_value_lookup_string(args, "ctrl");
      if (key_val && fl_value_get_type(key_val) == FL_VALUE_TYPE_STRING) {
        key = fl_value_get_string(key_val);
        for (auto& c : key) c = tolower(c);
      }
      if (ctrl_val) ctrl = fl_value_get_bool(ctrl_val);
    }
    if (!key.empty()) {
      std::string cmd = "xdotool key --clearmodifiers " +
                        std::string(ctrl ? "ctrl+" : "") + key;
      g_spawn_command_line_async(cmd.c_str(), nullptr);
    }
    g_autoptr(FlValue) result = fl_value_new_bool(!key.empty());
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "focus.take") == 0) {
    GtkWindow* win = GetToplevel(self);
    if (win && self->state) {
      GdkDisplay* gdk_display = gtk_widget_get_display(GTK_WIDGET(win));
      Display* display = GDK_DISPLAY_XDISPLAY(gdk_display);
      Window self_xid = GDK_WINDOW_XID(gtk_widget_get_window(GTK_WIDGET(win)));
      Window current = ReadNetActiveWindow(display);
      // Never remember ourselves — mirrors the Windows plugin's same guard.
      self->state->saved_focus_target = (current != self_xid) ? current : 0;
    }
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "focus.giveBack") == 0) {
    bool ok = false;
    GtkWindow* win = GetToplevel(self);
    if (win && self->state && self->state->saved_focus_target != 0) {
      GdkDisplay* gdk_display = gtk_widget_get_display(GTK_WIDGET(win));
      Display* display = GDK_DISPLAY_XDISPLAY(gdk_display);
      RequestActivateWindow(display, self->state->saved_focus_target);
      self->state->saved_focus_target = 0;
      ok = true;
    }
    g_autoptr(FlValue) result = fl_value_new_bool(ok);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "notify.balloon") == 0) {
    std::string title = "Dito", body;
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* t_val = fl_value_lookup_string(args, "title");
      if (t_val && fl_value_get_type(t_val) == FL_VALUE_TYPE_STRING) title = fl_value_get_string(t_val);
      FlValue* b_val = fl_value_lookup_string(args, "body");
      if (b_val && fl_value_get_type(b_val) == FL_VALUE_TYPE_STRING) body = fl_value_get_string(b_val);
    }
    const gchar* argv[] = {"notify-send", "--app-name=Dito", title.c_str(), body.c_str(), nullptr};
    g_autoptr(GError) error = nullptr;
    bool ok = g_spawn_async(nullptr, const_cast<gchar**>(argv), nullptr, G_SPAWN_SEARCH_PATH,
                             nullptr, nullptr, nullptr, &error);
    if (!ok) g_warning("notify-send falhou: %s", error->message);
    g_autoptr(FlValue) result = fl_value_new_bool(ok);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "notify.alarmSound") == 0) {
    // paplay ignores the desktop "event sounds" toggle; canberra-gtk-play silently
    // no-ops when that toggle is off, so this alarm would never make a sound on
    // Windows either since PlaySound() there also does not check a UI-sound setting.
    const gchar* argv[] = {"paplay", "/usr/share/sounds/freedesktop/stereo/dialog-warning.oga",
                            nullptr};
    g_autoptr(GError) error = nullptr;
    bool ok = g_spawn_async(nullptr, const_cast<gchar**>(argv), nullptr, G_SPAWN_SEARCH_PATH,
                             nullptr, nullptr, nullptr, &error);
    if (!ok) g_warning("paplay falhou: %s", error->message);
    g_autoptr(FlValue) result = fl_value_new_bool(ok);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "notify") == 0) {
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  // --- WINDOW API ---
  if (g_strcmp0(method, "window.adoptAsHud") == 0) {
    GtkWindow* win = GetToplevel(self);
    if (!win) {
      fl_method_call_respond_error(method_call, "NO_WINDOW", "sem janela nativa", nullptr, nullptr);
      return;
    }
    gtk_window_set_accept_focus(win, FALSE);
    gtk_window_set_focus_on_map(win, FALSE);
    gtk_window_set_keep_above(win, TRUE);
    gtk_window_set_decorated(win, FALSE);
    gtk_window_set_skip_taskbar_hint(win, TRUE);
    // Dart calls invokeMethod<int>: must return an int, matching the HWND-as-int64 on Windows.
    g_autoptr(FlValue) result = fl_value_new_int(reinterpret_cast<intptr_t>(win));
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "window.adoptAsPanel") == 0) {
    GtkWindow* win = GetToplevel(self);
    if (!win) {
      fl_method_call_respond_error(method_call, "NO_WINDOW", "sem janela nativa", nullptr, nullptr);
      return;
    }
    gtk_window_set_keep_above(win, TRUE);
    gtk_window_set_decorated(win, FALSE);
    gtk_window_set_skip_taskbar_hint(win, TRUE);
    g_autoptr(FlValue) result = fl_value_new_int(reinterpret_cast<intptr_t>(win));
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "window.showNoActivate") == 0 ||
      g_strcmp0(method, "window.focus") == 0) {
    GtkWindow* win = GetToplevel(self);
    if (!win) {
      // This used to always respond TRUE here, so a null toplevel made show() a silent no-op.
      g_warning("%s: sem janela nativa (toplevel nulo)", method);
      fl_method_call_respond_error(method_call, "NO_WINDOW", "sem janela nativa", nullptr, nullptr);
      return;
    }
    gtk_widget_show_all(GTK_WIDGET(win));
    gtk_window_present(win);
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "window.hide") == 0) {
    GtkWindow* win = GetToplevel(self);
    if (!win) {
      g_warning("window.hide: sem janela nativa (toplevel nulo)");
      fl_method_call_respond_error(method_call, "NO_WINDOW", "sem janela nativa", nullptr, nullptr);
      return;
    }
    gtk_widget_hide(GTK_WIDGET(win));
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "window.setHitRect") == 0) {
    GtkWindow* win = GetToplevel(self);
    bool ok = false;
    if (win) {
      double left = 0, top = 0, width = 0, height = 0, radius = 0;
      if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
        auto num = [&](const char* k) -> double {
          FlValue* v = fl_value_lookup_string(args, k);
          if (!v) return 0;
          if (fl_value_get_type(v) == FL_VALUE_TYPE_FLOAT) return fl_value_get_float(v);
          if (fl_value_get_type(v) == FL_VALUE_TYPE_INT) return (double)fl_value_get_int(v);
          return 0;
        };
        left = num("left");
        top = num("top");
        width = num("width");
        height = num("height");
        radius = num("radius");
      }
      if (width > 0 && height > 0) {
        cairo_region_t* region;
        if (radius > 0) {
          // cairo has no rounded-rect region builder; two unioned rects approximate it.
          cairo_rectangle_int_t body = {(int)left, (int)(top + radius),
                                        (int)width, (int)(height - 2 * radius)};
          region = cairo_region_create_rectangle(&body);
          cairo_rectangle_int_t mid = {(int)(left + radius), (int)top,
                                       (int)(width - 2 * radius), (int)height};
          cairo_region_t* mid_region = cairo_region_create_rectangle(&mid);
          cairo_region_union(region, mid_region);
          cairo_region_destroy(mid_region);
        } else {
          cairo_rectangle_int_t rect = {(int)left, (int)top, (int)width, (int)height};
          region = cairo_region_create_rectangle(&rect);
        }
        // Input shape only — the bounding shape fights Flutter's own GL swapchain compositing.
        gtk_widget_input_shape_combine_region(GTK_WIDGET(win), region);
        cairo_region_destroy(region);
      } else {
        gtk_widget_input_shape_combine_region(GTK_WIDGET(win), nullptr);
      }
      ok = true;
    }
    g_autoptr(FlValue) result = fl_value_new_bool(ok);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "window.rect") == 0) {
    int x = 0, y = 0, w = 0, h = 0;
    GtkWindow* win = GetToplevel(self);
    if (win) {
      gtk_window_get_position(win, &x, &y);
      gtk_window_get_size(win, &w, &h);
    }
    g_autoptr(FlValue) result = fl_value_new_map();
    fl_value_set_string_take(result, "left", fl_value_new_int(x));
    fl_value_set_string_take(result, "top", fl_value_new_int(y));
    fl_value_set_string_take(result, "right", fl_value_new_int(x + w));
    fl_value_set_string_take(result, "bottom", fl_value_new_int(y + h));
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "window.handle") == 0) {
    int64_t self_xid = 0, foreground_xid = 0;
    GtkWindow* win = GetToplevel(self);
    if (win) {
      GdkDisplay* gdk_display = gtk_widget_get_display(GTK_WIDGET(win));
      Display* display = GDK_DISPLAY_XDISPLAY(gdk_display);
      self_xid = (int64_t)GDK_WINDOW_XID(gtk_widget_get_window(GTK_WIDGET(win)));
      foreground_xid = (int64_t)ReadNetActiveWindow(display);
    }
    g_autoptr(FlValue) result = fl_value_new_map();
    fl_value_set_string_take(result, "self", fl_value_new_int(self_xid));
    fl_value_set_string_take(result, "foreground", fl_value_new_int(foreground_xid));
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "window.setBottomCenter") == 0) {
    int w = 560, h = 180;
    int margin = 32;
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* wv = fl_value_lookup_string(args, "width");
      FlValue* hv = fl_value_lookup_string(args, "height");
      FlValue* mv = fl_value_lookup_string(args, "margin");
      if (wv) {
        if (fl_value_get_type(wv) == FL_VALUE_TYPE_FLOAT) w = (int)fl_value_get_float(wv);
        else if (fl_value_get_type(wv) == FL_VALUE_TYPE_INT) w = (int)fl_value_get_int(wv);
      }
      if (hv) {
        if (fl_value_get_type(hv) == FL_VALUE_TYPE_FLOAT) h = (int)fl_value_get_float(hv);
        else if (fl_value_get_type(hv) == FL_VALUE_TYPE_INT) h = (int)fl_value_get_int(hv);
      }
      if (mv) {
        if (fl_value_get_type(mv) == FL_VALUE_TYPE_FLOAT) margin = (int)fl_value_get_float(mv);
        else if (fl_value_get_type(mv) == FL_VALUE_TYPE_INT) margin = (int)fl_value_get_int(mv);
      }
    }
    int x = 0, y = 0;
    GtkWindow* win = GetToplevel(self);
    if (win) {
      GdkDisplay* display = gtk_widget_get_display(GTK_WIDGET(win));
      GdkMonitor* monitor = gdk_display_get_primary_monitor(display);
      if (!monitor) {
        monitor = gdk_display_get_monitor_at_window(display, gtk_widget_get_window(GTK_WIDGET(win)));
      }
      GdkRectangle geom = {0, 0, 1920, 1080};
      if (monitor) gdk_monitor_get_geometry(monitor, &geom);
      x = geom.x + (geom.width - w) / 2;
      y = geom.y + geom.height - h - margin;
      gtk_window_resize(win, w, h);
      gtk_window_move(win, x, y);
    }
    g_autoptr(FlValue) result = fl_value_new_map();
    fl_value_set_string_take(result, "x", fl_value_new_float((double)x));
    fl_value_set_string_take(result, "y", fl_value_new_float((double)y));
    fl_value_set_string_take(result, "w", fl_value_new_float((double)w));
    fl_value_set_string_take(result, "h", fl_value_new_float((double)h));
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  // --- TRAY API ---
  if (g_strcmp0(method, "tray.create") == 0) {
    bool ok = false;
    if (g_indicator_lib.Load() && self->state) {
      if (!self->state->app_indicator) {
        self->state->app_indicator = g_indicator_lib.ind_new(
            "dito", "dito", 0 /* APPLICATION_STATUS */);
      }
      if (self->state->app_indicator) {
        if (g_indicator_lib.set_icon_theme_path) {
          g_indicator_lib.set_icon_theme_path(
              self->state->app_indicator, "/usr/share/icons/hicolor/scalable/apps");
        }
        // Set an initial menu so AppIndicator displays immediately
        GtkWidget* menu = gtk_menu_new();
        GtkWidget* item_open = gtk_menu_item_new_with_label("Abrir Dito");
        auto* cb_open = new MenuCallbackData{self, "open"};
        g_signal_connect_data(
            item_open, "activate", G_CALLBACK(on_menu_item_activate), cb_open,
            [](gpointer d, GClosure*) { delete static_cast<MenuCallbackData*>(d); },
            (GConnectFlags)0);
        gtk_menu_shell_append(GTK_MENU_SHELL(menu), item_open);

        GtkWidget* item_quit = gtk_menu_item_new_with_label("Sair");
        auto* cb_quit = new MenuCallbackData{self, "quit"};
        g_signal_connect_data(
            item_quit, "activate", G_CALLBACK(on_menu_item_activate), cb_quit,
            [](gpointer d, GClosure*) { delete static_cast<MenuCallbackData*>(d); },
            (GConnectFlags)0);
        gtk_menu_shell_append(GTK_MENU_SHELL(menu), item_quit);

        gtk_widget_show_all(menu);
        g_indicator_lib.set_menu(self->state->app_indicator, GTK_MENU(menu));
        self->state->current_menu = menu;

        g_indicator_lib.set_status(self->state->app_indicator, 1 /* ACTIVE */);
        ok = true;
      }
    }
    g_autoptr(FlValue) result = fl_value_new_bool(ok);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "tray.setIcon") == 0) {
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP && self->state && self->state->app_indicator) {
      FlValue* p_val = fl_value_lookup_string(args, "path");
      if (p_val && fl_value_get_type(p_val) == FL_VALUE_TYPE_STRING) {
        const gchar* path = fl_value_get_string(p_val);
        std::string s_path(path);
        size_t last_slash = s_path.find_last_of("/\\");
        if (last_slash != std::string::npos && g_indicator_lib.set_icon_theme_path) {
          std::string dir = s_path.substr(0, last_slash);
          std::string file = s_path.substr(last_slash + 1);
          size_t dot = file.find_last_of('.');
          std::string icon_name = (dot != std::string::npos) ? file.substr(0, dot) : file;
          g_indicator_lib.set_icon_theme_path(self->state->app_indicator, dir.c_str());
          g_indicator_lib.set_icon_full(self->state->app_indicator, icon_name.c_str(), "Dito");
        } else {
          g_indicator_lib.set_icon_full(self->state->app_indicator, path, "Dito");
        }
      }
    }
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "tray.setTooltip") == 0) {
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP && self->state && self->state->app_indicator) {
      FlValue* t_val = fl_value_lookup_string(args, "tooltip");
      if (t_val && fl_value_get_type(t_val) == FL_VALUE_TYPE_STRING && g_indicator_lib.set_title) {
        const gchar* tooltip = fl_value_get_string(t_val);
        g_indicator_lib.set_title(self->state->app_indicator, tooltip);
      }
    }
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "tray.setMenu") == 0) {
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP && self->state && self->state->app_indicator) {
      FlValue* items_val = fl_value_lookup_string(args, "items");
      if (items_val && fl_value_get_type(items_val) == FL_VALUE_TYPE_LIST) {
        GtkWidget* menu = gtk_menu_new();
        const size_t count = fl_value_get_length(items_val);
        for (size_t i = 0; i < count; ++i) {
          FlValue* item_val = fl_value_get_list_value(items_val, i);
          if (fl_value_get_type(item_val) != FL_VALUE_TYPE_MAP) continue;

          FlValue* id_v = fl_value_lookup_string(item_val, "id");
          FlValue* label_v = fl_value_lookup_string(item_val, "label");
          FlValue* enabled_v = fl_value_lookup_string(item_val, "enabled");
          FlValue* checked_v = fl_value_lookup_string(item_val, "checked");
          FlValue* is_chk_v = fl_value_lookup_string(item_val, "checkbox");
          FlValue* is_sep_v = fl_value_lookup_string(item_val, "separator");

          const std::string id = (id_v && fl_value_get_type(id_v) == FL_VALUE_TYPE_STRING)
                                     ? fl_value_get_string(id_v)
                                     : "";
          const std::string label = (label_v && fl_value_get_type(label_v) == FL_VALUE_TYPE_STRING)
                                        ? fl_value_get_string(label_v)
                                        : "";
          const bool enabled = enabled_v ? fl_value_get_bool(enabled_v) : true;
          const bool checked = checked_v ? fl_value_get_bool(checked_v) : false;
          const bool is_chk = is_chk_v ? fl_value_get_bool(is_chk_v) : false;
          const bool is_sep = is_sep_v ? fl_value_get_bool(is_sep_v) : false;

          GtkWidget* mi = nullptr;
          if (is_sep) {
            mi = gtk_separator_menu_item_new();
          } else if (is_chk) {
            mi = gtk_check_menu_item_new_with_label(label.c_str());
            gtk_check_menu_item_set_active(GTK_CHECK_MENU_ITEM(mi), checked);
          } else {
            mi = gtk_menu_item_new_with_label(label.c_str());
          }

          gtk_widget_set_sensitive(mi, enabled);

          if (!id.empty()) {
            auto* cb_data = new MenuCallbackData{self, id};
            g_signal_connect_data(
                mi, "activate", G_CALLBACK(on_menu_item_activate), cb_data,
                [](gpointer data, GClosure*) {
                  delete static_cast<MenuCallbackData*>(data);
                },
                (GConnectFlags)0);
          }

          gtk_menu_shell_append(GTK_MENU_SHELL(menu), mi);
        }
        gtk_widget_show_all(menu);
        g_indicator_lib.set_menu(self->state->app_indicator, GTK_MENU(menu));
        self->state->current_menu = menu;
      }
    }
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "tray.destroy") == 0) {
    if (self->state && self->state->app_indicator && g_indicator_lib.set_status) {
      g_indicator_lib.set_status(self->state->app_indicator, 0); // PASSIVE
      self->state->app_indicator = nullptr;
    }
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  fl_method_call_respond_not_implemented(method_call, nullptr);
}

static FlMethodErrorResponse* key_channel_listen(FlEventChannel* channel,
                                                 FlValue* args,
                                                 gpointer user_data) {
  DitoWin32Plugin* self = DITO_WIN32_PLUGIN(user_data);
  self->key_channel_active = TRUE;
  SendHookStatus(self, true);
  return nullptr;
}

static FlMethodErrorResponse* key_channel_cancel(FlEventChannel* channel,
                                                 FlValue* args,
                                                 gpointer user_data) {
  DitoWin32Plugin* self = DITO_WIN32_PLUGIN(user_data);
  self->key_channel_active = FALSE;
  return nullptr;
}

static FlMethodErrorResponse* tray_channel_listen(FlEventChannel* channel,
                                                  FlValue* args,
                                                  gpointer user_data) {
  DitoWin32Plugin* self = DITO_WIN32_PLUGIN(user_data);
  self->tray_channel_active = TRUE;
  return nullptr;
}

static FlMethodErrorResponse* tray_channel_cancel(FlEventChannel* channel,
                                                  FlValue* args,
                                                  gpointer user_data) {
  DitoWin32Plugin* self = DITO_WIN32_PLUGIN(user_data);
  self->tray_channel_active = FALSE;
  return nullptr;
}

void dito_win32_plugin_register_with_registrar(
    FlPluginRegistrar* registrar) {
  // This registrar fires once per window (main+HUD+Review); XInitThreads() only needs one call.
  static std::once_flag x11_threads_init;
  std::call_once(x11_threads_init, [] { XInitThreads(); });

  DitoWin32Plugin* plugin = DITO_WIN32_PLUGIN(
      g_object_new(dito_win32_plugin_get_type(), nullptr));
  // Unreffed, this dangles once the caller's own registrar reference drops.
  plugin->registrar = FL_PLUGIN_REGISTRAR(g_object_ref(registrar));

  FlBinaryMessenger* messenger = fl_plugin_registrar_get_messenger(registrar);

  g_autoptr(FlStandardMethodCodec) method_codec = fl_standard_method_codec_new();
  plugin->method_channel = fl_method_channel_new(
      messenger, "dito/win32", FL_METHOD_CODEC(method_codec));
  fl_method_channel_set_method_call_handler(
      plugin->method_channel, method_call_cb, g_object_ref(plugin), g_object_unref);

  g_autoptr(FlStandardMethodCodec) key_codec = fl_standard_method_codec_new();
  plugin->key_channel = fl_event_channel_new(
      messenger, "dito/keys", FL_METHOD_CODEC(key_codec));
  fl_event_channel_set_stream_handlers(
      plugin->key_channel, key_channel_listen, key_channel_cancel,
      g_object_ref(plugin), g_object_unref);

  g_autoptr(FlStandardMethodCodec) tray_codec = fl_standard_method_codec_new();
  plugin->tray_channel = fl_event_channel_new(
      messenger, "dito/tray", FL_METHOD_CODEC(tray_codec));
  fl_event_channel_set_stream_handlers(
      plugin->tray_channel, tray_channel_listen, tray_channel_cancel,
      g_object_ref(plugin), g_object_unref);

  StartKeyHook(plugin);

  g_object_unref(plugin);
}
