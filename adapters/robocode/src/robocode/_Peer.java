package robocode;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.TimeUnit;

import robocode.robotinterfaces.*;
import robocode.util.Utils;

/**
 * Internal (not Robocode API): one bot's state for a battle, and the hand-over
 * between the engine (host thread) and the bot's own thread.
 *
 * Robocode bots run their own loop in run() and block in execute() until the
 * next turn. Each engine turn, the host hands the observation to the bot
 * thread (applyObs + event dispatch happen there, as in Robocode), and the bot
 * thread hands back its queued commands when it reaches the next execute().
 * Units: the engine works in cells, Robocode in pixels (16 px per cell).
 *
 * One peer for the whole battle, as in Robocode: each round gets a new robot
 * object, but objects from earlier rounds still control the robot (strong bots
 * keep helpers built in round 1 that hold the round-1 robot). newRound() resets
 * everything that belongs to a round.
 */
public final class _Peer {
    public static final double PX = 16.0;
    public static final Object DEATH_SIGNAL = new Object();

    public static final class End {
        final boolean won;
        public End(boolean won) { this.won = won; }
    }

    /** Abandons an interruptible handler when a new event of its priority arrives, so
     *  it can start again from the top (Robocode's setInterruptible / scan()). */
    static final class Interrupted extends Error {
        final int priority;
        Interrupted(int priority) { super(null, null, false, false); this.priority = priority; }
    }

    /** Unwinds the bot thread at the end of its round (Robocode does the same). */
    static final class RoundOver extends Error {
        RoundOver() { super(null, null, false, false); }
    }

    // Identity, set by the host
    public String name = "bot";
    public int botId;
    public String team;
    public Map<Integer, String> teammates = new HashMap<>();
    public int roundNum, numRounds = 1;
    public long quotaBytes = 200 * 1024;

    // Status, in Robocode units (px, degrees)
    double x, y, heading, gunHeading, radarHeading, velocity, energy = 100, gunHeat, coolingRate = 0.1;
    double fieldW = 768, fieldH = 768;
    long time;
    int others, skipped;
    boolean hasStatus;

    // Queued commands
    boolean scanRequested;
    // Remaining turns are in radians, as in Robocode: its float arithmetic decides
    // on which tick a turn ends, and bots notice a tick's difference.
    double distance, bodyTurn, gunTurn, radarTurn, fire, maxVelocity = Rules.MAX_VELOCITY, maxTurnRate = Rules.MAX_TURN_RATE;
    boolean adjGun, adjRadar, adjRadarRobot, adjRadarRobotSet;
    Double velocityRate, turnRate, gunRate, radarRate;   // RateControlRobot
    double[] stopped;                                   // stop() / resume()

    // Events and conditions
    final List<Event> pending = new ArrayList<>();
    final List<Condition> conditions = new ArrayList<>();
    final Map<String, Integer> priorities = new HashMap<>();
    int currentPriority = Integer.MIN_VALUE;
    Event currentEvent;                                 // the handler running now
    Double fireHeading;                                 // fire assistance (plain Robot)
    boolean interruptible;

    // Bullets and the other bots we know
    final List<Bullet> unconfirmed = new ArrayList<>();
    final Map<Integer, Bullet> bullets = new HashMap<>();
    final Map<Integer, String> names = new HashMap<>();
    final Map<Integer, Double> energies = new HashMap<>();
    final List<Object> outbox = new ArrayList<>();

    // Hand-over
    SynchronousQueue<Object> toBot = new SynchronousQueue<>();
    SynchronousQueue<Map<String, Object>> toHost = new SynchronousQueue<>();
    Object robot;                         // the bot object of this round (any IBasicRobot)
    IBasicEvents basic;
    IAdvancedEvents advanced;
    ITeamEvents teamEvents;
    Runnable runnable;
    java.io.PrintStream out = System.err;
    final _PeerAdapter adapter = new _PeerAdapter(this);
    Thread thread;
    public boolean started;
    volatile boolean broken;

