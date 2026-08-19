#include "include/dito_whisper/dito_whisper_plugin.h"

#include <flutter_linux/flutter_linux.h>

#define DITO_WHISPER_PLUGIN(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj), dito_whisper_plugin_get_type(), \
                              DitoWhisperPlugin))

struct _DitoWhisperPlugin {
  GObject parent_instance;
};

G_DEFINE_TYPE(DitoWhisperPlugin, dito_whisper_plugin, g_object_get_type())

static void dito_whisper_plugin_dispose(GObject* object) {
  G_OBJECT_CLASS(dito_whisper_plugin_parent_class)->dispose(object);
}

static void dito_whisper_plugin_class_init(DitoWhisperPluginClass* klass) {
  G_OBJECT_CLASS(klass)->dispose = dito_whisper_plugin_dispose;
}

static void dito_whisper_plugin_init(DitoWhisperPlugin* self) {}

void dito_whisper_plugin_register_with_registrar(
    FlPluginRegistrar* registrar) {
  // FFI symbols are exported directly by the shared library.
}
