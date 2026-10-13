# Survival guide: from reflexes to evolution

Survival mode is a small artificial ecosystem: creatures on a hilly 2.5D world
must find food before their energy runs out. There is no shooting; the only
enemy is starvation, and the other creatures, who eat the same food.

The guide goes up in levels. Each level introduces one idea from research on
animal behaviour, ecology or artificial intelligence, shows how it maps onto the
Terrabots API, and ends with an exercise you can measure. The example agents
live in [`terrabots/agents/`](../terrabots/agents/) and [`bots/`](../bots/).

---

## 0. The rules

| What | Default |
|---|---|
| Start energy | 100 |
| Metabolism | −1 energy every tick, moving or not |
| Moving one cell (8 directions) | −1, plus 2 per unit of height climbed, plus the water depth when wading |
| Climb limit | a step up of more than 2 height units is impossible; rock is impassable |
| Eating | standing on a food cell: +20 per tick (at most what the cell holds), −2 for eating |
| Food | cells start with 15–50, regrow 0.5 per tick up to 50; about one new food cell every 3 ticks |
| Crowding | one creature per cell |
| Death | energy at 0 or below |
| Perception | creatures, food and terrain within 15 cells **and line of sight** (hills hide things) |
| Messages | to one creature per tick, within 25 cells and line of sight, read next tick |

All of these are in `SimConfig` / `ResourceConfig` and in the viewer's Survival
tab. **The arithmetic that matters:** a creature that walks burns 2 per tick, one
that stands burns 1, and a meal gives +18 per tick. Wandering is expensive;
knowing where food is, is worth a lot.

Run survival mode in the browser (`terrabots-battle`, Survival tab) or headless:

```bash
terrabots-run --headless --ticks 600 --seed 1 \
    --agent bots.wanderer:WandererAgent=4 --agent terrabots.agents.grazer:Grazer=4
```

**How to compare agents:** put them in the same world and count survivors and
average lifetime (ticks alive) over many seeds. One world proves nothing. The
table below comes from 16 worlds (48 × 48, procedural terrain, 600 ticks), four
of each agent per world:

| Agent | Level | Survivors (of 64) | Average lifetime |
|---|---|---|---|
| `WandererAgent` | 1 | 3 | 177 ticks |
| `Grazer` | 2 | **7** | **221 ticks** |
| `LevyForager` | 3 | 4 | 206 ticks |
| `Sharer` | 5 | 2 | 164 ticks |

Sharing coming last isn't a mistake; level 5 explains why.

---

## Level 1: reactive agents

**Idea.** Very simple sensor-to-motor rules can look surprisingly purposeful.
Braitenberg (1984) built "vehicles" whose wheels were wired straight to light
sensors; depending on the wiring they seem to fear, love or explore the light.
No memory, no plan.

**In Terrabots.** `bots/wanderer.py`: if food is in sight, walk to the nearest;
otherwise step randomly. `decide()` looks only at the current `Observation`.

**Exercise.** Change Wanderer to walk to the *biggest* food in sight instead of
the nearest. Better or worse? Then try "biggest per distance".

## Level 2: when to leave a patch

**Idea.** Optimal foraging theory asks which choices maximise the energy an
animal gains per unit of time (MacArthur & Pianka 1966; Stephens & Krebs 1986).
The *Marginal Value Theorem* (Charnov 1976) answers a classic question: a forager
eating from a patch that is getting emptier should leave when its intake rate
drops to the average rate it could get elsewhere, travel included.

**In Terrabots.** A cell gives `min(20, amount) − 2` per tick. Below 3 left, eating
costs more than it gives, so leave. `Grazer` stays until then and picks the
food with the best amount-per-distance; it lives longest in the table above.