    /** Connect a bot object, as Robocode does: setOut, setPeer, then its listeners. */
    public void attach(IBasicRobot r) {
        robot = r;
        r.setOut(out);
        r.setPeer(adapter);
        runnable = r.getRobotRunnable();
        basic = r.getBasicEventListener();
        advanced = r instanceof IAdvancedRobot ? ((IAdvancedRobot) r).getAdvancedEventListener() : null;
        teamEvents = r instanceof ITeamRobot ? ((ITeamRobot) r).getTeamEventListener() : null;
    }

    /** A new round: fresh round state, the new robot object, a new hand-over. */
    public void newRound(IBasicRobot r, int round) {
        roundNum = round;
        hasStatus = false;
        time = 0;
        skipped = 0;
        energy = 100;
        gunHeat = 0;
        velocity = 0;
        distance = bodyTurn = gunTurn = radarTurn = fire = 0;
        maxVelocity = Rules.MAX_VELOCITY;
        maxTurnRate = Rules.MAX_TURN_RATE;
        adjGun = adjRadar = adjRadarRobot = adjRadarRobotSet = false;
        velocityRate = turnRate = gunRate = radarRate = null;
        stopped = null;
        pending.clear();
        conditions.clear();
        currentPriority = Integer.MIN_VALUE;
        currentEvent = null;
        fireHeading = null;
        interruptible = false;
        unconfirmed.clear();
        bullets.clear();
        energies.clear();
        outbox.clear();
        toBot = new SynchronousQueue<>();
        toHost = new SynchronousQueue<>();
        thread = null;
        started = false;
        broken = false;
        attach(r);
    }

    // ------------------------------------------------------------------
    // Host side
    // ------------------------------------------------------------------

    /** First turn: status from the observation, then start the bot's thread. */
    public void start(Map<String, Object> obs) {
        applyObs(obs);
        started = true;
        thread = new Thread(this::botMain, "robot");
        thread.setDaemon(true);
        thread.start();
    }

    public void nextTurn(Map<String, Object> obs) throws InterruptedException {
        while (thread.isAlive()) {
            if (toBot.offer(obs, 50, TimeUnit.MILLISECONDS)) return;
        }
    }

    /** The commands of this turn, or null if the bot thread has ended. */
    public Map<String, Object> awaitCommands() throws InterruptedException {
        while (thread.isAlive()) {
            Map<String, Object> c = toHost.poll(50, TimeUnit.MILLISECONDS);
            if (c != null) return c;
        }
        return null;
    }

    public void signal(Object s, long waitMs) throws InterruptedException {
        if (thread == null || !thread.isAlive()) return;
        toBot.offer(s, waitMs, TimeUnit.MILLISECONDS);
        if (s instanceof End) thread.join(waitMs);
    }

    public List<Object> takeOutbox() {
        List<Object> out = new ArrayList<>(outbox);
        outbox.clear();
        return out;
    }

    /** An AdvancedRobot (Robocode charges only these for hitting a wall). */
    public boolean isAdvanced() { return advanced != null; }

    /** Always false: commands() does the adjusting and sends turns the engine carries along. */
    public boolean adjustGun() { return false; }

    public boolean adjustRadar() { return false; }

    // ------------------------------------------------------------------
    // Bot thread
    // ------------------------------------------------------------------

    private void botMain() {
        try {
            // As in Robocode: before run() only the round's first status (time 0; some
            // bots set up in onStatus at time 0); other events come at the first execute().
            dispatchStatusOnly();
            runnable.run();
            while (true) execute();
        } catch (RoundOver over) {
            // round finished
        } catch (Throwable t) {
            out.println("Robot stopped: " + t);
            t.printStackTrace(out);
            broken = true;
            idle();
        }
    }

    /** A crashed bot stays in the round doing nothing, as in Robocode. */
    private void idle() {
        try {
            while (true) {
                distance = bodyTurn = gunTurn = radarTurn = fire = 0;
                toHost.put(commands());
                Object t = toBot.take();
                if (t == DEATH_SIGNAL || t instanceof End) return;
            }
        } catch (InterruptedException ignored) {
        }
    }

