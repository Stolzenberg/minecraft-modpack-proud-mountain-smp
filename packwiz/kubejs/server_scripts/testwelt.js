// Testwelt: flache Creative-Dimension zum Ausprobieren von Bauwerken und Maschinen
//
// /testwelt bringt jeden Spieler in die Dimension proudmountain:testwelt und beim zweiten Aufruf zurück an die
// Stelle, an der er die normale Welt verlassen hat. Die Dimension kommt aus dem Datapack in
// kubejs/data/proudmountain/ (dimension, dimension_type, worldgen/biome): Grundgestein und 15 Schichten grauer
// Beton (Oberfläche y = 16), keine Strukturen, keine Features, Biom ohne Spawns und Niederschlag, immer Mittag.
//
// Strenge Trennung: Jeder Spieler hat ein Survival- und ein Testwelt-Profil (Inventar mit Rüstung und Offhand,
// Curios-Slots, Endertruhe, XP, Leben, Hunger, Effekte, Feuer, Spielmodus).
// Getauscht wird immer dann, wenn Dimension und aktives Profil nicht zusammenpassen: beim Dimensionswechsel,
// Login, Respawn und zusätzlich jede Sekunde. Das gerade inaktive Profil liegt in server.persistentData.
// Hinein und hinaus geht es nur per /testwelt: Portale, Waystones usw. von oder in die
// Testwelt werden blockiert, auch für Items, Tiere und Fahrzeuge.
// Mobs gibt es nur aus Spawn-Eiern (auch per Werfer), Eimern und /summon, dazu deren Nachwuchs, Umwandlungen und
// von ihnen gerufene Mobs. Höchstens MAX_MOBS gleichzeitig, /testwelt mobs entfernt alle Mobs im Umkreis.
// Kills in der Testwelt zählen nicht für die Statistik.
// In der Testwelt außerdem gesperrt:
//   - natürliche Spawns, Spawner, Golems und Wither aus Blöcken
//   - Waystones (globales Netz), Paraglider-Statuen und -Upgrades (Herz/Ausdauer gelten dauerhaft),
//     Endportalrahmen, Netherportale, Respawnpunkte
// Advancements und Statistiken sind nicht getrennt.

