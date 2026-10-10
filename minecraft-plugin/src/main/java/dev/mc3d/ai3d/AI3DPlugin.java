package dev.mc3d.ai3d;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.sk89q.worldedit.EditSession;
import com.sk89q.worldedit.LocalSession;
import com.sk89q.worldedit.WorldEdit;
import com.sk89q.worldedit.WorldEditException;
import com.sk89q.worldedit.bukkit.BukkitAdapter;
import com.sk89q.worldedit.extent.clipboard.Clipboard;
import com.sk89q.worldedit.extent.clipboard.io.ClipboardFormat;
import com.sk89q.worldedit.extent.clipboard.io.ClipboardFormats;
import com.sk89q.worldedit.extent.clipboard.io.ClipboardReader;
import com.sk89q.worldedit.function.operation.Operation;
import com.sk89q.worldedit.function.operation.Operations;
import com.sk89q.worldedit.math.BlockVector3;
import com.sk89q.worldedit.regions.selector.CuboidRegionSelector;
import com.sk89q.worldedit.session.ClipboardHolder;
import net.md_5.bungee.api.ChatColor;
import net.md_5.bungee.api.ChatMessageType;
import net.md_5.bungee.api.chat.BaseComponent;
import net.md_5.bungee.api.chat.ClickEvent;
import net.md_5.bungee.api.chat.ComponentBuilder;
import net.md_5.bungee.api.chat.HoverEvent;
import net.md_5.bungee.api.chat.TextComponent;
import net.md_5.bungee.api.chat.hover.content.Text;
import org.bukkit.Bukkit;
import org.bukkit.Particle;
import org.bukkit.World;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

public final class AI3DPlugin extends JavaPlugin implements Listener, TabCompleter {
    private static final String PREFIX = ChatColor.AQUA + "[AI3D] " + ChatColor.RESET;
    private static final List<String> SUBCOMMANDS =
            Arrays.asList("confirm", "cancel", "here", "status", "load", "reload", "help");
    private static final List<String> FLAGS =
            Arrays.asList("--size", "--fill", "--hollow", "--quality", "--seed", "--palette", "--height");

