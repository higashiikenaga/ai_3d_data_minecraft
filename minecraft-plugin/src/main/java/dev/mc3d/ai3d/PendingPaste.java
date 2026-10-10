package dev.mc3d.ai3d;

import com.sk89q.worldedit.extent.clipboard.Clipboard;
import com.sk89q.worldedit.math.BlockVector3;
import org.bukkit.World;

/** A generated build waiting for the player's confirmation. */
final class PendingPaste {
    final String name;
    final Clipboard clipboard;
    World world;
    BlockVector3 to;
    final long expiresAt;

    PendingPaste(String name, Clipboard clipboard, World world, BlockVector3 to, long expiresAt) {
        this.name = name;
        this.clipboard = clipboard;
        this.world = world;
        this.to = to;
        this.expiresAt = expiresAt;
    }

    /** Minimum corner in world coordinates when pasted at {@link #to}. */
    BlockVector3 min() {
        return clipboard.getRegion().getMinimumPoint().subtract(clipboard.getOrigin()).add(to);
    }

    /** Maximum corner (inclusive) in world coordinates when pasted at {@link #to}. */
    BlockVector3 max() {
        return clipboard.getRegion().getMaximumPoint().subtract(clipboard.getOrigin()).add(to);
    }
}
