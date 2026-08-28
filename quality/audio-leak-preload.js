// Test double for the pill's IPC bridge, plus a tap on getUserMedia so the gate can see every
// stream the renderer ever acquired -- a leaked stream is one whose tracks are still "live".
const handlers = {}
const sent = []
const acquired = []

window.api = {
  on: (channel, fn) => {
    ;(handlers[channel] ||= []).push(fn)
  },
  send: (channel, payload) => sent.push({ channel, payload }),
  invoke: async (channel) => (channel === 'i18n:lang' ? 'pt' : undefined),
}

const realGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
navigator.mediaDevices.getUserMedia = async (constraints) => {
  const stream = await realGetUserMedia(constraints)
  acquired.push(stream)
  return stream
}

window.gateHooks = {
  emit: (channel, payload) => (handlers[channel] ?? []).forEach((fn) => fn(payload)),
  report: () => {
    const tracks = acquired.flatMap((s) => s.getTracks())
    return {
      acquired: acquired.length,
      tracks: tracks.length,
      live: tracks.filter((t) => t.readyState === 'live').length,
      sent: sent.map((s) => s.channel),
    }
  },
}
