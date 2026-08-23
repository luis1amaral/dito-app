#include "key_table.h"

#include <algorithm>
#include <map>

namespace dito {

namespace {

const std::map<std::string, UINT>& Table() {
  static const std::map<std::string, UINT> table = {
      {"f1", VK_F1},   {"f2", VK_F2},   {"f3", VK_F3},   {"f4", VK_F4},
      {"f5", VK_F5},
      {"f9", VK_F9},   {"f10", VK_F10}, {"f11", VK_F11}, {"f12", VK_F12},
      {"f13", VK_F13}, {"f14", VK_F14}, {"f15", VK_F15}, {"f16", VK_F16},
      {"space", VK_SPACE},
      {"print_screen", VK_SNAPSHOT},
      {"page_up", VK_PRIOR},
      {"page_down", VK_NEXT},
      {"scroll_lock", VK_SCROLL},
      {"pause", VK_PAUSE},
      {"insert", VK_INSERT},
      {"menu", VK_APPS},
      {"home", VK_HOME},
      {"end", VK_END},
      {"caps_lock", VK_CAPITAL},
  };
  return table;
}

}  // namespace

UINT VkFromName(const std::string& name) {
  std::string key = name;
  std::transform(key.begin(), key.end(), key.begin(),
                 [](unsigned char c) { return static_cast<char>(::tolower(c)); });
  const auto it = Table().find(key);
  return it == Table().end() ? 0 : it->second;
}

std::string NameFromVk(UINT vk) {
  for (const auto& [name, code] : Table()) {
    if (code == vk) return name;
  }
  return "";
}

}  // namespace dito
