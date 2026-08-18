#ifndef DITO_WIN32_KEY_TABLE_H_
#define DITO_WIN32_KEY_TABLE_H_

#include <windows.h>

#include <string>

namespace dito {

// Only keys that type no character, mirroring src/dito/keys.py BINDABLE.
UINT VkFromName(const std::string& name);

std::string NameFromVk(UINT vk);

}  // namespace dito

#endif  // DITO_WIN32_KEY_TABLE_H_