    void execute() {
        if (thread == null) return;     // before the round started (e.g. from a constructor)
        Object t;
        try {
            toHost.put(commands());
            fire = 0;
            fireHeading = null;
            t = toBot.take();
        } catch (InterruptedException e) {
            throw new RoundOver();
        }
        // A death or round end happens during the next turn; Robocode stamps it with that turn.
        if (t == DEATH_SIGNAL || t instanceof End) time++;
        if (t == DEATH_SIGNAL) {
            deliver(new DeathEvent());
            awaitEnd();
        }
        if (t instanceof End) {
            finish((End) t);
        }
        @SuppressWarnings("unchecked") Map<String, Object> obs = (Map<String, Object>) t;
        applyObs(obs);
        dispatch();
    }

    private void awaitEnd() {
        try {
            while (true) {
                Object t = toBot.take();
                if (t instanceof End) finish((End) t);
            }
        } catch (InterruptedException e) {
            throw new RoundOver();
        }
    }

    private void finish(End end) {
        if (end.won) deliver(new WinEvent());
        deliver(new RoundEndedEvent(roundNum, (int) time, (int) time));
        throw new RoundOver();
    }

    private void deliver(Event e) {
        e.setTime(time);
        try {
            e.dispatch(this);
        } catch (RoundOver over) {
            throw over;
        } catch (Throwable t) {
            t.printStackTrace(out);
        }
    }

    // ------------------------------------------------------------------
    // Engine observation -> status, remaining amounts, events
    // ------------------------------------------------------------------

