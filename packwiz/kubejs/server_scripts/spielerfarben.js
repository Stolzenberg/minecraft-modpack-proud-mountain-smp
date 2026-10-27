// Spielerfarben: Spielername in der Farbe, die der Spieler auch auf https://stats.proud-mountain.com hat
//
// Die Zuordnung Spieler -> Farbnummer steht in config/proudmountain/spielerfarben.json (liest auch das Dashboard).
// Gesetzt wird der Anzeigename (PlayerEvent.NameFormat), damit ist der Name überall dort farbig, wo Minecraft ihn
// verwendet: Chat, Todes- und Fortschrittsmeldungen, /say, /me. Das Chatformat "Name: Text" (statt "<Name> Text")
// kommt aus kubejs/data/minecraft/chat_type/chat.json, der Text bleibt weiß.
// Änderungen an der Datei greifen erst nach einem Neustart (NativeEvents, kein kubejs reload).

;(function () {
  const FILE = 'config/proudmountain/spielerfarben.json'
  // wie --s1 … --s8 auf der Statistikseite (helle Variante, auf dem dunklen Chat-Hintergrund gut lesbar)
  const SLOT_COLORS = [0x2a78d6, 0xeb6834, 0x1baf7a, 0xeda100, 0xe87ba4, 0x008300, 0x6250d6, 0xe34948]

  const $NameFormat = Java.loadClass('net.neoforged.neoforge.event.entity.player.PlayerEvent$NameFormat')
  const $Component = Java.loadClass('net.minecraft.network.chat.Component')

  let colors = {}
  try {
    let farben = JSON.parse(String(JsonIO.readString(FILE))).farben || {}
    Object.keys(farben).forEach(name => {
      let slot = Number(farben[name])
      if (slot >= 1 && slot <= SLOT_COLORS.length) colors[name] = SLOT_COLORS[slot - 1]
    })
    console.info(`[spielerfarben] ${Object.keys(colors).length} Spielerfarben geladen`)
  } catch (e) {
    console.error(`[spielerfarben] ${FILE} nicht lesbar: ${e}`)
  }

  NativeEvents.onEvent($NameFormat, event => {
    let name = String(event.getUsername().getString())
    let color = colors[name]
    if (color !== undefined) event.setDisplayname($Component.literal(name).withColor(color))
  })
})()