**Exercise.** Make the leaving threshold depend on what you can see: if rich
food is close, leave earlier. Estimate the average intake rate from your last
100 ticks and leave when the current cell drops below it (Charnov's rule).

## Level 3: searching

**Idea.** When no food is in sight, how should you search? A plain random walk
keeps revisiting the same area. *Lévy flights* (straight runs whose lengths follow
a power law: mostly short, now and then very long) are more efficient when food
is sparse and patchy (Viswanathan et al. 1999). Searching near the last find
first ("area-restricted search") pays off when food comes in clumps.

**In Terrabots.** `LevyForager` searches with run lengths drawn from
P(l) ∝ l^−2. Two Terrabots twists: climbing costs energy, so the cheapest path to
food is often around a hill, not over it (shortest path search, e.g. A*,
Hart, Nilsson & Raphael 1968, with step cost = the move cost); and hills hide
food, so high ground gives a better view.

**Exercise.** Give LevyForager a memory of where it found food and return there
when it's been a while (food regrows). Then make its runs avoid steep climbs.
Measure both changes separately.

## Level 4: competition

**Idea.** Animals spread over patches so that each gets about the same intake:
the *ideal free distribution* (Fretwell & Lucas 1969). Crowding a patch lowers
everyone's share. And a shared resource that regrows can be eaten faster than it
recovers, the *tragedy of the commons* (Hardin 1968).

**In Terrabots.** Other creatures are visible (`obs.visible_agents`) and block
cells. Ideas: avoid food that others are closer to; prefer food nobody else is
heading for; repel from crowds, attract to food (a potential field, the same
anti-gravity idea that battle bots use).

**Exercise.** Count, per tick, how many creatures are within 5 cells of each food
cell you see, and pick food by amount / (distance × (1 + competitors)). Does the
whole population live longer if *everyone* uses your rule?

## Level 5: communication and cooperation

**Idea.** Animals that share information find patchy food faster (social
foraging), and simple local rules give rise to group behaviour: Reynolds' *boids*
(1987) flock with just separation, alignment and cohesion; ants coordinate
through trails they leave behind (stigmergy; Bonabeau, Dorigo & Theraulaz 1999).
But information is a public good: whoever finds food and tells others gains
little, whoever listens gains a lot. This is the *producer–scrounger* game
(Barnard & Sibly 1981).

**In Terrabots.** `Shout` sends a small message to one creature you can see;
it arrives next tick (`obs.inbox`, `on_message`). `Sharer` tells others about rich
food and follows tips it receives. In the table above it does *worst*: its tips
send other Sharers to the same patch, they compete there, and creatures of other
kinds never share back. That's the producer–scrounger trade-off, measured.

**Exercise.** Make sharing pay: share only with your own kind (tag your messages
and only answer tagged ones), share only food too big for one creature to finish,
or share where food *was* (regrowth) instead of where it is. Which works?

## Level 6: learning

**Idea.** *Reinforcement learning* (Sutton & Barto 2018): an agent tries actions,
receives rewards and learns which actions pay off in which state, e.g. with
Q-learning (Watkins & Dayan 1992). In survival mode the reward is obvious:
energy gained, or ticks survived.

**In Terrabots.** `Observation.to_dict()` gives a flat feature dictionary (energy,
position, nearest food, number of visible creatures...). A first experiment: a
tabular Q-learner whose state is a few coarse buckets (energy low/high, food in
sight yes/no, crowded yes/no), whose actions are "go to food", "stay", "Lévy
step", and whose reward is the energy change per tick. Run many seeded worlds
headless (`Simulation` from Python) to train it. A full Gymnasium/PettingZoo
wrapper is on the roadmap.

**Exercise.** Train the Q-learner for 200 worlds, then compare it with Grazer on
50 new seeds. Does it rediscover Charnov's rule?

## Level 7: evolution

**Idea.** Instead of designing behaviour, let it evolve: *genetic algorithms*
(Holland 1975) keep the fitter individuals of a population and recombine and
mutate their parameters; *neuroevolution* evolves neural networks, even their
structure (NEAT, Stanley & Miikkulainen 2002). When creatures compete, the best
strategy depends on what everyone else does: *evolutionary game theory*
(Maynard Smith & Price 1973) studies which mixes of strategies are stable.

**In Terrabots.** Give an agent a few numbers (leave threshold, food-vs-crowd
weight, run-length exponent), run each candidate in seeded worlds, keep the
longest-living, mutate, repeat. CMA-ES (Hansen & Ostermeier 2001) is a robust
off-the-shelf choice. Evolve in mixed populations, not alone: an agent tuned in
an empty world may do badly among rivals.

**Exercise.** Evolve Grazer's three numbers against a mixed population, then
check the result on seeds it never saw. Did it overfit?

---

## Going further

- Wilensky & Rand (2015) is a friendly introduction to agent-based modelling,
  the research field survival mode belongs to.
- Interesting questions to measure: Does terrain (hills hiding food) favour
  memory over search? Do mixed populations live longer than single-species ones?
  Is there a stable mix of sharers and non-sharers?

## References

- Barnard, C. J., & Sibly, R. M. (1981). Producers and scroungers: A general model
  and its application to captive flocks of house sparrows. *Animal Behaviour*, 29,
  543–550.
- Bonabeau, E., Dorigo, M., & Theraulaz, G. (1999). *Swarm Intelligence: From
  Natural to Artificial Systems*. Oxford University Press.
- Braitenberg, V. (1984). *Vehicles: Experiments in Synthetic Psychology*. MIT Press.
- Charnov, E. L. (1976). Optimal foraging, the marginal value theorem.
  *Theoretical Population Biology*, 9(2), 129–136.
- Fretwell, S. D., & Lucas, H. L. (1969). On territorial behavior and other factors
  influencing habitat distribution in birds. *Acta Biotheoretica*, 19, 16–36.
- Hansen, N., & Ostermeier, A. (2001). Completely derandomized self-adaptation in
  evolution strategies. *Evolutionary Computation*, 9(2), 159–195.
- Hardin, G. (1968). The tragedy of the commons. *Science*, 162, 1243–1248.
- Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). A formal basis for the
  heuristic determination of minimum cost paths. *IEEE Transactions on Systems
  Science and Cybernetics*, 4(2), 100–107.
- Holland, J. H. (1975). *Adaptation in Natural and Artificial Systems*. University
  of Michigan Press.
- MacArthur, R. H., & Pianka, E. R. (1966). On optimal use of a patchy environment.
  *The American Naturalist*, 100, 603–609.
- Maynard Smith, J., & Price, G. R. (1973). The logic of animal conflict. *Nature*,
  246, 15–18.
- Reynolds, C. W. (1987). Flocks, herds and schools: A distributed behavioral model.
  *Computer Graphics (SIGGRAPH '87)*, 21(4), 25–34.
- Stanley, K. O., & Miikkulainen, R. (2002). Evolving neural networks through
  augmenting topologies. *Evolutionary Computation*, 10(2), 99–127.
- Stephens, D. W., & Krebs, J. R. (1986). *Foraging Theory*. Princeton University Press.
- Sutton, R. S., & Barto, A. G. (2018). *Reinforcement Learning: An Introduction*
  (2nd ed.). MIT Press.
- Viswanathan, G. M., Buldyrev, S. V., Havlin, S., da Luz, M. G. E., Raposo, E. P., &
  Stanley, H. E. (1999). Optimizing the success of random searches. *Nature*, 401,
  911–914.
- Watkins, C. J. C. H., & Dayan, P. (1992). Q-learning. *Machine Learning*, 8, 279–292.
- Wilensky, U., & Rand, W. (2015). *An Introduction to Agent-Based Modeling*. MIT Press.
