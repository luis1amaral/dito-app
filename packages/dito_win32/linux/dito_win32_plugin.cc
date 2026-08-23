#include "include/dito_win32/dito_win32_plugin.h"

#include <flutter_linux/flutter_linux.h>
#include <gtk/gtk.h>
#include <gdk/gdkx.h>
#include <sys/utsname.h>
#include <dlfcn.h>

#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/XKBlib.h>
#include <X11/Xatom.h>
#include <X11/keysym.h>
#include <poll.h>

#include <algorithm>
#include <cmath>
#include <atomic>
#include <cctype>
#include <chrono>
#include <functional>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <tuple>
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
  bool grabbed{false};
};

// XGrabKey is exclusive: another client holding F9/F10 makes ours fail, and X reports it only here.
std::atomic<int64_t> g_x11_error_count{0};

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

  // Grab/ungrab happen only on the X11 thread; other threads leave work here.
  std::vector<KeyCode> pending_ungrab;
  std::atomic<bool> sync_now{false};

  // Mirrors GetForegroundWindow() bookkeeping on the Windows plugin (focus.take/giveBack).
  Window saved_focus_target{0};
  Window last_paste_target{0};

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

// One keyboard hook per PROCESS, never per window: a separate XOpenDisplay per window means separate X clients fighting for the exclusive XGrabKey (docs/armadilhas.md 2.1).
static PluginState* SharedKeyState() {
  static PluginState* shared = new PluginState();
  return shared;
}

static std::mutex g_plugins_mutex;
static std::vector<DitoWin32Plugin*> g_plugins;

/// Keys reach every registered window: only the main one listens, and it is not always the first.
static void ForEachKeyChannel(const std::function<void(DitoWin32Plugin*)>& send) {
  std::vector<DitoWin32Plugin*> targets;
  {
    std::lock_guard<std::mutex> lock(g_plugins_mutex);
    for (DitoWin32Plugin* p : g_plugins) {
      if (p->key_channel_active && p->key_channel != nullptr) targets.push_back(p);
    }
  }
  for (DitoWin32Plugin* p : targets) send(p);
}

