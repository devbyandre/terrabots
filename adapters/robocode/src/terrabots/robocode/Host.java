package terrabots.robocode;

import java.io.BufferedReader;
import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import robocode.Droid;
import robocode.Robot;
import robocode._Peer;
import robocode.util.Utils;

/**
 * Runs one Robocode bot (a class from its jar) for the Terrabots engine:
 *
 *     java -cp adapter.jar:bot.jar terrabots.robocode.Host
 *
 * Speaks the sandbox protocol (terrabots/battle/sandbox_child.py) on stdin and
 * stdout: start, round, decide, death, round_end, stop. Everything the bot
 * prints goes to stderr.
 */
public final class Host {
    private static PrintStream replies;

    private static void send(Map<String, Object> msg) {
        replies.println(Json.write(msg));
        replies.flush();
    }

    private static Map<String, Object> msg(String type) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("t", type);
        return m;
    }

    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        System.setProperty("java.awt.headless", "true");
        replies = new PrintStream(new FileOutputStream(FileDescriptor.out), false, "UTF-8");
        System.setOut(System.err);
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));

        Map<String, Object> start = (Map<String, Object>) Json.parse(in.readLine());
        String className = ((String) start.get("spec")).replaceFirst("^robocode:", "");
        if (start.get("seed") instanceof Number) Utils.setSeed(((Number) start.get("seed")).longValue());
        long quota = (long) (Json.num(start, "quota_kb") * 1024);
        Class<?> cls;
        try {
            cls = Class.forName(className);
            if (!Robot.class.isAssignableFrom(cls)) {
                throw new IllegalArgumentException(className + " doesn't extend robocode.Robot "
                        + "(bots built on robocode.robotinterfaces aren't supported)");
            }
        } catch (Throwable t) {
            Map<String, Object> err = msg("error");
            err.put("msg", t.toString());
            send(err);
            return;
        }
        Map<String, Object> ready = msg("ready");
        ready.put("class", cls.getSimpleName());
        ready.put("droid", Droid.class.isAssignableFrom(cls));
        send(ready);

        _Peer peer = null;
        String line;
        while ((line = in.readLine()) != null) {
            Map<String, Object> m = (Map<String, Object>) Json.parse(line);
            String kind = (String) m.get("t");
            switch (kind) {
                case "round": {
                    peer = new _Peer();
                    peer.botId = (int) Json.num(m, "bot_id");
                    peer.name = (String) m.get("name");
                    peer.team = (String) m.get("team");
                    peer.roundNum = (int) Json.num(m, "round") - 1;
                    peer.numRounds = (int) Json.num(m, "rounds");
                    peer.quotaBytes = quota;
                    Map<Integer, String> mates = new HashMap<>();
                    Object raw = m.get("teammates");
                    if (raw instanceof Map) {
                        for (Map.Entry<String, Object> e : ((Map<String, Object>) raw).entrySet()) {
                            mates.put(Integer.parseInt(e.getKey()), (String) e.getValue());
                        }
                    }
                    peer.teammates = mates;
                    Map<String, Object> ok = msg("ok");
                    try {
                        Robot r = (Robot) cls.getDeclaredConstructor().newInstance();
                        peer.attach(r);
                    } catch (Throwable t) {
                        Map<String, Object> err = msg("error");
                        err.put("msg", "can't create " + className + ": " + t);
                        send(err);
                        break;
                    }
                    ok.put("adj_gun", false);
                    ok.put("adj_radar", false);
                    ok.put("colors", new HashMap<String, Object>());
                    send(ok);
                    break;
                }
                case "decide": {
                    long t0 = System.nanoTime();
                    Map<String, Object> obs = (Map<String, Object>) m.get("obs");
                    if (!peer.started) peer.start(obs);
                    else peer.nextTurn(obs);
                    Map<String, Object> action = peer.awaitCommands();
                    if (action == null) {          // the bot's thread is gone: stand still
                        action = new LinkedHashMap<>();
                        for (String k : new String[] {"velocity", "body_turn", "gun_turn", "radar_turn", "fire"}) action.put(k, 0);
                        action.put("shout", null);
                    }
                    Map<String, Object> reply = msg("action");
                    reply.put("seq", m.get("seq"));
                    reply.put("elapsed_ms", (System.nanoTime() - t0) / 1e6);
                    reply.put("console", List.of());
                    reply.put("action", action);
                    reply.put("shapes", List.of());
                    reply.put("adj_gun", peer.adjustGun());
                    reply.put("adj_radar", peer.adjustRadar());
                    reply.put("outbox", peer.takeOutbox());
                    send(reply);
                    break;
                }
                case "death":
                    if (peer != null) peer.signal(_Peer.DEATH_SIGNAL, 1000);
                    break;
                case "round_end":
                    if (peer != null) peer.signal(new _Peer.End(Boolean.TRUE.equals(m.get("won"))), 1000);
                    break;
                case "stop":
                    System.exit(0);
                    break;
                default:
                    break;
            }
        }
        System.exit(0);
    }
}