    private static double num(Map<String, Object> m, String k) {
        Object v = m.get(k);
        return v instanceof Number ? ((Number) v).doubleValue() : 0.0;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> list(Map<String, Object> m, String k) {
        Object v = m.get(k);
        return v instanceof List ? (List<Map<String, Object>>) v : new ArrayList<>();
    }

    private double rel(double absolute) {
        return Utils.normalRelativeAngleDegrees(absolute - heading);
    }

    private String nameOf(int id) {
        String n = names.get(id);
        return n != null ? n : teammates.getOrDefault(id, "bot" + id);
    }

    void applyObs(Map<String, Object> obs) {
        double h0 = heading, g0 = gunHeading, r0 = radarHeading;
        x = num(obs, "x") * PX;
        y = num(obs, "y") * PX;
        heading = num(obs, "heading");
        gunHeading = num(obs, "gun_heading");
        radarHeading = num(obs, "radar_heading");
        velocity = num(obs, "velocity") * PX;
        energy = num(obs, "energy");
        gunHeat = num(obs, "gun_heat");
        time = (long) num(obs, "tick") - 1;     // Robocode counts turns from 0, the engine ticks from 1
        others = (int) num(obs, "others");
        fieldW = num(obs, "arena_width") * PX;
        fieldH = num(obs, "arena_height") * PX;
        boolean hasPrev = hasStatus;
        if (hasStatus) updateRemaining(h0, g0, r0);
        hasStatus = true;

        pending.removeIf(e -> e.getTime() < time - 1);
        for (Map<String, Object> s : list(obs, "scanned_bots")) {
            int id = (int) num(s, "bot_id");
            String n = (String) s.get("name");
            names.put(id, n);
            energies.put(id, num(s, "energy"));
            add(new ScannedRobotEvent(n, num(s, "energy"), rel(num(s, "bearing")), num(s, "distance") * PX,
                    num(s, "heading"), num(s, "velocity") * PX, false));
        }
        for (Map<String, Object> f : list(obs, "bullet_fired")) {
            if (!unconfirmed.isEmpty()) {
                Bullet b = unconfirmed.remove(0);
                bullets.put((int) num(f, "bullet_id"), b);
            }
        }
        unconfirmed.removeIf(b -> b.firedAt < time - 1);
        for (Map<String, Object> e : list(obs, "bullet_hit_bullet")) {
            Bullet mine = resolve((int) num(e, "bullet_id"), null, e);
            Bullet other = new Bullet(num(e, "other_heading"), num(e, "other_x") * PX, num(e, "other_y") * PX,
                    num(e, "other_power"), nameOf((int) num(e, "other_shooter_id")), null, false, -1);
            add(new BulletHitBulletEvent(mine, other));
        }
        for (Map<String, Object> e : list(obs, "bullet_hit")) {
            int target = (int) num(e, "target_id");
            energies.put(target, num(e, "target_energy"));
            add(new BulletHitEvent(nameOf(target), num(e, "target_energy"), resolve((int) num(e, "bullet_id"), nameOf(target), e)));
        }
        for (Map<String, Object> e : list(obs, "bullet_missed")) {
            add(new BulletMissedEvent(resolve((int) num(e, "bullet_id"), null, e)));
        }
        for (Map<String, Object> e : list(obs, "hit_by_bullet")) {
            double power = num(e, "power");
            double from = num(e, "bearing");
            Bullet b = new Bullet(Utils.normalAbsoluteAngleDegrees(from + 180), num(e, "x") * PX, num(e, "y") * PX,
                    power, nameOf((int) num(e, "shooter_id")), name, false, -1);
            // Bullets hit before robots turn: the bearing is from the heading before this turn's turn.
            add(new HitByBulletEvent(Utils.normalRelativeAngleDegrees(from - (hasPrev ? h0 : heading)), b));
        }
        for (Map<String, Object> e : list(obs, "hit_bot")) {
            int id = (int) num(e, "bot_id");
            boolean fault = Boolean.TRUE.equals(e.get("my_fault"));
            if (fault) distance = 0;
            add(new HitRobotEvent(nameOf(id), rel(num(e, "bearing")), energies.getOrDefault(id, 0.0), fault));
        }
        if (!list(obs, "hit_wall").isEmpty()) {
            distance = 0;
            add(new HitWallEvent(rel(num(list(obs, "hit_wall").get(0), "bearing"))));
        }
        for (Map<String, Object> e : list(obs, "bot_death")) {
            add(new RobotDeathEvent((String) e.get("name")));
        }
        for (Map<String, Object> m : list(obs, "team_messages")) {
            add(new MessageEvent((String) m.get("sender_name"), decode(m.get("data"))));
        }
        int sk = (int) num(obs, "skipped_turns");
        if (sk > skipped) add(new SkippedTurnEvent(time));
        skipped = sk;
        add(new StatusEvent(status()));
    }

    private void add(Event e) {
        e.setTime(time);
        pending.add(e);
    }

    private Bullet resolve(int id, String victim, Map<String, Object> where) {
        Bullet b = bullets.remove(id);
        if (b == null) b = new Bullet(0, x, y, 0, name, victim, false, -1);
        b.active = false;
        b.victim = victim;
        b.x = num(where, "x") * PX;
        b.y = num(where, "y") * PX;
        return b;
    }

    private void updateRemaining(double h0, double g0, double r0) {
        // Turns were already counted down in commands(), exactly as Robocode does.
        distance = consume(distance, velocity);
    }

    private static double consume(double remaining, double done) {
        if (remaining == 0) return 0;
        if (Double.isInfinite(remaining)) return remaining;
        double left = remaining - done;
        if (Math.abs(left) < 1e-6 || (left > 0) != (remaining > 0)) return 0;
        return left;
    }

    RobotStatus status() {
        return new RobotStatus(x, y, currentEnergy(), heading, gunHeading, radarHeading, velocity, currentGunHeat(),
                distance, bodyTurn, gunTurn, radarTurn, others, roundNum, numRounds, time);
    }

    // ------------------------------------------------------------------
    // Events: Robocode's order (higher priority first; a handler is only
    // interrupted by higher-priority events unless it set interruptible)
    // ------------------------------------------------------------------

    int priorityOf(Event e) {
        Integer p = priorities.get(e.getClass().getSimpleName());
        return p != null ? p : e.getPriority();
    }

    void dispatch() {
        for (Condition c : new ArrayList<>(conditions)) {
            boolean hit;
            try {
                hit = c.test();
            } catch (RoundOver over) {
                throw over;
            } catch (Throwable t) {
                hit = false;
            }
            if (hit) add(new CustomEvent(c));
        }
        while (true) {
            Event next = null;
            int best = Integer.MIN_VALUE;
            for (Event e : pending) {
                int p = priorityOf(e);
                boolean allowed = p > currentPriority || (interruptible && p == currentPriority);
                if (allowed && (next == null || p > best)) {
                    next = e;
                    best = p;
                }
            }
            if (next == null) return;
            if (best == currentPriority) {
                // Same priority as the handler we're inside: it set interruptible, so
                // abandon it; the frame that called it dispatches this event next.
                throw new Interrupted(best);
            }
            pending.remove(next);
            int outer = currentPriority;
            Event outerEvent = currentEvent;
            boolean outerInterruptible = interruptible;
            currentPriority = best;
            currentEvent = next;
            interruptible = false;
            try {
                next.dispatch(this);
            } catch (Interrupted in) {
                if (in.priority != best) throw in;
            } catch (RoundOver over) {
                throw over;
            } catch (Throwable t) {
                t.printStackTrace(out);
            } finally {
                currentPriority = outer;
                currentEvent = outerEvent;
                interruptible = outerInterruptible;
            }
        }
    }

    private void dispatchStatusOnly() {
        for (Event e : new ArrayList<>(pending)) {
            if (e instanceof StatusEvent) {
                pending.remove(e);
                deliver(e);
            }
        }
    }

    /** Robocode's scan()/rescan(): a turn in which a running onScannedRobot may be restarted. */
    void rescan() {
        boolean was = interruptible;
        Integer p = priorities.get("ScannedRobotEvent");
        if (currentPriority == (p != null ? p : 10)) interruptible = true;
        scanRequested = true;     // scan even if nothing moves this turn
        execute();
        interruptible = was;
    }

    List<Event> allEvents() {
        return new ArrayList<>(pending);
    }

    // ------------------------------------------------------------------
    // Commands -> engine action
    // ------------------------------------------------------------------

    Map<String, Object> commands() {
        double v;
        if (velocityRate != null) {
            v = velocityRate;
        } else {
            double rem = Math.abs(distance);
            v = rem < 1e-6 ? 0 : Math.copySign(Math.min(Math.min(Rules.MAX_VELOCITY, maxVelocity), stoppable(rem)), distance);
        }
        // RateControlRobot sets the remaining turns to its rates before every execute().
        if (turnRate != null) bodyTurn = Math.toRadians(turnRate);
        if (gunRate != null) gunTurn = Math.toRadians(gunRate);
        if (radarRate != null) radarTurn = Math.toRadians(radarRate);

        // Robocode's RobotPeer.updateHeading/GunHeading/RadarHeading: the gun always
        // turns with the body and the radar with the gun; "adjust" takes the carried
        // turn off the remaining turn instead.
        double rate = Math.min(Math.toRadians(maxTurnRate),
                (0.4 + 0.6 * (1 - Math.abs(velocity) / Rules.MAX_VELOCITY)) * Rules.MAX_TURN_RATE_RADIANS);
        double body = step(bodyTurn, rate);
        bodyTurn = left(bodyTurn, body, rate);
        if (adjGun) gunTurn -= body;
        if (adjRadarRobot) radarTurn -= body;
        double gun = step(gunTurn, Rules.GUN_TURN_RATE_RADIANS);
        gunTurn = left(gunTurn, gun, Rules.GUN_TURN_RATE_RADIANS);
        if (adjRadar) radarTurn -= gun;
        double radar = step(radarTurn, Rules.RADAR_TURN_RATE_RADIANS);
        radarTurn = left(radarTurn, radar, Rules.RADAR_TURN_RATE_RADIANS);

        Map<String, Object> a = new LinkedHashMap<>();
        a.put("velocity", v / PX);
        a.put("body_turn", Math.toDegrees(body));
        a.put("gun_turn", Math.toDegrees(gun));
        a.put("radar_turn", Math.toDegrees(radar));
        a.put("fire", fire);
        a.put("fire_heading", fireHeading);
        a.put("shout", null);
        a.put("scan", scanRequested);
        scanRequested = false;
        return a;
    }

    /** This tick's turn: all that is left if it is less than the rate, else the rate. */
    private static double step(double remaining, double rate) {
        if (Double.isNaN(remaining) || remaining == 0) return 0;
        return Math.abs(remaining) < rate ? remaining : Math.copySign(rate, remaining);
    }

    private static double left(double remaining, double turned, double rate) {
        return Double.isNaN(remaining) || Math.abs(remaining) < rate ? 0 : remaining - turned;
    }

    /** Fastest speed now that still stops within `remaining`, braking 2 px/tick afterwards. */
    private static double stoppable(double remaining) {
        if (Double.isInfinite(remaining)) return Rules.MAX_VELOCITY;
        double lo = 0, hi = Math.min(remaining, Rules.MAX_VELOCITY);
        for (int k = 0; k < 40; k++) {
            double mid = (lo + hi) / 2;
            int n = (int) (mid / Rules.DECELERATION);
            double travel = (n + 1) * mid - Rules.DECELERATION * n * (n + 1) / 2.0;
            if (travel <= remaining) lo = mid; else hi = mid;
        }
        return lo;
    }

    /** As in Robocode, a shot queued this turn already shows in energy and gun heat. */
    double currentEnergy() { return energy - fire; }

    double currentGunHeat() { return fire > 0 ? gunHeat + Rules.getGunHeat(fire) : gunHeat; }

    Bullet queueFire(double power) {
        if (currentGunHeat() > 0 || power <= 0 || currentEnergy() <= 0) return null;
        power = Math.min(Math.max(power, Rules.MIN_BULLET_POWER), Math.min(Rules.MAX_BULLET_POWER, energy));
        fire = power;
        // Robocode's fire assistance (BasicRobotProxy.setFireImpl): a plain Robot that
        // fires from this turn's onScannedRobot with gun and radar aligned shoots
        // straight at the scanned robot, whatever the gun's exact heading.
        fireHeading = null;
        if (!isAdvanced() && currentEvent instanceof ScannedRobotEvent && currentEvent.getTime() == time
                && gunHeading == radarHeading) {
            fireHeading = Utils.normalAbsoluteAngleDegrees(heading + ((ScannedRobotEvent) currentEvent).getBearing());
        }
        Bullet b = new Bullet(fireHeading != null ? fireHeading : gunHeading, x, y, power, name, null, true, time);
        unconfirmed.add(b);
        return b;
    }

    // ------------------------------------------------------------------
    // Team messages: Java objects travel serialized, as base64 in JSON
    // ------------------------------------------------------------------

    void queueMessage(Integer to, Serializable message) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
                out.writeObject(message);
            }
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("java", Base64.getEncoder().encodeToString(bytes.toByteArray()));
            List<Object> entry = new ArrayList<>();
            entry.add(to);
            entry.add(data);
            outbox.add(entry);
        } catch (Exception e) {
            out.println("message not sent: " + e);
        }
    }

    @SuppressWarnings("unchecked")
    private static Serializable decode(Object data) {
        if (data instanceof Map && ((Map<String, Object>) data).get("java") instanceof String) {
            try (ObjectInputStream in = new ObjectInputStream(new ByteArrayInputStream(
                    Base64.getDecoder().decode((String) ((Map<String, Object>) data).get("java"))))) {
                return (Serializable) in.readObject();
            } catch (Exception e) {
                return null;
            }
        }
        return data instanceof Serializable ? (Serializable) data : String.valueOf(data);
    }
}
