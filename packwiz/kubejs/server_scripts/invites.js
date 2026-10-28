// Einladungen mit Bürgschaft: Wer auf der Whitelist steht, kann genau einen neuen Spieler einladen und bürgt für ihn
//
// Wird ein Spieler mit /punish gebannt, trifft es seine Bürgen mit: wer ihn eingeladen hat, bekommt die halbe Zeit,
// dessen Einlader ein Viertel, der nächste ein Achtel (höchstens 3 Stufen nach oben). Fliegt der Eingeladene von der
// Whitelist, ist die Einladung wieder frei. Wer von Anfang an dabei war (.env), hat keinen Bürgen.
//   /invite <name>                    zeigt, worauf man sich einlässt, /invite <name> confirm lädt ein
//   /invites [name]                   wer wen eingeladen hat, wer für einen bürgt, ob die Einladung frei ist
//   /punish <name> <hours> [reason]   nur OPs: Bann auf Zeit, Bürgen werden mitgebannt
// Einladungen und verhängte Banns stehen in config/proudmountain/einladungen.json (nicht im Repo, nur auf dem Server).
// Die Banns selbst liegen in banned-players.json mit Ablaufzeit. Vanilla hebt abgelaufene Banns nicht sauber auf
// (isBanned sieht sie noch, get() räumt sie dann weg und der Login scheitert an null), deshalb entfernt dieses
// Skript sie jede Sekunde selbst. Aufheben vorzeitig: /pardon <name>, das trifft dann nur diesen einen Spieler.