    private GeneratorClient client;
    /** Players with a generation in progress -> job id ("" while submitting). */
    private final Map<UUID, String> running = new ConcurrentHashMap<>();
    private final Map<UUID, PendingPaste> pending = new ConcurrentHashMap<>();
    private BukkitTask particleTask;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        loadSettings();
        Bukkit.getPluginManager().registerEvents(this, this);
        getCommand("ai3d").setTabCompleter(this);
        particleTask = Bukkit.getScheduler().runTaskTimer(this, this::tickPending, 20L, 10L);
    }

    @Override
    public void onDisable() {
        if (particleTask != null) {
            particleTask.cancel();
        }
        pending.clear();
        running.clear();
    }

    private void loadSettings() {
        reloadConfig();
        client = new GeneratorClient(getConfig().getString("server-url", "http://127.0.0.1:8765"),
                getConfig().getString("api-key", ""));
    }

    // ------------------------------------------------------------------ commands

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (args.length == 0 || args[0].equalsIgnoreCase("help")) {
            sendHelp(sender, label);
            return true;
        }
        String sub = args[0].toLowerCase(Locale.ROOT);
        if (sub.equals("reload")) {
            if (!sender.hasPermission("ai3d.admin")) {
                sender.sendMessage(PREFIX + ChatColor.RED + "権限がありません");
                return true;
            }
            loadSettings();
            sender.sendMessage(PREFIX + "設定を再読み込みしました");
            return true;
        }
        if (!(sender instanceof Player)) {
            sender.sendMessage(PREFIX + "プレイヤーのみ実行できます");
            return true;
        }
        Player player = (Player) sender;
        switch (sub) {
            case "confirm":
                confirm(player);
                return true;
            case "cancel":
                cancel(player);
                return true;
            case "here":
                moveHere(player);
                return true;
            case "status":
                status(player);
                return true;
            case "load":
                if (args.length < 2) {
                    player.sendMessage(PREFIX + "使い方: /" + label + " load <schem名>");
                } else {
                    loadExisting(player, args[1]);
                }
                return true;
            default:
                generate(player, args);
                return true;
        }
    }

    private void sendHelp(CommandSender s, String label) {
        s.sendMessage(PREFIX + "AIで3Dを生成して建築にします");
        s.sendMessage(ChatColor.YELLOW + "/" + label + " <プロンプト> [--size N] [--fill] [--quality] [--seed N] [--palette wool,concrete]");
        s.sendMessage(ChatColor.GRAY + "  例: /" + label + " a medieval castle with towers --size 64");
        s.sendMessage(ChatColor.YELLOW + "/" + label + " confirm" + ChatColor.GRAY + "  表示中の範囲に貼り付け (//undo で戻せます)");
        s.sendMessage(ChatColor.YELLOW + "/" + label + " here" + ChatColor.GRAY + "     今いる場所に範囲を移動");
        s.sendMessage(ChatColor.YELLOW + "/" + label + " cancel" + ChatColor.GRAY + "   キャンセル");
        s.sendMessage(ChatColor.YELLOW + "/" + label + " status" + ChatColor.GRAY + "   生成状況");
        s.sendMessage(ChatColor.YELLOW + "/" + label + " load <名前>" + ChatColor.GRAY + " 保存済みschemを確認付きで貼り付け");
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        if (args.length == 1) {
            return SUBCOMMANDS.stream().filter(s -> s.startsWith(args[0].toLowerCase(Locale.ROOT)))
                    .collect(Collectors.toList());
        }
        if (args.length == 2 && args[0].equalsIgnoreCase("load")) {
            return listSchematics().stream().filter(s -> s.startsWith(args[1])).collect(Collectors.toList());
        }
        String last = args[args.length - 1];
        if (last.startsWith("-")) {
            return FLAGS.stream().filter(f -> f.startsWith(last)).collect(Collectors.toList());
        }
        return new ArrayList<>();
    }

    // ------------------------------------------------------------------ generation

    private void generate(Player player, String[] args) {
        UUID id = player.getUniqueId();
        if (running.containsKey(id)) {
            player.sendMessage(PREFIX + ChatColor.RED + "生成中のジョブがあります。/ai3d status で確認できます");
            return;
        }
        JsonObject params;
        try {
            params = parseArgs(player, args);
        } catch (IllegalArgumentException e) {
            player.sendMessage(PREFIX + ChatColor.RED + e.getMessage());
            return;
        }
        running.put(id, "");
        String prompt = params.get("prompt").getAsString();
        player.sendMessage(PREFIX + "生成を開始します: " + ChatColor.WHITE + prompt
                + ChatColor.GRAY + " (" + params.get("size").getAsInt() + "ブロック)");

        Bukkit.getScheduler().runTaskAsynchronously(this, () -> {
            String jobId;
            try {
                jobId = client.submit(params).get("id").getAsString();
            } catch (Exception e) {
                running.remove(id, "");
                message(id, ChatColor.RED + "生成サーバーに接続できません: " + e.getMessage());
                return;
            }
            if (!running.replace(id, "", jobId)) {
                return; // cancelled while submitting
            }
            try {
                pollUntilDone(id, jobId);
            } catch (InterruptedException e) {
                running.remove(id, jobId);
                Thread.currentThread().interrupt();
            }
        });
    }

    private JsonObject parseArgs(Player player, String[] args) {
        int size = getConfig().getInt("default-size", 48);
        boolean fill = getConfig().getBoolean("fill", false);
        boolean quality = false;
        boolean height = false;
        Integer seed = null;
        String palette = getConfig().getString("palette", "");
        List<String> words = new ArrayList<>();
        for (int i = 0; i < args.length; i++) {
            String a = args[i];
            switch (a.toLowerCase(Locale.ROOT)) {
                case "--size":
                case "-s":
                    size = parseInt(args, ++i, "--size");
                    break;
                case "--seed":
                    seed = parseInt(args, ++i, "--seed");
                    break;
                case "--palette":
                    if (++i >= args.length) throw new IllegalArgumentException("--palette の値がありません");
                    palette = args[i];
                    break;
                case "--fill":
                    fill = true;
                    break;
                case "--hollow":
                    fill = false;
                    break;
                case "--quality":
                    quality = true;
                    break;
                case "--height":
                    height = true;
                    break;
                default:
                    words.add(a);
            }
        }
        if (words.isEmpty()) {
            throw new IllegalArgumentException("プロンプトを入力してください (英語推奨)");
        }
        int max = getConfig().getInt("max-size", 128);
        if (size < 4 || (size > max && !player.hasPermission("ai3d.admin"))) {
            throw new IllegalArgumentException("サイズは 4〜" + max + " で指定してください");
        }
        JsonObject p = new JsonObject();
        p.addProperty("prompt", String.join(" ", words));
        p.addProperty("size", size);
        p.addProperty("fill", fill);
        p.addProperty("quality", quality);
        p.addProperty("fit", height ? "height" : "max");
        p.addProperty("seed", seed != null ? seed : (int) (Math.random() * 1_000_000));
        p.addProperty("mc_version", detectMcVersion());
        if (palette != null && !palette.isEmpty()) {
            p.addProperty("palette", palette);
        }
        return p;
    }

    private static int parseInt(String[] args, int i, String flag) {
        if (i >= args.length) throw new IllegalArgumentException(flag + " の値がありません");
        try {
            return Integer.parseInt(args[i]);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(flag + " には数値を指定してください");
        }
    }

    /** Map the running server version onto one of the versions mc3d knows (block availability). */
    private static String detectMcVersion() {
        String v = Bukkit.getBukkitVersion().split("-")[0];
        String[] known = {"1.21.4", "1.21.1", "1.20.6", "1.20.4", "1.20.1", "1.19.4", "1.18.2",
                "1.17.1", "1.16.5", "1.15.2", "1.14.4", "1.13.2"};
        for (String k : known) {
            if (compareVersions(v, k) >= 0) return k;
        }
        return "1.13.2";
    }

    private static int compareVersions(String a, String b) {
        String[] x = a.split("\\."), y = b.split("\\.");
        for (int i = 0; i < Math.max(x.length, y.length); i++) {
            int xi = i < x.length ? parseOr0(x[i]) : 0, yi = i < y.length ? parseOr0(y[i]) : 0;
            if (xi != yi) return Integer.compare(xi, yi);
        }
        return 0;
    }

    private static int parseOr0(String s) {
        try {
            return Integer.parseInt(s);
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    /** Runs on an async thread: poll the job, then download and load the schematic. */
    private void pollUntilDone(UUID playerId, String jobId) throws InterruptedException {
        long interval = Math.max(1, getConfig().getInt("poll-interval-seconds", 2)) * 1000L;
        long deadline = System.currentTimeMillis() + getConfig().getInt("timeout-seconds", 900) * 1000L;
        String lastLabel = null;
        int failures = 0;
        // Stops as soon as the player cancels (the entry is removed or replaced).
        while (jobId.equals(running.get(playerId))) {
            if (System.currentTimeMillis() > deadline) {
                running.remove(playerId, jobId);
                message(playerId, ChatColor.RED + "タイムアウトしました");
                return;
            }
            JsonObject st;
            try {
                st = client.status(jobId);
                failures = 0;
            } catch (IOException e) {
                if (++failures >= 5) {
                    running.remove(playerId, jobId);
                    message(playerId, ChatColor.RED + "生成サーバーとの通信に失敗しました: " + e.getMessage());
                    return;
                }
                Thread.sleep(interval);
                continue;
            }
            String status = str(st, "status");
            if (status.equals("error")) {
                running.remove(playerId, jobId);
                message(playerId, ChatColor.RED + "生成に失敗しました: " + str(st, "error"));
                return;
            }
            if (status.equals("done")) {
                finishJob(playerId, jobId, st);
                return;
            }
            String label = status.equals("queued")
                    ? "順番待ち (" + str(st, "queue_position") + "番目)"
                    : stageLabel(str(st, "stage"));
            String elapsed = status.equals("running") ? " " + str(st, "elapsed") + "秒" : "";
            actionBar(playerId, ChatColor.AQUA + "AI3D: " + ChatColor.WHITE + label + elapsed);
            if (!label.equals(lastLabel)) {
                message(playerId, ChatColor.GRAY + label + " ...");
                lastLabel = label;
            }
            Thread.sleep(interval);
        }
    }

    private static String stageLabel(String stage) {
        switch (stage) {
            case "text→image":
                return "画像を生成中";
            case "image→3D":
                return "3Dモデルを生成中";
            case "voxelize→schem":
                return "ブロックに変換中";
            default:
                return "準備中";
        }
    }

    private static String str(JsonObject o, String key) {
        JsonElement e = o.get(key);
        return e == null || e.isJsonNull() ? "" : e.getAsString();
    }

    private void finishJob(UUID playerId, String jobId, JsonObject st) {
        try {
            String name = str(st, "name") + "_" + jobId;
            Path dir = schematicsDir();
            Files.createDirectories(dir);
            Path file = dir.resolve(name + ".schem");
            client.downloadSchem(jobId, file);
            Clipboard clipboard = readClipboard(file.toFile());
            String elapsed = str(st, "elapsed");
            Bukkit.getScheduler().runTask(this, () -> {
                if (!running.remove(playerId, jobId)) return; // cancelled meanwhile
                Player p = Bukkit.getPlayer(playerId);
                if (p == null) return;
                p.sendMessage(PREFIX + ChatColor.GREEN + "生成完了 (" + elapsed + "秒) → " + name + ".schem");
                p.sendMessage(ChatColor.GRAY + "  サイズ " + dims(st) + "  ブロック数 " + str(st, "block_count")
                        + "  主なブロック: " + topBlocks(st));
                startPending(p, name, clipboard);
            });
        } catch (Exception e) {
            running.remove(playerId, jobId);
            message(playerId, ChatColor.RED + "schemの読み込みに失敗しました: " + e.getMessage());
        }
    }

    private static String dims(JsonObject st) {
        JsonArray s = st.getAsJsonArray("shape");
        if (s == null || s.size() != 3) return "?";
        return s.get(0).getAsInt() + "x" + s.get(1).getAsInt() + "x" + s.get(2).getAsInt();
    }

    private static String topBlocks(JsonObject st) {
        JsonElement e = st.get("top_blocks");
        if (e == null || !e.isJsonObject()) return "";
        return e.getAsJsonObject().keySet().stream().limit(4)
                .map(k -> k.replace("minecraft:", "").replaceAll("\\[.*]", ""))
                .collect(Collectors.joining(", "));
    }

    private void status(Player player) {
        String jobId = running.get(player.getUniqueId());
        PendingPaste pp = pending.get(player.getUniqueId());
        if (jobId == null && pp == null) {
            player.sendMessage(PREFIX + "生成中・確認待ちのものはありません");
            return;
        }
        if (pp != null) {
            player.sendMessage(PREFIX + "確認待ち: " + pp.name);
            sendConfirmButtons(player);
        }
        if (jobId != null) {
            player.sendMessage(PREFIX + "生成中です" + (jobId.isEmpty() ? "" : " (job " + jobId + ")"));
        }
    }

    // ------------------------------------------------------------------ schematics

    private Path schematicsDir() {
        WorldEdit we = WorldEdit.getInstance();
        return we.getWorkingDirectoryPath(we.getConfiguration().saveDir);
    }

    private List<String> listSchematics() {
        try (java.util.stream.Stream<Path> s = Files.list(schematicsDir())) {
            return s.map(p -> p.getFileName().toString())
                    .filter(n -> n.endsWith(".schem") || n.endsWith(".schematic"))
                    .map(n -> n.substring(0, n.lastIndexOf('.')))
                    .sorted().collect(Collectors.toList());
        } catch (IOException e) {
            return new ArrayList<>();
        }
    }

    private static Clipboard readClipboard(File file) throws IOException {
        ClipboardFormat format = ClipboardFormats.findByFile(file);
        if (format == null) {
            throw new IOException("unknown schematic format: " + file.getName());
        }
        try (InputStream in = new FileInputStream(file); ClipboardReader reader = format.getReader(in)) {
            return reader.read();
        }
    }

    private void loadExisting(Player player, String name) {
        if (name.contains("/") || name.contains("\\") || name.contains("..")) {
            player.sendMessage(PREFIX + ChatColor.RED + "不正な名前です");
            return;
        }
        Path dir = schematicsDir();
        Path file = dir.resolve(name + ".schem");
        if (!Files.exists(file)) file = dir.resolve(name + ".schematic");
        if (!Files.exists(file)) file = dir.resolve(name);
        if (!Files.exists(file)) {
            player.sendMessage(PREFIX + ChatColor.RED + "見つかりません: " + name);
            return;
        }
        File f = file.toFile();
        UUID id = player.getUniqueId();
        Bukkit.getScheduler().runTaskAsynchronously(this, () -> {
            try {
                Clipboard clipboard = readClipboard(f);
                Bukkit.getScheduler().runTask(this, () -> {
                    Player p = Bukkit.getPlayer(id);
                    if (p != null) startPending(p, name, clipboard);
                });
            } catch (IOException e) {
                message(id, ChatColor.RED + "読み込みに失敗しました: " + e.getMessage());
            }
        });
    }

    // ------------------------------------------------------------------ preview & paste

    private void startPending(Player player, String name, Clipboard clipboard) {
        long expire = System.currentTimeMillis() + getConfig().getInt("pending-expire-seconds", 600) * 1000L;
        PendingPaste pp = new PendingPaste(name, clipboard, player.getWorld(),
                BukkitAdapter.asBlockVector(player.getLocation()), expire);
        pending.put(player.getUniqueId(), pp);

        // Also put it into the WorldEdit clipboard so //paste, //rotate etc. work too.
        com.sk89q.worldedit.entity.Player wePlayer = BukkitAdapter.adapt(player);
        LocalSession session = WorldEdit.getInstance().getSessionManager().get(wePlayer);
        session.setClipboard(new ClipboardHolder(clipboard));
        showSelection(player, pp);

        player.sendMessage(PREFIX + "貼り付け範囲を表示しています"
                + ChatColor.GRAY + " (WorldEditCUIでは選択範囲として、無い場合はパーティクルで表示)");
        sendConfirmButtons(player);
    }

    /** Select the paste region so WorldEditCUI (and //size etc.) show the bounding box. */
    private void showSelection(Player player, PendingPaste pp) {
        com.sk89q.worldedit.entity.Player wePlayer = BukkitAdapter.adapt(player);
        LocalSession session = WorldEdit.getInstance().getSessionManager().get(wePlayer);
        com.sk89q.worldedit.world.World weWorld = BukkitAdapter.adapt(pp.world);
        CuboidRegionSelector selector = new CuboidRegionSelector(weWorld, pp.min(), pp.max());
        session.setRegionSelector(weWorld, selector);
        session.dispatchCUISelection(wePlayer);
    }

    private void sendConfirmButtons(Player player) {
        BaseComponent[] msg = new ComponentBuilder("  ")
                .append(button("[貼り付け]", ChatColor.GREEN, "/ai3d confirm", "表示中の範囲に貼り付けます (//undo で戻せます)"))
                .append("  ", ComponentBuilder.FormatRetention.NONE)
                .append(button("[ここに移動]", ChatColor.YELLOW, "/ai3d here", "今いる場所を基準に範囲を移動します"))
                .append("  ", ComponentBuilder.FormatRetention.NONE)
                .append(button("[キャンセル]", ChatColor.RED, "/ai3d cancel", "貼り付けをやめます"))
                .create();
        player.spigot().sendMessage(msg);
    }

    private static BaseComponent[] button(String label, ChatColor color, String command, String hover) {
        TextComponent c = new TextComponent(label);
        c.setColor(color);
        c.setBold(true);
        c.setClickEvent(new ClickEvent(ClickEvent.Action.RUN_COMMAND, command));
        c.setHoverEvent(new HoverEvent(HoverEvent.Action.SHOW_TEXT, new Text(hover)));
        return new BaseComponent[]{c};
    }

    private void moveHere(Player player) {
        PendingPaste pp = pending.get(player.getUniqueId());
        if (pp == null) {
            player.sendMessage(PREFIX + "確認待ちのものはありません");
            return;
        }
        pp.world = player.getWorld();
        pp.to = BukkitAdapter.asBlockVector(player.getLocation());
        showSelection(player, pp);
        player.sendMessage(PREFIX + "範囲を移動しました");
        sendConfirmButtons(player);
    }

    private void cancel(Player player) {
        boolean hadJob = running.remove(player.getUniqueId()) != null;
        boolean hadPending = pending.remove(player.getUniqueId()) != null;
        player.sendMessage(PREFIX + (hadJob || hadPending ? "キャンセルしました" : "キャンセルするものはありません"));
    }

    private void confirm(Player player) {
        PendingPaste pp = pending.remove(player.getUniqueId());
        if (pp == null) {
            player.sendMessage(PREFIX + "確認待ちのものはありません");
            return;
        }
        com.sk89q.worldedit.entity.Player wePlayer = BukkitAdapter.adapt(player);
        LocalSession session = WorldEdit.getInstance().getSessionManager().get(wePlayer);
        com.sk89q.worldedit.world.World weWorld = BukkitAdapter.adapt(pp.world);
        boolean ignoreAir = getConfig().getBoolean("paste-ignore-air", true);
        try (EditSession editSession = WorldEdit.getInstance().newEditSession(weWorld)) {
            Operation op = new ClipboardHolder(pp.clipboard)
                    .createPaste(editSession)
                    .to(pp.to)
                    .ignoreAirBlocks(ignoreAir)
                    .build();
            Operations.complete(op);
            session.remember(editSession);
            player.sendMessage(PREFIX + ChatColor.GREEN + "貼り付けました: " + pp.name
                    + ChatColor.GRAY + " (" + editSession.getBlockChangeCount() + "ブロック, //undo で戻せます)");
        } catch (WorldEditException e) {
            player.sendMessage(PREFIX + ChatColor.RED + "貼り付けに失敗しました: " + e.getMessage());
        }
    }

    /** Every 10 ticks: expire old previews and draw the bounding box with particles. */
    private void tickPending() {
        long now = System.currentTimeMillis();
        boolean particles = getConfig().getBoolean("preview-particles", true);
        for (Map.Entry<UUID, PendingPaste> e : pending.entrySet()) {
            PendingPaste pp = e.getValue();
            Player p = Bukkit.getPlayer(e.getKey());
            if (p == null) continue;
            if (now > pp.expiresAt) {
                pending.remove(e.getKey());
                p.sendMessage(PREFIX + "確認待ちの期限が切れたためキャンセルしました");
                continue;
            }
            if (particles && p.getWorld().equals(pp.world)) {
                drawBox(p, pp.min(), pp.max().add(1, 1, 1));
            }
        }
    }

    private static void drawBox(Player p, BlockVector3 a, BlockVector3 b) {
        double x1 = a.getX(), y1 = a.getY(), z1 = a.getZ();
        double x2 = b.getX(), y2 = b.getY(), z2 = b.getZ();
        double perimeter = 4 * ((x2 - x1) + (y2 - y1) + (z2 - z1));
        double step = Math.max(0.5, perimeter / 400.0);
        double[][] corners = {{x1, y1, z1}, {x2, y1, z1}, {x1, y2, z1}, {x1, y1, z2},
                {x2, y2, z1}, {x2, y1, z2}, {x1, y2, z2}, {x2, y2, z2}};
        int[][] edges = {{0, 1}, {0, 2}, {0, 3}, {1, 4}, {1, 5}, {2, 4}, {2, 6}, {3, 5}, {3, 6}, {4, 7}, {5, 7}, {6, 7}};
        for (int[] edge : edges) {
            double[] s = corners[edge[0]], t = corners[edge[1]];
            double len = Math.abs(t[0] - s[0]) + Math.abs(t[1] - s[1]) + Math.abs(t[2] - s[2]);
            for (double d = 0; d <= len; d += step) {
                double f = len == 0 ? 0 : d / len;
                p.spawnParticle(Particle.END_ROD, s[0] + (t[0] - s[0]) * f, s[1] + (t[1] - s[1]) * f,
                        s[2] + (t[2] - s[2]) * f, 1, 0, 0, 0, 0);
            }
        }
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        pending.remove(event.getPlayer().getUniqueId());
    }

    // ------------------------------------------------------------------ messaging helpers

    private void message(UUID playerId, String text) {
        Bukkit.getScheduler().runTask(this, () -> {
            Player p = Bukkit.getPlayer(playerId);
            if (p != null) p.sendMessage(PREFIX + text);
        });
    }

    private void actionBar(UUID playerId, String text) {
        Bukkit.getScheduler().runTask(this, () -> {
            Player p = Bukkit.getPlayer(playerId);
            if (p != null) p.spigot().sendMessage(ChatMessageType.ACTION_BAR, TextComponent.fromLegacyText(text));
        });
    }
}