static void SendKeyEdgeTo(DitoWin32Plugin* self, const std::string& type,
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

static void SendKeyEdge(DitoWin32Plugin*, const std::string& type,
                        const std::string& action, const std::string& key,
                        int64_t micros) {
  ForEachKeyChannel([&](DitoWin32Plugin* p) {
    SendKeyEdgeTo(p, type, action, key, micros);
  });
}

static void SendKeyTickTo(DitoWin32Plugin* self,
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

static void SendKeyTick(DitoWin32Plugin*,
                        const std::vector<std::string>& down_actions,
                        int64_t micros) {
  ForEachKeyChannel([&](DitoWin32Plugin* p) {
    SendKeyTickTo(p, down_actions, micros);
  });
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
  g_x11_error_count.fetch_add(1);
  g_warning("dito: erro do X (code=%d, request=%d) — tecla global pode estar tomada",
            e->error_code, e->request_code);
  return 0;
}

static int X11IOErrorHandler(Display* d) {
  g_warning("dito: conexao com o X caiu");
  return 0;
}

// Returns false when another client already holds the key (BadAccess); X11 thread only.
static bool GrabOnThread(PluginState* state, KeyCode kc) {
  static const unsigned int modifiers[] = {
      0,
      Mod2Mask,                  // NumLock
      LockMask,                  // CapsLock
      Mod2Mask | LockMask,       // NumLock + CapsLock
  };

  const int64_t before = g_x11_error_count.load();
  for (unsigned int mod : modifiers) {
    XGrabKey(state->display, kc, mod, state->root_window, True, GrabModeAsync,
             GrabModeAsync);
  }
  XSync(state->display, False);
  return g_x11_error_count.load() == before;
}

static void SendGrabStatusTo(DitoWin32Plugin* self, const std::string& action,
                             const std::string& key, bool ok) {
  if (!self->key_channel_active || self->key_channel == nullptr) return;

  FlValue* map = fl_value_new_map();
  fl_value_set_string_take(map, "type", fl_value_new_string("grab"));
  fl_value_set_string_take(map, "name", fl_value_new_string(action.c_str()));
  fl_value_set_string_take(map, "key", fl_value_new_string(key.c_str()));
  fl_value_set_string_take(map, "ok", fl_value_new_bool(ok));

  g_autoptr(GError) error = nullptr;
  fl_event_channel_send(self->key_channel, map, nullptr, &error);
  fl_value_unref(map);
}

static void SendGrabStatus(DitoWin32Plugin*, const std::string& action,
                           const std::string& key, bool ok) {
  ForEachKeyChannel([&](DitoWin32Plugin* p) {
    SendGrabStatusTo(p, action, key, ok);
  });
}

// Grab result travels to Dart on the main loop, same trip the key edges take.
static void PostGrabStatus(DitoWin32Plugin* self, const std::string& action,
                           const std::string& key, bool ok) {
  struct GrabData {
    DitoWin32Plugin* plugin;
    std::string action;
    std::string key;
    bool ok;
  };
  auto* d = new GrabData{self, action, key, ok};
  g_idle_add(
      [](gpointer data) -> gboolean {
        auto* g = static_cast<GrabData*>(data);
        SendGrabStatus(g->plugin, g->action, g->key, g->ok);
        delete g;
        return G_SOURCE_REMOVE;
      },
      d);
}

// Grabs every binding that is not held yet; called on the X11 thread, retried while it fails.
static void SyncGrabsOnThread(DitoWin32Plugin* self) {
  PluginState* state = self->state;
  std::vector<KeyCode> ungrab;
  std::vector<std::tuple<std::string, std::string, KeyCode>> to_grab;

  {
    std::lock_guard<std::mutex> lock(state->mutex);
    ungrab.swap(state->pending_ungrab);
    for (const auto& b : state->bindings) {
      if (!b.grabbed) to_grab.emplace_back(b.action, b.key, b.keycode);
    }
  }

  static const unsigned int modifiers[] = {0, Mod2Mask, LockMask,
                                           Mod2Mask | LockMask};
  for (const KeyCode kc : ungrab) {
    for (unsigned int mod : modifiers) {
      XUngrabKey(state->display, kc, mod, state->root_window);
    }
  }
  if (!ungrab.empty()) XFlush(state->display);

  for (const auto& [action, key, kc] : to_grab) {
    const bool ok = GrabOnThread(state, kc);
    bool changed = false;
    {
      std::lock_guard<std::mutex> lock(state->mutex);
      for (auto& b : state->bindings) {
        if (b.keycode == kc && b.action == action && b.grabbed != ok) {
          b.grabbed = ok;
          changed = true;
        }
      }
    }
    if (changed || !ok) PostGrabStatus(self, action, key, ok);
  }
}

static void X11ThreadMain(DitoWin32Plugin* self) {
  XSetErrorHandler(X11ErrorHandler);
  XSetIOErrorHandler(X11IOErrorHandler);
  Display* display = XOpenDisplay(nullptr);
  if (!display) {
    self->state->running = false;
    g_warning("dito: XOpenDisplay falhou — teclas globais fora do ar");
    return;
  }

  {
    std::lock_guard<std::mutex> lock(self->state->mutex);
    self->state->display = display;
    self->state->root_window = DefaultRootWindow(display);
  }
  SyncGrabsOnThread(self);

  Bool supp = False;
  XkbSetDetectableAutoRepeat(display, True, &supp);

  int x11_fd = ConnectionNumber(display);
  struct pollfd pfd;
  pfd.fd = x11_fd;
  pfd.events = POLLIN;

  int64_t ticks_since_sync = 0;
  while (self->state && self->state->running) {
    // ~2s: retries the grab a rival client is holding; bind/unbind ask for it right away.
    if (++ticks_since_sync >= 200 || self->state->sync_now.exchange(false)) {
      ticks_since_sync = 0;
      SyncGrabsOnThread(self);
    }
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

// Bind/unbind from Dart only leave a mark; the X11 thread owns every Xlib call on this display.
static void RequestGrabSync(DitoWin32Plugin* self) {
  if (self->state) self->state->sync_now = true;
}

static void RequestUngrab(DitoWin32Plugin* self, KeyCode kc) {
  if (!self->state) return;
  {
    std::lock_guard<std::mutex> lock(self->state->mutex);
    self->state->pending_ungrab.push_back(kc);
  }
  self->state->sync_now = true;
}

// Idempotent across windows: the second and third registration only join the broadcast list.
static void StartKeyHook(DitoWin32Plugin* self) {
  {
    std::lock_guard<std::mutex> lock(g_plugins_mutex);
    if (std::find(g_plugins.begin(), g_plugins.end(), self) == g_plugins.end()) {
      g_plugins.push_back(self);
    }
  }
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

  // Closing one window must not take the shared hook down with it.
  bool alone = false;
  {
    std::lock_guard<std::mutex> lock(g_plugins_mutex);
    alone = g_plugins.size() <= 1;
  }
  if (alone) {
    StopKeyHook(self);
  } else if (self->tick_timer_id != 0) {
    g_source_remove(self->tick_timer_id);
    self->tick_timer_id = 0;
  }

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
  // The state is shared by every window now: only the LAST plugin standing may tear it down.
  bool last = false;
  {
    std::lock_guard<std::mutex> lock(g_plugins_mutex);
    g_plugins.erase(std::remove(g_plugins.begin(), g_plugins.end(), self), g_plugins.end());
    last = g_plugins.empty();
  }
  if (last && self->state != nullptr) {
    if (self->state->app_indicator && g_indicator_lib.set_status) {
      g_indicator_lib.set_status(self->state->app_indicator, 0); // PASSIVE
    }
  }
  self->state = nullptr;

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
  self->state = SharedKeyState();
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

// A single ISOLATED synthetic key (down only or up only), which the self-test needs and Ctrl+V does not cover.
static int InjectKeyForTest(const std::string& nome, bool down) {
  void* lib = dlopen("libXtst.so.6", RTLD_LAZY);
  if (!lib) return 0;
  auto fake_key = (int (*)(Display*, unsigned int, int, unsigned long))
      dlsym(lib, "XTestFakeKeyEvent");
  if (!fake_key) return 0;
  Display* d = XOpenDisplay(nullptr);
  if (!d) return 0;
  const KeyCode kc = XKeysymToKeycode(d, KeySymFromName(nome));
  int enviados = 0;
  if (kc != 0 && fake_key(d, kc, down ? True : False, 0)) enviados = 1;
  XFlush(d);
  XCloseDisplay(d);
  return enviados;
}

static GtkWindow* GetToplevel(DitoWin32Plugin* self) {
  if (!self->registrar) return nullptr;
  FlView* view = fl_plugin_registrar_get_view(self->registrar);
  if (!view) return nullptr;
  GtkWidget* win = gtk_widget_get_toplevel(GTK_WIDGET(view));
  return (win && GTK_IS_WINDOW(win)) ? GTK_WINDOW(win) : nullptr;
}

// Weak-pointer targets so a delayed tick can outlive the view/window without touching freed memory.
static void SetWindowOpacity(GtkWindow* win, bool opaque) {
  GdkWindow* gdk_win = gtk_widget_get_window(GTK_WIDGET(win));
  if (!gdk_win) return;
  Display* display = GDK_DISPLAY_XDISPLAY(gdk_window_get_display(gdk_win));
  Atom prop = XInternAtom(display, "_NET_WM_WINDOW_OPACITY", False);
  if (prop == None) return;
  unsigned long value = opaque ? 0xFFFFFFFFul : 0ul;
  XChangeProperty(display, GDK_WINDOW_XID(gdk_win), prop, XA_CARDINAL, 32,
                  PropModeReplace, reinterpret_cast<unsigned char*>(&value), 1);
  XFlush(display);
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

// Monitor of the window the dono is actually using, not the OS-wide "primary" that never moves.
static void RequestActivateWindow(Display* display, Window target, Time when = CurrentTime) {
  if (!display || target == 0) return;
  Atom net_active = XInternAtom(display, "_NET_ACTIVE_WINDOW", False);

  XEvent event = {};
  event.xclient.type = ClientMessage;
  event.xclient.send_event = True;
  event.xclient.display = display;
  event.xclient.window = target;
  event.xclient.message_type = net_active;
  event.xclient.format = 32;
  // Source 2 (pager): source 1 with a zero timestamp is what the WM drops as focus stealing.
  event.xclient.data.l[0] = 2;
  event.xclient.data.l[1] = static_cast<long>(when);
  event.xclient.data.l[2] = static_cast<long>(ReadNetActiveWindow(display));

  XSendEvent(display, DefaultRootWindow(display), False,
             SubstructureRedirectMask | SubstructureNotifyMask, &event);
  XFlush(display);
}

// Inspects WM_CLASS to determine if the target window is a Linux terminal emulator.
static bool IsTerminalWindow(Display* display, Window window) {
  if (!display || window == 0) return false;

  Window curr = window;
  for (int depth = 0; depth < 5 && curr != 0; ++depth) {
    XClassHint hint = {};
    if (XGetClassHint(display, curr, &hint) != 0) {
      std::string res_name = hint.res_name ? hint.res_name : "";
      std::string res_class = hint.res_class ? hint.res_class : "";
      if (hint.res_name) XFree(hint.res_name);
      if (hint.res_class) XFree(hint.res_class);

      for (auto& c : res_name) c = tolower(c);
      for (auto& c : res_class) c = tolower(c);

      static const char* const kTerminals[] = {
          "gnome-terminal", "gnome-terminal-server", "xterm", "alacritty",
          "kitty", "konsole", "xfce4-terminal", "tilix", "terminator",
          "urxvt", "foot", "st-256color", "wezterm", "mate-terminal",
          "lxterminal", "qterminal", "cinnamon-terminal"
      };

      for (const char* term : kTerminals) {
        if (res_name.find(term) != std::string::npos ||
            res_class.find(term) != std::string::npos) {
          return true;
        }
      }
      return false;
    }

    Window root = 0, parent = 0, *children = nullptr;
    unsigned int nchildren = 0;
    if (XQueryTree(display, curr, &root, &parent, &children, &nchildren) != 0) {
      if (children) XFree(children);
      if (parent == root || parent == curr) break;
      curr = parent;
    } else {
      break;
    }
  }

  return false;
}

// Synchronous on purpose: Windows uses SendInput, and Enter must never outrun the paste.
static bool RunXdotoolKey(const std::string& keyspec) {
  // Direct XTEST instead of subprocess: avoids UI freeze on GTK thread (armadilhas 4.7).
  static bool xtest_ok = false;
  static bool xtest_tentado = false;
  static void* xtest_lib = nullptr;
  static int (*fake_key)(Display*, unsigned int, int, unsigned long) = nullptr;

  if (!xtest_tentado) {
    xtest_tentado = true;
    xtest_lib = dlopen("libXtst.so.6", RTLD_LAZY);
    if (xtest_lib) {
      fake_key = (int (*)(Display*, unsigned int, int, unsigned long))
          dlsym(xtest_lib, "XTestFakeKeyEvent");
      xtest_ok = fake_key != nullptr;
    }
    if (!xtest_ok) g_warning("dito: sem XTest, caindo para xdotool (interface pode travar)");
  }

  if (xtest_ok) {
    Display* d = XOpenDisplay(nullptr);
    if (d) {
      bool com_ctrl = false;
      bool com_shift = false;
      bool com_alt = false;
      std::string tecla = keyspec;

      while (true) {
        if (tecla.rfind("ctrl+", 0) == 0) {
          com_ctrl = true;
          tecla = tecla.substr(5);
        } else if (tecla.rfind("shift+", 0) == 0) {
          com_shift = true;
          tecla = tecla.substr(6);
        } else if (tecla.rfind("alt+", 0) == 0) {
          com_alt = true;
          tecla = tecla.substr(4);
        } else {
          break;
        }
      }

      const KeyCode kc = XKeysymToKeycode(d, KeySymFromName(tecla));
      const KeyCode ctrl = XKeysymToKeycode(d, XK_Control_L);
      const KeyCode shift = XKeysymToKeycode(d, XK_Shift_L);
      const KeyCode alt = XKeysymToKeycode(d, XK_Alt_L);

      if (kc != 0) {
        if (com_ctrl) fake_key(d, ctrl, True, 0);
        if (com_shift) fake_key(d, shift, True, 0);
        if (com_alt) fake_key(d, alt, True, 0);
        fake_key(d, kc, True, 0);
        fake_key(d, kc, False, 0);
        if (com_alt) fake_key(d, alt, False, 0);
        if (com_shift) fake_key(d, shift, False, 0);
        if (com_ctrl) fake_key(d, ctrl, False, 0);
        XFlush(d);
        XCloseDisplay(d);
        return true;
      }
      XCloseDisplay(d);
    }
  }

  const gchar* argv[] = {"xdotool", "key", "--clearmodifiers", keyspec.c_str(), nullptr};
  gint status = 0;
  g_autoptr(GError) error = nullptr;
  if (!g_spawn_sync(nullptr, const_cast<gchar**>(argv), nullptr, G_SPAWN_SEARCH_PATH, nullptr,
                    nullptr, nullptr, nullptr, &status, &error)) {
    g_warning("xdotool key %s nao executou: %s", keyspec.c_str(), error->message);
    return false;
  }
  if (status != 0) {
    g_warning("xdotool key %s saiu com status %d", keyspec.c_str(), status);
    return false;
  }
  return true;
}

// gtk_clipboard_set_text has no return value; these mirror it but report real selection ownership.
static void ClipboardGetFunc(GtkClipboard* clipboard, GtkSelectionData* selection_data,
                             guint info, gpointer user_data) {
  gtk_selection_data_set_text(selection_data, static_cast<const gchar*>(user_data), -1);
}

static void ClipboardClearFunc(GtkClipboard* clipboard, gpointer user_data) {
  g_free(user_data);
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
                auto& bindings = self->state->bindings;
                bindings.erase(std::remove_if(bindings.begin(), bindings.end(),
                                              [&](const X11Binding& b) {
                                                return b.action == action;
                                              }),
                               bindings.end());
                bindings.push_back({action, key, kc, suppress, false});
              }
              RequestGrabSync(self);
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
        std::vector<KeyCode> keycodes;
        {
          std::lock_guard<std::mutex> lock(self->state->mutex);
          for (auto it = self->state->bindings.begin(); it != self->state->bindings.end();) {
            if (it->action == action) {
              keycodes.push_back(it->keycode);
              it = self->state->bindings.erase(it);
            } else {
              ++it;
            }
          }
        }
        for (const KeyCode kc : keycodes) RequestUngrab(self, kc);
      }
    }
    g_autoptr(FlValue) result = fl_value_new_bool(TRUE);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "keys.unbindAll") == 0) {
    if (self->state) {
      std::vector<KeyCode> keycodes;
      {
        std::lock_guard<std::mutex> lock(self->state->mutex);
        for (const auto& b : self->state->bindings) keycodes.push_back(b.keycode);
        self->state->bindings.clear();
        self->state->seen.clear();
      }
      for (const KeyCode kc : keycodes) RequestUngrab(self, kc);
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
      for (const auto& b : self->state->bindings) {
        fl_value_set_string_take(result, ("grab:" + b.action).c_str(),
                                 fl_value_new_bool(b.grabbed));
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

  if (g_strcmp0(method, "keys.injectForTest") == 0) {
    std::string tecla;
    bool down = true;
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* k = fl_value_lookup_string(args, "key");
      FlValue* dv = fl_value_lookup_string(args, "down");
      if (k && fl_value_get_type(k) == FL_VALUE_TYPE_STRING) tecla = fl_value_get_string(k);
      if (dv && fl_value_get_type(dv) == FL_VALUE_TYPE_BOOL) down = fl_value_get_bool(dv);
    }
    g_autoptr(FlValue) result = fl_value_new_int(InjectKeyForTest(tecla, down));
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
    bool ok = false;
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* text_val = fl_value_lookup_string(args, "text");
      if (text_val && fl_value_get_type(text_val) == FL_VALUE_TYPE_STRING) {
        const gchar* text = fl_value_get_string(text_val);
        GtkClipboard* clip = gtk_clipboard_get(GDK_SELECTION_CLIPBOARD);

        GtkTargetList* target_list = gtk_target_list_new(nullptr, 0);
        gtk_target_list_add_text_targets(target_list, 0);
        gint n_targets = 0;
        GtkTargetEntry* targets = gtk_target_table_new_from_list(target_list, &n_targets);

        // Selection ownership can outlive this call; Get/Clear own this copy, not the stack text.
        gchar* owned_text = g_strdup(text);
        ok = gtk_clipboard_set_with_data(clip, targets, n_targets, ClipboardGetFunc,
                                         ClipboardClearFunc, owned_text);
        // ok==FALSE means our callbacks were never installed, so nothing else will free this.
        if (!ok) g_free(owned_text);

        gtk_target_table_free(targets, n_targets);
        gtk_target_list_unref(target_list);
      }
    }
    g_autoptr(FlValue) result = fl_value_new_bool(ok);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "input.targetKind") == 0) {
    const char* kind = "gui";
    Display* display = XOpenDisplay(nullptr);
    if (display) {
      Window target = self->state ? self->state->last_paste_target : 0;
      if (target == 0) target = ReadNetActiveWindow(display);
      if (target != 0 && IsTerminalWindow(display, target)) kind = "terminal";
      XCloseDisplay(display);
    }
    g_autoptr(FlValue) result = fl_value_new_string(kind);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "input.sendCtrlV") == 0 ||
      g_strcmp0(method, "paste.ctrl_v") == 0) {
    bool is_terminal = false;
    Display* display = XOpenDisplay(nullptr);
    if (display) {
      Window target = ReadNetActiveWindow(display);
      if (target == 0 && self->state) {
        target = self->state->last_paste_target;
      }
      if (target != 0) {
        is_terminal = IsTerminalWindow(display, target);
      }
      XCloseDisplay(display);
    }
    const std::string spec = is_terminal ? "ctrl+shift+v" : "ctrl+v";
    g_autoptr(FlValue) result = fl_value_new_bool(RunXdotoolKey(spec));
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "input.sendEnter") == 0 ||
      g_strcmp0(method, "paste.enter") == 0) {
    g_autoptr(FlValue) result = fl_value_new_bool(RunXdotoolKey("Return"));
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
    // Same allow-list as the Windows plugin: never build a key spec out of arbitrary input.
    if (key != "a" && key != "c" && key != "v" && key != "enter") {
      fl_method_call_respond_error(method_call, "KEY_UNKNOWN",
                                   ("tecla desconhecida: " + key).c_str(), nullptr, nullptr);
      return;
    }
    const std::string spec =
        std::string(ctrl ? "ctrl+" : "") + (key == "enter" ? "Return" : key);
    g_autoptr(FlValue) result = fl_value_new_bool(RunXdotoolKey(spec));
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
      // Never remember ourselves, but never forget who came before either (docs/armadilhas.md 4.5).
      if (current != self_xid && current != 0) {
        self->state->saved_focus_target = current;
        self->state->last_paste_target = current;
      }
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
      const Window target = self->state->saved_focus_target;
      self->state->last_paste_target = target;
      RequestActivateWindow(display, target);
      self->state->saved_focus_target = 0;
      // One check, no retry loop: window.focus's busy-wait is a known issue left for later.
      XSync(display, False);
      if (ReadNetActiveWindow(display) != target) {
        g_warning("focus.giveBack: foco nao voltou para o alvo salvo (0x%lx)", target);
      }
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
    // paplay ignores the desktop "event sounds" toggle, unlike canberra-gtk-play which silently no-ops when it's off.
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

  // accept_focus=FALSE writes WM_HINTS.input=False, permanent under Mutter unlike Windows' weaker WS_EX_NOACTIVATE (docs/armadilhas.md 4.6).
  if (g_strcmp0(method, "window.setFocusable") == 0) {
    GtkWindow* win = GetToplevel(self);
    bool focusable = true;
    if (fl_value_get_type(args) == FL_VALUE_TYPE_BOOL) {
      focusable = fl_value_get_bool(args);
    }
    if (win) {
      gtk_window_set_accept_focus(win, focusable ? TRUE : FALSE);
      gtk_window_set_focus_on_map(win, focusable ? TRUE : FALSE);
    }
    g_autoptr(FlValue) result = fl_value_new_bool(win != nullptr);
    fl_method_call_respond_success(method_call, result, nullptr);
    return;
  }

  if (g_strcmp0(method, "window.showNoActivate") == 0) {
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

  if (g_strcmp0(method, "window.focus") == 0) {
    GtkWindow* win = GetToplevel(self);
    if (!win) {
      g_warning("window.focus: sem janela nativa (toplevel nulo)");
      fl_method_call_respond_error(method_call, "NO_WINDOW", "sem janela nativa", nullptr, nullptr);
      return;
    }
    gtk_widget_show_all(GTK_WIDGET(win));
    GdkWindow* gdk_win = gtk_widget_get_window(GTK_WIDGET(win));
    if (!gdk_win) {
      gtk_window_present(win);
      g_autoptr(FlValue) unrealized = fl_value_new_bool(FALSE);
      fl_method_call_respond_success(method_call, unrealized, nullptr);
      return;
    }

    Display* display = GDK_DISPLAY_XDISPLAY(gdk_window_get_display(gdk_win));
    const Window xid = GDK_WINDOW_XID(gdk_win);
    bool active = false;
    // Ask, then confirm: answering TRUE without checking is what hid this bug for a whole day.
    for (int attempt = 0; attempt < 2 && !active; attempt++) {
      const Time when = gdk_x11_get_server_time(gdk_win);
      // Muffin/Mutter judge focus stealing by the window's user time; a stale one is refused.
      gdk_x11_window_set_user_time(gdk_win, when);
      gtk_window_present_with_time(win, when);
      RequestActivateWindow(display, xid, when);
      XSync(display, False);
      // The WM is another client: give it a moment to act before calling the request refused.
      for (int wait = 0; wait < 20 && !active; wait++) {
        g_usleep(5000);
        active = ReadNetActiveWindow(display) == xid;
      }
    }
    if (!active) {
      // A re-mapped window trips focus-stealing prevention; take the focus at the X level instead.
      XWindowAttributes attrs = {};
      if (XGetWindowAttributes(display, xid, &attrs) && attrs.map_state == IsViewable) {
        XSetInputFocus(display, xid, RevertToParent, gdk_x11_get_server_time(gdk_win));
        XSync(display, False);
        active = true;
      } else {
        g_warning("window.focus: janela nao esta visivel, sem foco possivel");
      }
    }
    g_autoptr(FlValue) result = fl_value_new_bool(active);
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
          // Cairo has no rounded-corner region: built strip by strip, one line per pixel of the arc, so the clip follows the curve instead of cutting square.
          cairo_rectangle_int_t body = {(int)left, (int)(top + radius),
                                        (int)width, (int)(height - 2 * radius)};
          region = cairo_region_create_rectangle(&body);
          const int r = (int)radius;
          for (int i = 0; i < r; ++i) {
            const double dy = r - i - 0.5;
            const int inset = r - (int)(std::sqrt((double)r * r - dy * dy) + 0.5);
            cairo_rectangle_int_t topo = {(int)left + inset, (int)top + i,
                                          (int)width - 2 * inset, 1};
            cairo_rectangle_int_t base = {(int)left + inset,
                                          (int)(top + height) - i - 1,
                                          (int)width - 2 * inset, 1};
            cairo_region_union_rectangle(region, &topo);
            cairo_region_union_rectangle(region, &base);
          }
        } else {
          cairo_rectangle_int_t rect = {(int)left, (int)top, (int)width, (int)height};
          region = cairo_region_create_rectangle(&rect);
        }
        // Without an RGBA visual the window is opaque: the shape clip is what leaves only the pill.
        gtk_widget_shape_combine_region(GTK_WIDGET(win), region);
        gtk_widget_input_shape_combine_region(GTK_WIDGET(win), region);
        cairo_region_destroy(region);
        SetWindowOpacity(win, true);
      } else {
        // Empty region = invisible window without unmapping; real show/hide failed intermittently on this WM (docs/armadilhas.md 4.3).
        cairo_region_t* empty = cairo_region_create();
        gtk_widget_input_shape_combine_region(GTK_WIDGET(win), empty);
        // An empty shape is what Muffin gets wrong: it does not repaint the freed area, leaving a ghost toast (docs/armadilhas.md 4.8).
        if (gdk_screen_is_composited(gtk_widget_get_screen(GTK_WIDGET(win)))) {
          SetWindowOpacity(win, false);
        } else {
          gtk_widget_shape_combine_region(GTK_WIDGET(win), empty);
        }
        cairo_region_destroy(empty);
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

  if (g_strcmp0(method, "test.ownsForeground") == 0) {
    bool owns = false;
    GtkWindow* win = GetToplevel(self);
    GdkWindow* gdk_win = win ? gtk_widget_get_window(GTK_WIDGET(win)) : nullptr;
    if (gdk_win) {
      Display* display = GDK_DISPLAY_XDISPLAY(gdk_window_get_display(gdk_win));
      // Read-only twin of the check in window.focus: compare, don't request.
      owns = ReadNetActiveWindow(display) == GDK_WINDOW_XID(gdk_win);
    }
    g_autoptr(FlValue) result = fl_value_new_bool(owns);
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
  // Everything here casts GDK handles to X11 ones; say so loudly instead of segfaulting later.
  static std::once_flag backend_warned;
  std::call_once(backend_warned, [] {
    if (!GDK_IS_X11_DISPLAY(gdk_display_get_default())) {
      g_critical("dito_win32: sessao nao e X11; teclas globais, foco e colagem nao vao funcionar");
    }
  });

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
