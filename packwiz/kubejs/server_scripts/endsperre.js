// End-Sperre: Das End bleibt zu, bis ein OP es mit /endsperre freischalten öffnet
//
// Solange es gesperrt ist, bricht jede Reise ins End ab (Endportal, Teleport-Befehle, Waystones, Items und Tiere
// im Portal). Hinaus geht es immer. OPs im Creative- oder Zuschauermodus kommen trotzdem hinein, zum Nachschauen.
// Der Zustand liegt in server.persistentData und übersteht Neustarts, ohne Eintrag ist das End gesperrt.
//   /endsperre               zeigt den Zustand
//   /endsperre freischalten  öffnet das End und sagt es allen Spielern
//   /endsperre sperren       sperrt es wieder (wer schon drin ist, bleibt drin)

;(function () {
  const OPEN_KEY = 'proudmountain_end_open'
  const END = 'minecraft:the_end'

  const $TravelEvent = Java.loadClass('net.neoforged.neoforge.event.entity.EntityTravelToDimensionEvent')

  const lastNotice = {} // UUID → Server-Tick der letzten Sperr-Meldung

  function isOpen(server) {
    return server.persistentData.getBoolean(OPEN_KEY)
  }

  function status(server) {
    return isOpen(server) ? 'Das End ist freigeschaltet.' : 'Das End ist gesperrt.'
  }

  ServerEvents.commandRegistry(event => {
    const { commands: Commands } = event
    const reply = (ctx, msg) => ctx.source.sendSuccess(() => Text.of(msg), true)
    event.register(Commands.literal('endsperre')
      .requires(src => src.hasPermission(2))
      .executes(ctx => {
        reply(ctx, status(ctx.source.getServer()))
        return 1
      })
      .then(Commands.literal('freischalten').executes(ctx => {
        let server = ctx.source.getServer()
        if (isOpen(server)) {
          reply(ctx, 'Das End ist schon freigeschaltet.')
          return 0
        }
        server.persistentData.putBoolean(OPEN_KEY, true)
        console.info('[endsperre] End freigeschaltet')
        server.tell(Text.of('Das End ist jetzt freigeschaltet!').gold().bold())
        return 1
      }))
      .then(Commands.literal('sperren').executes(ctx => {
        let server = ctx.source.getServer()
        server.persistentData.putBoolean(OPEN_KEY, false)
        console.info('[endsperre] End gesperrt')
        reply(ctx, 'Das End ist gesperrt. Wer schon drin ist, bleibt drin, kann aber jederzeit hinaus.')
        return 1
      })))
  })

  NativeEvents.onEvent($TravelEvent, event => {
    if (String(event.getDimension().location()) != END) return
    let entity = event.getEntity()
    let server = entity.getServer()
    if (!server || isOpen(server)) return
    if (entity.isPlayer() && entity.hasPermissions(2) && (entity.isCreative() || entity.isSpectator())) return
    event.setCanceled(true)
    if (!entity.isPlayer()) return
    // Wer im Portal steht, löst das jeden Tick aus: höchstens alle 3 s melden
    let id = String(entity.uuid)
    let now = server.getTickCount()
    if (lastNotice[id] && now - lastNotice[id] < 60) return
    lastNotice[id] = now
    entity.displayClientMessage(Text.of('Das End ist noch gesperrt und wird später freigeschaltet.').red(), true)
  })
})()