;(function () {
  const FILE = 'config/proudmountain/einladungen.json'
  const COLORS_FILE = 'config/proudmountain/spielerfarben.json'
  const CHAIN = 3 // so viele Bürgen nach oben werden mitgebannt
  const HINT = 'Wird von KubeJS invites.js geschrieben (/invite, /punish). Einladungen: wer wen eingeladen hat ' +
    '(farbe = Spielerfarbe 1–8 für Chat und Statistikseite). Banns: nur zur Übersicht, maßgeblich ist banned-players.json.'

  const $Date = Java.loadClass('java.util.Date')
  const $UUID = Java.loadClass('java.util.UUID')
  const $GameProfile = Java.loadClass('com.mojang.authlib.GameProfile')
  const $UserBanListEntry = Java.loadClass('net.minecraft.server.players.UserBanListEntry')
  const $UserWhiteListEntry = Java.loadClass('net.minecraft.server.players.UserWhiteListEntry')
  const $DoubleArgumentType = Java.loadClass('com.mojang.brigadier.arguments.DoubleArgumentType')

  function load() {
    let data = {}
    try {
      data = JSON.parse(String(JsonIO.readString(FILE)))
    } catch (e) {
      // Datei gibt es erst nach der ersten Einladung
    }
    return { _hinweis: HINT, einladungen: data.einladungen || [], banns: data.banns || [] }
  }

  function save(data) {
    JsonIO.write(FILE, JsonIO.parseRaw(JSON.stringify(data)))
  }

  function profile(uuid, name) {
    return new $GameProfile($UUID.fromString(uuid), name)
  }

  function lookup(server, name) {
    // fragt bei Mojang nach, wenn der Name nicht im Cache ist. Die Variante ausdrücklich wählen, sonst nimmt Rhino
    // get(UUID) und scheitert beim Umwandeln des Namens in eine UUID (außerhalb von try/catch)
    let found = server.getProfileCache()['get(java.lang.String)'](name)
    return found.isPresent() ? found.get() : null
  }

  function whitelisted(server, uuid, name) {
    return server.getPlayerList().getWhiteList().isWhiteListed(profile(uuid, name))
  }

  // Die jüngste Einladung zählt, falls jemand entfernt und später von einem anderen neu eingeladen wurde
  function inviteOf(data, uuid) {
    for (let i = data.einladungen.length - 1; i >= 0; i--) {
      if (data.einladungen[i].anUuid == uuid) return data.einladungen[i]
    }
    return null
  }

  // Die Einladung, die jemand vergeben hat, solange der Eingeladene noch auf der Whitelist steht
  function activeInviteBy(server, data, uuid) {
    for (let i = data.einladungen.length - 1; i >= 0; i--) {
      let e = data.einladungen[i]
      if (e.vonUuid == uuid && inviteOf(data, e.anUuid) === e && whitelisted(server, e.anUuid, e.an)) return e
    }
    return null
  }

  // Bürgen von unten nach oben: [{uuid, name}, …], höchstens CHAIN Stück
  function guarantors(data, uuid) {
    let out = []
    let seen = {}
    seen[uuid] = true
    let invite = inviteOf(data, uuid)
    while (invite && out.length < CHAIN && !seen[invite.vonUuid]) {
      seen[invite.vonUuid] = true
      out.push({ uuid: invite.vonUuid, name: invite.von })
      invite = inviteOf(data, invite.vonUuid)
    }
    return out
  }

  // Die am wenigsten vergebene Farbe, bei Gleichstand die kleinste Nummer (wie die freien Farben im Dashboard)
  function nextColor(server, data) {
    let count = [0, 0, 0, 0, 0, 0, 0, 0, 0]
    try {
      let farben = JSON.parse(String(JsonIO.readString(COLORS_FILE))).farben || {}
      Object.keys(farben).forEach(name => count[Number(farben[name])]++)
    } catch (e) {
      console.error(`[invites] ${COLORS_FILE} nicht lesbar: ${e}`)
    }
    data.einladungen.forEach(e => {
      if (e.farbe && inviteOf(data, e.anUuid) === e && whitelisted(server, e.anUuid, e.an)) count[e.farbe]++
    })
    let best = 1
    for (let c = 2; c <= 8; c++) if (count[c] < count[best]) best = c
    return best
  }

  function duration(minutes) {
    let h = Math.floor(minutes / 60)
    let m = minutes % 60
    if (h && m) return `${h} Std. ${m} Min.`
    return h ? `${h} Std.` : `${m} Min.`
  }

  function date(ms) {
    let d = new Date(ms)
    let two = n => (n < 10 ? '0' : '') + n
    return `${two(d.getDate())}.${two(d.getMonth() + 1)}. um ${two(d.getHours())}:${two(d.getMinutes())} Uhr`
  }

  // Bann auf Zeit, kommt ein bestehender Bann auf Zeit dazu, wird verlängert. Gibt null zurück bei Dauerbann.
  function ban(server, uuid, name, minutes, reason, source) {
    let bans = server.getPlayerList().getBans()
    let gp = profile(uuid, name)
    let now = Date.now()
    let start = now
    let existing = bans.get(gp)
    if (existing) {
      if (!existing.getExpires()) return null
      start = Math.max(now, Number(existing.getExpires().getTime()))
    }
    let until = start + minutes * 60000
    bans.add(new $UserBanListEntry(gp, new $Date(now), source, new $Date(until), reason))
    let online = server.getPlayerList().getPlayer(gp.getId())
    if (online) {
      online.connection['disconnect(net.minecraft.network.chat.Component)'](
        Text.of(`Du bist bis ${date(until)} gebannt.\n\n${reason}`))
    }
    console.info(`[invites] ${name} für ${duration(minutes)} gebannt (bis ${date(until)}): ${reason}`)
    return until
  }

  function expireBans(server) {
    let bans = server.getPlayerList().getBans()
    if (bans.isEmpty()) return
    let now = Date.now()
    let expired = []
    bans.getEntries().forEach(e => {
      if (e.getExpires() && Number(e.getExpires().getTime()) <= now) expired.push(e)
    })
    expired.forEach(e => {
      // getUser() ist nicht öffentlich, daher über den Eintrag (remove(K) gibt es auch)
      bans['remove(net.minecraft.server.players.StoredUserEntry)'](e)
      console.info(`[invites] Bann von ${e.getDisplayName().getString()} abgelaufen`)
    })
  }

  function invite(ctx, name, confirmed) {
    let player = ctx.source.getPlayerOrException()
    let server = ctx.source.getServer()
    let reply = (msg) => player.tell(msg)
    let me = String(player.uuid)
    let myName = player.getScoreboardName()
    if (!server.getPlayerList().getWhiteList().isWhiteListed(player.getGameProfile())) {
      reply(Text.of('Einladen kann nur, wer selbst auf der Whitelist steht.').red())
      return 0
    }
    let data = load()
    let used = activeInviteBy(server, data, me)
    if (used) {
      reply(Text.of(`Du hast deine Einladung schon an ${used.an} vergeben.`).red())
      return 0
    }
    let target = lookup(server, name)
    if (!target) {
      reply(Text.of(`Einen Minecraft-Account „${name}“ gibt es nicht.`).red())
      return 0
    }
    let targetName = String(target.getName())
    let targetUuid = String(target.getId())
    if (server.getPlayerList().getWhiteList().isWhiteListed(target)) {
      reply(Text.of(`${targetName} steht schon auf der Whitelist.`).red())
      return 0
    }
    if (!confirmed) {
      let cmd = `/invite ${targetName} confirm`
      let upper = guarantors(data, me).length ? ', wer dich eingeladen hat für ein Viertel' : ''
      reply(Text.of(`Du kannst genau einen Spieler einladen und bürgst dann für ${targetName}: ` +
        `Wird ${targetName} gebannt, wirst du für die halbe Zeit mitgebannt${upper}.`).gold())
      reply(Text.of('Zum Bestätigen hier klicken: ').gold()
        .append(Text.of(cmd).yellow().underlined().clickRunCommand(cmd)))
      return 1
    }
    server.getPlayerList().getWhiteList().add(new $UserWhiteListEntry(target))
    data.einladungen.push({
      von: myName, vonUuid: me, an: targetName, anUuid: targetUuid,
      am: new Date().toISOString(), farbe: nextColor(server, data),
    })
    save(data)
    console.info(`[invites] ${myName} hat ${targetName} eingeladen`)
    server.tell(Text.of(`${myName} hat ${targetName} eingeladen und bürgt für ${targetName}.`).gold())
    return 1
  }

  function punish(ctx, name, hours, reason) {
    let server = ctx.source.getServer()
    let reply = (msg) => ctx.source.sendSystemMessage(msg)
    let target = lookup(server, name)
    if (!target) {
      reply(Text.of(`Einen Minecraft-Account „${name}“ gibt es nicht.`).red())
      return 0
    }
    let targetName = String(target.getName())
    let targetUuid = String(target.getId())
    let source = String(ctx.source.getTextName())
    let grund = reason || 'kein Grund angegeben'
    let minutes = Math.max(1, Math.round(hours * 60))
    let data = load()
    let am = new Date().toISOString()

    let until = ban(server, targetUuid, targetName, minutes, `Grund: ${grund}`, source)
    if (until === null) {
      reply(Text.of(`${targetName} ist schon dauerhaft gebannt, niemand wurde mitgebannt.`).red())
      return 0
    }
    data.banns.push({ spieler: targetName, uuid: targetUuid, minuten: minutes, grund: grund, von: source, am: am })

    let also = []
    let chain = guarantors(data, targetUuid)
    chain.forEach((g, i) => {
      let m = Math.max(1, Math.round(minutes / Math.pow(2, i + 1)))
      let via = i == 0 ? '' : ` über ${chain.slice(0, i).reverse().map(c => c.name).join(' → ')}`
      let why = `Mitgebannt, weil du${via} für ${targetName} bürgst. Grund für ${targetName}: ${grund}`
      if (ban(server, g.uuid, g.name, m, why, source) === null) {
        also.push(`${g.name} (schon dauerhaft gebannt)`)
        return
      }
      also.push(`${g.name} (${duration(m)})`)
      data.banns.push({ spieler: g.name, uuid: g.uuid, minuten: m, grund: grund, von: source, am: am, buergeFuer: targetName })
    })
    save(data)

    server.tell(Text.of(`${targetName} wurde für ${duration(minutes)} gebannt. Grund: ${grund}`).red())
    if (also.length) server.tell(Text.of(`Als Bürgen mitgebannt: ${also.join(', ')}`).red())
    if (!ctx.source.isPlayer()) reply(Text.of(`${targetName} bis ${date(until)} gebannt` +
      (also.length ? `, mitgebannt: ${also.join(', ')}` : '')))
    return 1
  }

  function info(ctx, name) {
    let server = ctx.source.getServer()
    let reply = (msg) => ctx.source.sendSystemMessage(Text.of(msg))
    let self = ctx.source.isPlayer() && (!name || name.toLowerCase() == ctx.source.getTextName().toLowerCase())
    let target = name ? lookup(server, name) : ctx.source.isPlayer() ? ctx.source.getPlayerOrException().getGameProfile() : null
    if (!target) {
      reply(name ? `Einen Minecraft-Account „${name}“ gibt es nicht.` : 'Benutzung: /invites <name>')
      return 0
    }
    let targetName = String(target.getName())
    let uuid = String(target.getId())
    let data = load()

    let invited = inviteOf(data, uuid)
    if (invited) reply(`${targetName} wurde am ${date(Date.parse(invited.am))} von ${invited.von} eingeladen.`)
    else if (whitelisted(server, uuid, targetName)) reply(`${targetName} war von Anfang an dabei und hat keinen Bürgen.`)
    else reply(`${targetName} steht nicht auf der Whitelist.`)

    let chain = guarantors(data, uuid)
    if (chain.length) {
      let parts = ['halbe Zeit', 'ein Viertel', 'ein Achtel']
      reply(`Wird ${targetName} gebannt, trifft es auch: ` + chain.map((g, i) => `${g.name} (${parts[i]})`).join(', '))
    }

    let given = activeInviteBy(server, data, uuid)
    if (given) reply(`${targetName} hat ${given.an} eingeladen und bürgt für ${given.an}.`)
    else if (whitelisted(server, uuid, targetName)) {
      reply(self ? 'Du kannst noch einen Spieler einladen: /invite <name>' : `${targetName} kann noch einen Spieler einladen.`)
    }
    return 1
  }

  ServerEvents.commandRegistry(event => {
    const { commands: Commands, arguments: Arguments, builtinSuggestions: Suggestions } = event
    const whitelistNames = (ctx, builder) => Suggestions.suggest(ctx.source.getServer().getPlayerList().getWhiteListNames(), builder)
    // Fehler im Skript sollen als Meldung ankommen und nicht als "An unexpected error occurred". Das greift nur für
    // JS-Fehler: Java-Ausnahmen (RuntimeException) lässt Rhino an catch vorbei, die landen als "unexpected error"
    // ohne Log. Deshalb überladene Java-Methoden immer mit ausdrücklicher Signatur aufrufen, z. B. obj['get(java.lang.String)'].
    const guarded = (label, fn) => ctx => {
      try {
        return fn(ctx)
      } catch (e) {
        console.error(`[invites] ${label}: ${e}`)
        ctx.source.sendSystemMessage(Text.of(`${label}: Fehler, siehe Server-Log.`).red())
        return 0
      }
    }

    event.register(Commands.literal('invite')
      .requires(src => src.isPlayer())
      .then(Commands.argument('name', Arguments.WORD.create(event))
        .executes(guarded('/invite', ctx => invite(ctx, String(Arguments.WORD.getResult(ctx, 'name')), false)))
        .then(Commands.literal('confirm')
          .executes(guarded('/invite', ctx => invite(ctx, String(Arguments.WORD.getResult(ctx, 'name')), true))))))

    event.register(Commands.literal('invites')
      .executes(guarded('/invites', ctx => info(ctx, null)))
      .then(Commands.argument('name', Arguments.WORD.create(event))
        .suggests(whitelistNames)
        .executes(guarded('/invites', ctx => info(ctx, String(Arguments.WORD.getResult(ctx, 'name')))))))

    event.register(Commands.literal('punish')
      .requires(src => src.hasPermission(2))
      .then(Commands.argument('name', Arguments.WORD.create(event))
        .suggests(whitelistNames)
        .then(Commands.argument('hours', $DoubleArgumentType.doubleArg(0.1, 8760))
          .executes(guarded('/punish', ctx => punish(ctx, String(Arguments.WORD.getResult(ctx, 'name')),
            $DoubleArgumentType.getDouble(ctx, 'hours'), null)))
          .then(Commands.argument('reason', Arguments.GREEDY_STRING.create(event))
            .executes(guarded('/punish', ctx => punish(ctx, String(Arguments.WORD.getResult(ctx, 'name')),
              $DoubleArgumentType.getDouble(ctx, 'hours'), String(Arguments.GREEDY_STRING.getResult(ctx, 'reason')))))))))
  })

  ServerEvents.tick(event => {
    if (event.server.getTickCount() % 20 != 0) return
    try {
      expireBans(event.server)
    } catch (e) {
      console.error(`[invites] Abgelaufene Banns aufheben: ${e}`)
    }
  })
})()
