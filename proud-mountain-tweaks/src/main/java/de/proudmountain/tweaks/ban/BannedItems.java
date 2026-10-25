package de.proudmountain.tweaks.ban;

import com.mojang.serialization.MapCodec;
import de.proudmountain.tweaks.ProudMountainTweaks;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.tags.TagKey;
import net.minecraft.world.entity.decoration.ItemFrame;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.common.loot.IGlobalLootModifier;
import net.neoforged.neoforge.event.entity.EntityJoinLevelEvent;
import net.neoforged.neoforge.event.tick.PlayerTickEvent;
import net.neoforged.neoforge.registries.DeferredRegister;
import net.neoforged.neoforge.registries.NeoForgeRegistries;

/**
 * Verbannte Items (Tag proudmountain_tweaks:banned, derzeit Elytren) gibt es auf dem Server nicht:
 * Loot (Truhen, Lootr, Vaults, Mobs) verliert sie per globalem Loot-Modifier, Item-Frames in Strukturen
 * (Endschiff, Moog's End Structures) werden beim Laden geleert, Item-Entities verschwinden, und wer doch
 * eine im Inventar hat (Creative, /give), verliert sie nach spätestens einer Sekunde.
 * Lootr darf die Frames vorher nicht übernehmen: lootr:convert/item_frame_blacklist und
 * convert_elytras_to_item_frames = false in config/lootr-common.toml.
 */
public final class BannedItems {
    public static final TagKey<Item> TAG =
            TagKey.create(Registries.ITEM, ResourceLocation.fromNamespaceAndPath(ProudMountainTweaks.MOD_ID, "banned"));
    private static final int INTERVAL = 20;

    private static final DeferredRegister<MapCodec<? extends IGlobalLootModifier>> LOOT_MODIFIERS =
            DeferredRegister.create(NeoForgeRegistries.Keys.GLOBAL_LOOT_MODIFIER_SERIALIZERS, ProudMountainTweaks.MOD_ID);

    static {
        LOOT_MODIFIERS.register("remove_banned", () -> RemoveBannedLoot.CODEC);
    }

    private BannedItems() {
    }

    public static void init(IEventBus modBus) {
        LOOT_MODIFIERS.register(modBus);
        NeoForge.EVENT_BUS.addListener(EntityJoinLevelEvent.class, BannedItems::onEntityJoin);
        NeoForge.EVENT_BUS.addListener(PlayerTickEvent.Post.class, BannedItems::onPlayerTick);
    }

    private static void onEntityJoin(EntityJoinLevelEvent event) {
        if (event.getLevel().isClientSide()) {
            return;
        }
        if (event.getEntity() instanceof ItemFrame frame && frame.getItem().is(TAG)) {
            frame.setItem(ItemStack.EMPTY, false); // ohne Nachbar-Update, der Chunk lädt gerade erst
        } else if (event.getEntity() instanceof ItemEntity item && item.getItem().is(TAG)) {
            event.setCanceled(true);
        }
    }

    private static void onPlayerTick(PlayerTickEvent.Post event) {
        if (!(event.getEntity() instanceof ServerPlayer player) || player.tickCount % INTERVAL != 0) {
            return;
        }
        // Inventar samt Rüstung und Offhand, Crafting-Feld und Maus-Cursor
        int removed = player.getInventory().clearOrCountMatchingItems(
                stack -> stack.is(TAG), -1, player.inventoryMenu.getCraftSlots());
        if (removed > 0) {
            player.containerMenu.broadcastChanges();
            player.displayClientMessage(Component.literal("Elytren sind auf diesem Server verbannt."), true);
        }
    }
}
