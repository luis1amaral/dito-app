#pragma once

#include <string>
#include <flutter/encodable_value.h>
#include <iostream>

struct WindowConfiguration {
  std::string arguments;
  bool hidden_at_launch = false;
  // Fork: a HUD must never take focus, and that can only be decided at CreateWindowEx time.
  bool focusable = true;

  static WindowConfiguration FromEncodableMap(
      const flutter::EncodableMap* map) {
    WindowConfiguration config;
    
    if (!map) return config;
    
    try {
      auto it = map->find(flutter::EncodableValue("arguments"));
      if (it != map->end()) {
        config.arguments = std::get<std::string>(it->second);
      }
      
      it = map->find(flutter::EncodableValue("hiddenAtLaunch"));
      if (it != map->end()) {
        config.hidden_at_launch = std::get<bool>(it->second);
      }

      it = map->find(flutter::EncodableValue("focusable"));
      if (it != map->end()) {
        config.focusable = std::get<bool>(it->second);
      }
    } catch (const std::exception& e) {
      std::cerr << "Failed to parse WindowConfiguration: " << e.what() 
                << std::endl;
    }
    
    return config;
  }
};