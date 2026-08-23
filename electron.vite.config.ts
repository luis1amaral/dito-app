import { defineConfig } from 'electron-vite'
import { resolve } from 'node:path'

// Two renderer entries: the settings window and the overlay pill.
export default defineConfig({
  main: {
    build: {
      rollupOptions: {
        // The addon is loaded at runtime by absolute path; bundling it would break that.
        external: ['electron', 'sherpa-onnx-node', 'electron-updater'],
        // The worker runs in its own thread and needs to stay a separate file on disk.
        input: {
          index: resolve(__dirname, 'src/main/index.ts'),
          'engine-worker': resolve(__dirname, 'src/main/engine-worker.ts')
        },
        output: { entryFileNames: '[name].js' }
      }
    }
  },
  preload: {
    build: { rollupOptions: { external: ['electron'] } }
  },
  renderer: {
    root: 'src/renderer',
    build: {
      rollupOptions: {
        input: {
          settings: resolve(__dirname, 'src/renderer/settings.html'),
          pill: resolve(__dirname, 'src/renderer/pill.html')
        }
      }
    }
  }
})
