#include "include/dito_win32/dito_win32_plugin.h"

#include <flutter_linux/flutter_linux.h>
#include <gtk/gtk.h>

#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <string>
#include <thread>
#include <vector>

#define DITO_WIN32_PLUGIN(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj), dito_win32_plugin_get_type(), \
                              DitoWin32Plugin))

struct _DitoWin32Plugin {
  GObject parent_instance;
  FlPluginRegistrar* registrar;
  FlMethodChannel* method_channel;
  FlEventChannel* key_channel;
  FlEventChannel* tray_channel;
};

G_DEFINE_TYPE(DitoWin32Plugin, dito_win32_plugin, g_object_get_type())

static void dito_win32_plugin_dispose(GObject* object) {
  DitoWin32Plugin* self = DITO_WIN32_PLUGIN(object);
  if (self->method_channel != nullptr) {
    g_clear_object(&self->method_channel);
  }
  if (self->key_channel != nullptr) {
    g_clear_object(&self->key_channel);
  }
  if (self->tray_channel != nullptr) {
    g_clear_object(&self->tray_channel);
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
}

static std::string exec_cmd(const char* cmd) {
  char buffer[128];
  std::string result = "";
  FILE* pipe = popen(cmd, "r");
  if (!pipe) return "";
  while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
    result += buffer;
  }
  pclose(pipe);
  return result;
}

static FlMethodResponse* handle_method_call(DitoWin32Plugin* self,
                                           FlMethodCall* method_call) {
  const gchar* method = fl_method_call_get_name(method_call);
  FlValue* args = fl_method_call_get_args(method_call);

  if (g_strcmp0(method, "paste.ctrlV") == 0) {
    // Injeta Ctrl+V no Linux tentando xdotool (X11) e wtype (Wayland)
    system("xdotool key --clearmodifiers ctrl+v 2>/dev/null || wtype -M ctrl -k v -m ctrl 2>/dev/null || ydotool key 29:1 47:1 47:0 29:0 2>/dev/null &");
    return FL_METHOD_RESPONSE(fl_method_success_response_new(fl_value_new_bool(TRUE)));
  } else if (g_strcmp0(method, "paste.enter") == 0) {
    system("xdotool key Return 2>/dev/null || wtype -k Return 2>/dev/null &");
    return FL_METHOD_RESPONSE(fl_method_success_response_new(fl_value_new_bool(TRUE)));
  } else if (g_strcmp0(method, "clipboard.read") == 0) {
    std::string clip = exec_cmd("xclip -o -selection clipboard 2>/dev/null || wl-paste 2>/dev/null");
    return FL_METHOD_RESPONSE(fl_method_success_response_new(fl_value_new_string(clip.c_str())));
  } else if (g_strcmp0(method, "clipboard.write") == 0) {
    if (fl_value_get_type(args) == FL_VALUE_TYPE_MAP) {
      FlValue* text_v = fl_value_lookup_string(args, "text");
      if (text_v && fl_value_get_type(text_v) == FL_VALUE_TYPE_STRING) {
        const char* text = fl_value_get_string(text_v);
        // Escreve no clipboard via xclip / wl-copy
        FILE* p = popen("xclip -i -selection clipboard 2>/dev/null || wl-copy 2>/dev/null", "w");
        if (p) {
          fputs(text, p);
          pclose(p);
        }
      }
    }
    return FL_METHOD_RESPONSE(fl_method_success_response_new(fl_value_new_bool(TRUE)));
  } else if (g_strcmp0(method, "adoptAsPanel") == 0) {
    return FL_METHOD_RESPONSE(fl_method_success_response_new(nullptr));
  } else if (g_strcmp0(method, "window.showNoActivate") == 0) {
    return FL_METHOD_RESPONSE(fl_method_success_response_new(nullptr));
  } else if (g_strcmp0(method, "window.setHitRect") == 0) {
    return FL_METHOD_RESPONSE(fl_method_success_response_new(nullptr));
  } else if (g_strcmp0(method, "keys.bind") == 0 ||
             g_strcmp0(method, "keys.unbindAll") == 0 ||
             g_strcmp0(method, "keys.pause") == 0 ||
             g_strcmp0(method, "keys.resume") == 0) {
    return FL_METHOD_RESPONSE(fl_method_success_response_new(nullptr));
  } else if (g_strcmp0(method, "keys.snapshot") == 0) {
    g_autoptr(FlValue) map = fl_value_new_map();
    return FL_METHOD_RESPONSE(fl_method_success_response_new(map));
  } else if (g_strcmp0(method, "tray.init") == 0 ||
             g_strcmp0(method, "tray.setIcon") == 0 ||
             g_strcmp0(method, "tray.setTooltip") == 0 ||
             g_strcmp0(method, "tray.setMenu") == 0 ||
             g_strcmp0(method, "tray.remove") == 0) {
    return FL_METHOD_RESPONSE(fl_method_success_response_new(nullptr));
  }

  return FL_METHOD_RESPONSE(fl_method_not_implemented_response_new());
}

static void method_call_cb(FlMethodChannel* channel,
                           FlMethodCall* method_call,
                           gpointer user_data) {
  DitoWin32Plugin* self = DITO_WIN32_PLUGIN(user_data);
  g_autoptr(FlMethodResponse) response = handle_method_call(self, method_call);
  fl_method_call_respond(method_call, response, nullptr);
}

void dito_win32_plugin_register_with_registrar(
    FlPluginRegistrar* registrar) {
  DitoWin32Plugin* plugin = DITO_WIN32_PLUGIN(
      g_object_new(dito_win32_plugin_get_type(), nullptr));
  plugin->registrar = registrar;

  g_autoptr(FlStandardMethodCodec) codec = fl_standard_method_codec_new();
  plugin->method_channel = fl_method_channel_new(
      fl_plugin_registrar_get_messenger(registrar),
      "dito/win32", FL_METHOD_CODEC(codec));
  fl_method_channel_set_method_call_handler(
      plugin->method_channel, method_call_cb, g_object_ref(plugin), g_object_unref);

  g_object_unref(plugin);
}
