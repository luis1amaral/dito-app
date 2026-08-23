// The only bridge to a screen: with contextIsolation on, nothing else is reachable.
import { contextBridge, ipcRenderer } from 'electron'
import type {
  EventChannel,
  EventMap,
  InvokeChannel,
  InvokeMap,
  RendererApi,
  SendChannel,
  SendMap
} from '../shared/ipc'

const api: RendererApi = {
  invoke<C extends InvokeChannel>(channel: C, arg?: InvokeMap[C]['arg']) {
    return ipcRenderer.invoke(channel, arg) as Promise<InvokeMap[C]['ret']>
  },
  send<C extends SendChannel>(channel: C, payload: SendMap[C]) {
    ipcRenderer.send(channel, payload)
  },
  // Returns the unsubscribe function: a screen that reloads must not stack listeners.
  on<C extends EventChannel>(channel: C, listener: (payload: EventMap[C]) => void) {
    const wrapped = (_event: unknown, payload: EventMap[C]): void => listener(payload)
    ipcRenderer.on(channel, wrapped)
    return () => ipcRenderer.removeListener(channel, wrapped)
  }
}

contextBridge.exposeInMainWorld('api', api)
