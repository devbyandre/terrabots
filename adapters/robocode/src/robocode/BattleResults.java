package robocode;

/** Battle results for onBattleEnded (not sent by Terrabots, which scores battles itself). */
public class BattleResults implements java.io.Serializable {
    public String getTeamLeaderName() { return ""; }
    public int getRank() { return 0; }
    public double getScore() { return 0; }
    public int getFirsts() { return 0; }
}