;(function () {
  const DATA_KEY = 'proudmountain_testwelt'
  const DIM = 'proudmountain:testwelt'
  const SPAWN = [0.5, 16, 0.5]
  const VOID_Y = -8 // wer darunter fällt (Bedrock im Creative abgebaut), landet wieder auf der Oberfläche
  const HURT_COOLDOWN = 200 // nach Schaden 10 s kein Betreten (keine Flucht aus Kämpfen)
  const BLOCKED_BLOCKS = [/^waystones:/, /^paraglider:.*statue$/, /^minecraft:end_portal_frame$/]
  const BLOCKED_ITEMS = ['paraglider:heart_container', 'paraglider:stamina_vessel', 'paraglider:anti_vessel', 'paraglider:essence']
  const TAG_COMPOUND = 10
  const MAX_MOBS = 150 // gleichzeitig geladene Mobs in der Testwelt, gegen Lag
  const MOB_CLEAR_RADIUS = 64 // für /testwelt mobs
  // Ohne Spawn-Art entstehen Golems und Wither aus Blöcken, aber auch Nachwuchs (siehe mobAllowed)
  const BLOCKED_SPAWN_TYPES = ['NATURAL', 'CHUNK_GENERATION', 'SPAWNER', 'TRIAL_SPAWNER', 'STRUCTURE', 'PATROL', 'EVENT', 'TRIGGERED']

  const $CompoundTag = Java.loadClass('net.minecraft.nbt.CompoundTag')
  const $ListTag = Java.loadClass('net.minecraft.nbt.ListTag')
  const $GameType = Java.loadClass('net.minecraft.world.level.GameType')
  const $MobEffectInstance = Java.loadClass('net.minecraft.world.effect.MobEffectInstance')
  const $ItemStack = Java.loadClass('net.minecraft.world.item.ItemStack')
  const $Mob = Java.loadClass('net.minecraft.world.entity.Mob')
  const $AgeableMob = Java.loadClass('net.minecraft.world.entity.AgeableMob')
  const $ResourceLocation = Java.loadClass('net.minecraft.resources.ResourceLocation')
  const $CuriosApi = Java.loadClass('top.theillusivec4.curios.api.CuriosApi')
  const $TravelEvent = Java.loadClass('net.neoforged.neoforge.event.entity.EntityTravelToDimensionEvent')
  const $ChangedDimensionEvent = Java.loadClass('net.neoforged.neoforge.event.entity.player.PlayerEvent$PlayerChangedDimensionEvent')
  const $SetSpawnEvent = Java.loadClass('net.neoforged.neoforge.event.entity.player.PlayerSetSpawnEvent')
  const $PortalSpawnEvent = Java.loadClass('net.neoforged.neoforge.event.level.BlockEvent$PortalSpawnEvent')
  const $JoinLevelEvent = Java.loadClass('net.neoforged.neoforge.event.entity.EntityJoinLevelEvent')
  const $StatAwardEvent = Java.loadClass('net.neoforged.neoforge.event.StatAwardEvent')

  const travelAllowed = {} // UUIDs, die gerade per /testwelt reisen
  const lastHurt = {} // UUID → Server-Tick des letzten Schadens
  const lastNotice = {} // UUID → Server-Tick der letzten Sperr-Meldung

  // KubeJS überdeckt Level.dimension() mit einer Eigenschaft (ResourceLocation)
  function dimName(level) {
    return String(level.dimension)
  }

  function isTest(level) {
    return dimName(level) == DIM
  }

  function levelByName(server, name) {
    return server.getLevel($ResourceLocation.parse(name))
  }

  function uuid(player) {
    return String(player.uuid)
  }

  function notice(player, msg) {
    let id = uuid(player)
    let now = player.getServer().getTickCount()
    if (lastNotice[id] && now - lastNotice[id] < 60) return
    lastNotice[id] = now
    player.displayClientMessage(Text.of(msg).red(), true)
  }

  // --- Profile -------------------------------------------------------------------------------------------

  function allData(server) {
    let data = server.persistentData
    if (!data.contains(DATA_KEY)) data.put(DATA_KEY, new $CompoundTag())
    return data.getCompound(DATA_KEY)
  }

  function playerData(player) {
    let all = allData(player.getServer())
    let id = uuid(player)
    if (!all.contains(id)) all.put(id, new $CompoundTag())
    return all.getCompound(id)
  }

  function curios(player) {
    let opt = $CuriosApi.getCuriosInventory(player)
    return opt.isPresent() ? opt.get() : null
  }

  // Methoden mit ListTag-Parameter (Inventory.load, fromTag, loadInventory) lassen sich aus KubeJS nicht
  // aufrufen, Rhino macht aus der Liste eine ArrayList. Deshalb wird Slot für Slot gespeichert.
  function saveStack(list, stack, reg, slot) {
    if (stack.isEmpty()) return
    let t = new $CompoundTag()
    t.putInt('slot', slot)
    t.put('item', stack.save(reg))
    list.add(t)
  }

  function saveContainer(container, reg) {
    let list = new $ListTag()
    for (let i = 0; i < container.getContainerSize(); i++) saveStack(list, container.getItem(i), reg, i)
    return list
  }

  function loadContainer(container, list, reg) {
    container.clearContent()
    for (let i = 0; i < list.size(); i++) {
      let t = list.getCompound(i)
      container.setItem(t.getInt('slot'), $ItemStack.parseOptional(reg, t.getCompound('item')))
    }
  }

  // Curios-Slots je Typ (Kleidung, Rucksack …), normale und kosmetische Slots
  function curioHandlers(player, fn) {
    let c = curios(player)
    if (!c) return
    c.getCurios().forEach((id, handler) => {
      fn(String(id), false, handler.getStacks())
      fn(String(id), true, handler.getCosmeticStacks())
    })
  }

  function saveCurios(player, reg) {
    let list = new $ListTag()
    curioHandlers(player, (id, cosmetic, stacks) => {
      for (let i = 0; i < stacks.getSlots(); i++) {
        let before = list.size()
        saveStack(list, stacks.getStackInSlot(i), reg, i)
        if (list.size() > before) {
          list.getCompound(before).putString('id', id)
          list.getCompound(before).putBoolean('cosmetic', cosmetic)
        }
      }
    })
    return list
  }

  function loadCurios(player, list, reg) {
    let slots = {}
    curioHandlers(player, (id, cosmetic, stacks) => {
      slots[id + (cosmetic ? '#cosmetic' : '')] = stacks
      for (let i = 0; i < stacks.getSlots(); i++) stacks.setStackInSlot(i, $ItemStack.EMPTY)
    })
    for (let i = 0; i < list.size(); i++) {
      let t = list.getCompound(i)
      let stack = $ItemStack.parseOptional(reg, t.getCompound('item'))
      let stacks = slots[t.getString('id') + (t.getBoolean('cosmetic') ? '#cosmetic' : '')]
      let slot = t.getInt('slot')
      if (stacks && slot < stacks.getSlots()) stacks.setStackInSlot(slot, stack)
      else player.getInventory().placeItemBackInInventory(stack) // Slot gibt es nicht mehr
    }
  }

  // Liest alles, was getrennt werden muss, ohne etwas zu verändern
  function readProfile(player) {
    let reg = player.registryAccess()
    let p = new $CompoundTag()
    let inv = player.getInventory()
    p.put('inventory', saveContainer(inv, reg))
    p.putInt('selected', inv.selected)
    p.put('ender', saveContainer(player.getEnderChestInventory(), reg))
    p.put('curios', saveCurios(player, reg))
    p.putInt('xpLevel', player.experienceLevel)
    p.putFloat('xpProgress', player.experienceProgress)
    p.putInt('xpTotal', player.totalExperience)
    p.putFloat('health', player.getHealth())
    let food = player.getFoodData()
    p.putInt('food', food.getFoodLevel())
    p.putFloat('saturation', food.getSaturationLevel())
    let effects = new $ListTag()
    player.getActiveEffects().forEach(e => effects.add(e.save()))
    p.put('effects', effects)
    p.putInt('fire', player.getRemainingFireTicks())
    p.putString('gamemode', player.gameMode.getGameModeForPlayer().getName())
    return p
  }

  // Setzt ein Profil; ein leeres Profil (erster Besuch) ergibt leeres Inventar, volle Leiste, keine Effekte
  function applyProfile(player, p, creative) {
    let reg = player.registryAccess()
    let fresh = !p.contains('health')
    let inv = player.getInventory()
    loadContainer(inv, p.getList('inventory', TAG_COMPOUND), reg) // samt Rüstung und Offhand
    inv.selected = fresh ? 0 : p.getInt('selected')
    loadContainer(player.getEnderChestInventory(), p.getList('ender', TAG_COMPOUND), reg)
    loadCurios(player, p.getList('curios', TAG_COMPOUND), reg)
    player.experienceProgress = fresh ? 0 : p.getFloat('xpProgress')
    player.totalExperience = fresh ? 0 : p.getInt('xpTotal')
    player.setExperienceLevels(fresh ? 0 : p.getInt('xpLevel'))
    player.removeAllEffects()
    let effects = p.getList('effects', TAG_COMPOUND)
    for (let i = 0; i < effects.size(); i++) {
      let e = $MobEffectInstance.load(effects.getCompound(i))
      if (e) player.addEffect(e)
    }
    player.setHealth(fresh ? player.getMaxHealth() : Math.max(1, p.getFloat('health')))
    let food = player.getFoodData()
    food.setFoodLevel(fresh ? 20 : p.getInt('food'))
    food.setSaturation(fresh ? 5 : p.getFloat('saturation'))
    player.setRemainingFireTicks(fresh ? 0 : p.getInt('fire'))
    player.setGameMode(creative ? $GameType.CREATIVE : $GameType.byName(p.getString('gamemode'), $GameType.SURVIVAL))
    player.resetFallDistance()
  }

  function swap(player, toTest) {
    let d = playerData(player)
    let other = d.getCompound('stored').copy()
    // Erst das aktuelle Profil sichern, dann überschreiben: Bei einem Fehler geht nichts verloren
    d.put('stored', readProfile(player))
    d.putString('active', toTest ? 'test' : 'survival')
    try {
      applyProfile(player, other, toTest)
    } catch (e) {
      d.put('recovery_' + Date.now(), other)
      throw e
    }
    console.info(`[testwelt] ${player.getScoreboardName()}: Profil ${toTest ? 'Testwelt' : 'Survival'} geladen`)
  }

  // Bringt das aktive Profil in Einklang mit der Dimension, in der der Spieler gerade ist
  function ensure(player) {
    let inTest = isTest(player.level)
    let all = allData(player.getServer())
    let active = all.getCompound(uuid(player)).getString('active') == 'test'
    if (inTest != active) swap(player, inTest)
    else if (inTest && !player.isCreative() && !player.isSpectator()) player.setGameMode($GameType.CREATIVE)
  }

  function safeEnsure(player) {
    try {
      ensure(player)
    } catch (e) {
      console.error(`[testwelt] Profilwechsel für ${player.getScoreboardName()} fehlgeschlagen: ${e}`)
    }
  }

  // --- Reisen --------------------------------------------------------------------------------------------

  function posTag(player) {
    let t = new $CompoundTag()
    t.putString('dim', dimName(player.level))
    t.putDouble('x', player.getX())
    t.putDouble('y', player.getY())
    t.putDouble('z', player.getZ())
    t.putFloat('yaw', player.yaw) // KubeJS benennt getYRot/getXRot in yaw/pitch um
    t.putFloat('pitch', player.pitch)
    return t
  }

  function teleport(player, level, x, y, z, yaw, pitch) {
    let id = uuid(player)
    player.stopRiding()
    player.closeMenu() // KubeJS-Name für closeContainer
    travelAllowed[id] = true
    try {
      // per ResourceLocation, mit ServerLevel ist der Aufruf neben KubeJS' eigener Variante mehrdeutig
      player.teleportTo($ResourceLocation.parse(dimName(level)), x, y, z, yaw, pitch)
    } finally {
      delete travelAllowed[id]
    }
    player.resetFallDistance()
    safeEnsure(player)
  }

  function enter(player) {
    let server = player.getServer()
    let level = levelByName(server, DIM)
    if (!level) return 'Die Testwelt ist auf diesem Server nicht geladen.'
    let since = server.getTickCount() - (lastHurt[uuid(player)] || -HURT_COOLDOWN)
    if (since < HURT_COOLDOWN) return `Du hast gerade Schaden genommen. Warte noch ${Math.ceil((HURT_COOLDOWN - since) / 20)} s.`
    if (player.isSleeping()) return 'Nicht im Schlaf.'
    if (player.fallDistance > 3 || player.isInLava() || player.isOnFire()) return 'Nicht im Fallen oder Brennen.'
    let d = playerData(player)
    d.put('return', posTag(player))
    let last = d.getCompound('last')
    if (last.contains('x')) teleport(player, level, last.getDouble('x'), last.getDouble('y'), last.getDouble('z'), last.getFloat('yaw'), last.getFloat('pitch'))
    else teleport(player, level, SPAWN[0], SPAWN[1], SPAWN[2], 0, 0)
    player.tell(Text.of('Testwelt betreten: Creative-Modus, eigenes Inventar. Nichts von hier gelangt in die normale Welt. Zurück mit /testwelt.').gold())
    return null
  }

  function leave(player, rememberPosition) {
    let server = player.getServer()
    let d = playerData(player)
    if (rememberPosition) d.put('last', posTag(player))
    let r = d.getCompound('return')
    let level = r.contains('dim') ? levelByName(server, r.getString('dim')) : null
    if (level) {
      teleport(player, level, r.getDouble('x'), r.getDouble('y'), r.getDouble('z'), r.getFloat('yaw'), r.getFloat('pitch'))
    } else {
      let spawn = server.overworld().getSharedSpawnPos()
      teleport(player, server.overworld(), spawn.getX() + 0.5, spawn.getY(), spawn.getZ() + 0.5, 0, 0)
    }
    player.tell(Text.of('Zurück in der normalen Welt, dein Inventar ist wieder da.').gold())
  }

  // --- Mobs ----------------------------------------------------------------------------------------------

  // Spawn-Art merkt sich NeoForge am Mob (auch über Neustarts, NBT neoforge:spawn_type)
  function mobAllowed(mob) {
    let type = mob.getSpawnType()
    if (type == null) return mob instanceof $AgeableMob && mob.isBaby() // Zucht, Spawn-Ei auf Tier, Hühnerei
    return !BLOCKED_SPAWN_TYPES.includes(String(type))
  }

  function testMobs(level, fn) {
    level.getAllEntities().forEach(e => {
      if (e instanceof $Mob) fn(e)
    })
  }

  function clearMobs(player) {
    let mobs = []
    let r2 = MOB_CLEAR_RADIUS * MOB_CLEAR_RADIUS
    testMobs(player.level, m => {
      if (m.distanceToSqr(player.getX(), player.getY(), player.getZ()) <= r2) mobs.push(m)
    })
    mobs.forEach(m => m.discard()) // erst sammeln, dann entfernen, ohne Drops
    return mobs.length
  }

  ServerEvents.commandRegistry(event => {
    const { commands: Commands } = event
    event.register(Commands.literal('testwelt').executes(ctx => {
      let player = ctx.source.getPlayerOrException()
      try {
        if (isTest(player.level)) {
          leave(player, true)
        } else {
          let refusal = enter(player)
          if (refusal) {
            player.tell(Text.of(refusal).red())
            return 0
          }
        }
      } catch (e) {
        console.error(`[testwelt] /testwelt für ${player.getScoreboardName()}: ${e}`)
        player.tell(Text.of('Testwelt: Fehler, siehe Server-Log.').red())
        return 0
      }
      return 1
    }).then(Commands.literal('mobs').executes(ctx => {
      let player = ctx.source.getPlayerOrException()
      if (!isTest(player.level)) {
        player.tell(Text.of('/testwelt mobs geht nur in der Testwelt.').red())
        return 0
      }
      let n = clearMobs(player)
      player.tell(Text.of(`${n} Mobs im Umkreis von ${MOB_CLEAR_RADIUS} Blöcken entfernt.`).gold())
      return 1
    })))
  })

  // Jede andere Reise von oder in die Testwelt abbrechen (Portale, Waystones, Teleport-Befehle, Items, Züge …)
  NativeEvents.onEvent($TravelEvent, event => {
    let entity = event.getEntity()
    let fromTest = isTest(entity.level)
    let toTest = String(event.getDimension().location()) == DIM
    if (!fromTest && !toTest) return
    if (travelAllowed[String(entity.uuid)]) return
    event.setCanceled(true)
    if (entity.isPlayer()) notice(entity, 'In die Testwelt und hinaus geht es nur mit /testwelt.')
  })

  NativeEvents.onEvent($ChangedDimensionEvent, event => safeEnsure(event.getEntity()))

  NativeEvents.onEvent($SetSpawnEvent, event => {
    let spawn = event.getSpawnLevel()
    if (spawn && String(spawn.location()) == DIM) event.setCanceled(true)
  })

  NativeEvents.onEvent($PortalSpawnEvent, event => {
    let level = event.getLevel()
    if (level.dimension && isTest(level)) event.setCanceled(true)
  })

  PlayerEvents.loggedIn(event => safeEnsure(event.player))

  PlayerEvents.respawned(event => {
    let player = event.player
    try {
      // In der Testwelt gestorben (z. B. ins Void): zurück an den Ausgangspunkt mit dem Survival-Profil
      if (!isTest(player.level) && playerData(player).getString('active') == 'test') leave(player, false)
      else ensure(player)
    } catch (e) {
      console.error(`[testwelt] Respawn von ${player.getScoreboardName()}: ${e}`)
    }
  })

  EntityEvents.afterHurt(event => {
    let entity = event.entity
    if (entity.isPlayer()) lastHurt[uuid(entity)] = entity.getServer().getTickCount()
  })

  NativeEvents.onEvent($JoinLevelEvent, event => {
    let mob = event.getEntity()
    let level = event.getLevel()
    // Aus dem Speicher geladene Mobs wurden schon beim Spawnen geprüft (Nachwuchs ist inzwischen evtl. erwachsen)
    if (!(mob instanceof $Mob) || event.loadedFromDisk() || !isTest(level)) return
    if (!mobAllowed(mob)) {
      event.setCanceled(true)
      return
    }
    let count = 0
    testMobs(level, () => count++)
    if (count < MAX_MOBS) return
    event.setCanceled(true)
    let player = level['getNearestPlayer(net.minecraft.world.entity.Entity,double)'](mob, 16)
    if (player) notice(player, `Zu viele Mobs in der Testwelt (${MAX_MOBS}). Aufräumen mit /testwelt mobs.`)
  })

  // Kills in der Testwelt nicht in die Statistik (Stats-Dashboard)
  NativeEvents.onEvent($StatAwardEvent, event => {
    let player = event.getEntity()
    if (!isTest(player.level)) return
    let name = String(event.getStat().getName())
    if (name.startsWith('minecraft.killed:') || name == 'minecraft.custom:minecraft.mob_kills') event.setCanceled(true)
  })

  BlockEvents.placed(event => {
    if (!isTest(event.level)) return
    let id = String(event.block.id)
    if (!BLOCKED_BLOCKS.some(r => r.test(id))) return
    if (event.player) notice(event.player, 'Dieser Block ist in der Testwelt gesperrt.')
    // Bau-Werkzeuge mancher Mods melden die Platzierung erst danach und ignorieren den Abbruch
    let level = event.level
    let pos = event.block.pos
    event.server.scheduleInTicks(1, () => {
      if (String(level.getBlock(pos).id) == id) level.removeBlock(pos, false)
    })
    event.cancel()
  })

  ItemEvents.rightClicked(event => {
    if (!isTest(event.level) || !BLOCKED_ITEMS.includes(String(event.item.id))) return
    notice(event.player, 'Dauerhafte Upgrades sind in der Testwelt gesperrt.')
    event.cancel()
  })

  ServerEvents.tick(event => {
    let server = event.server
    let level = levelByName(server, DIM)
    if (!level) return
    // Wetter teilt sich die Dimension mit der Overworld: Regenlevel auf 0 halten, sonst wird der Himmel grau
    level.setRainLevel(0)
    level.setThunderLevel(0)
    let players = server.getPlayerList().getPlayers()
    if (server.getTickCount() % 5 == 0) {
      players.forEach(p => {
        if (!isTest(p.level) || p.getY() >= VOID_Y) return
        p.teleportTo(p.getX(), SPAWN[1], p.getZ())
        p.setMotion(0, 0, 0)
        p.resetFallDistance()
      })
    }
    if (server.getTickCount() % 20 == 0) players.forEach(p => safeEnsure(p))
  })
})()
