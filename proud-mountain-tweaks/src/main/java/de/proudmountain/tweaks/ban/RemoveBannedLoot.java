package de.proudmountain.tweaks.ban;

import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import it.unimi.dsi.fastutil.objects.ObjectArrayList;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.storage.loot.LootContext;
import net.minecraft.world.level.storage.loot.predicates.LootItemCondition;
import net.neoforged.neoforge.common.loot.IGlobalLootModifier;
import net.neoforged.neoforge.common.loot.LootModifier;

/** Globaler Loot-Modifier: entfernt verbannte Items aus jedem erzeugten Loot, siehe BannedItems. */
public final class RemoveBannedLoot extends LootModifier {
    public static final MapCodec<RemoveBannedLoot> CODEC =
            RecordCodecBuilder.mapCodec(inst -> codecStart(inst).apply(inst, RemoveBannedLoot::new));

    public RemoveBannedLoot(LootItemCondition[] conditions) {
        super(conditions);
    }

    @Override
    protected ObjectArrayList<ItemStack> doApply(ObjectArrayList<ItemStack> loot, LootContext context) {
        loot.removeIf(stack -> stack.is(BannedItems.TAG));
        return loot;
    }

    @Override
    public MapCodec<? extends IGlobalLootModifier> codec() {
        return CODEC;
    }
}
