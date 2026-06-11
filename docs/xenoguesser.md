# Xenoguesser

> A hyperspace inference engine. The engine seeds a hidden world, simulates life
> forward across deep time, and shows you only the **final form**. You read that
> form through alien instruments and reverse-engineer the world that produced it.

The premise: **the final form cannot lie.** Every trait is downstream of an
earlier pressure. A species is not random — its body, senses, cognition, society,
and self-modification are fossilized consequences of its starting conditions. The
planet writes the first draft, evolution edits it, culture starts editing
evolution back, and after a singularity the species reshapes itself — but even
that reshaping reveals what it feared, valued, worshipped, optimized for, or could
never escape.

Each alien is **a theorem with skin.**

---

## 0. The hidden Worldseed

A round does not begin with lore. It begins with a hidden **Worldseed** — a set
of causal facts the player never sees directly:

`planet type · star system · gravity · atmosphere · light cycles · chemistry ·
climate instability · catastrophes · predator pressure · resource scarcity ·
terrain · time scale · biosphere logic`

The engine then *conceptually* simulates that seed forward (not numerically
perfect — narratively, by rule) along the causal pipeline:

```
worldseed → ecology → body plan → senses → cognition → social structure
          → culture → technology → self-modification → final form
```

The player sees only the final form. Because each stage is derived from the
stage before it, the body is a transcript: read it backward and the Worldseed
falls out.

In the implementation, a Worldseed is represented as a set of **causal tags**
(`high_gravity`, `dim_light`, `flare`-equivalent `radiation_pressure`,
`synchronization`, `catastrophe`, …). The hidden seed is the union of tags
implied by the world's "true" answers, so a perfect reconstruction scores 100%
and every world is internally consistent by construction. See
`data/xenoguesser.ts`.

---

## 1. Core gameplay loop

```
   ┌─────────────────────────────────────────────────────────┐
   │ 1. SCAN      Probe the final form with six instruments.   │
   │              You don't read a dossier — you operate tools  │
   │              and assemble the evidence yourself.          │
   │                                                          ▼ │
   │ 2. INFER     Run each clue backward through the causal     │
   │              pipeline. Gracile sail-body → low gravity.    │
   │              Costly honest signalling → a world too        │
   │              synchronized to permit deception.            │
   │                                                          ▼ │
   │ 3. RECONSTRUCT  Commit a guess across 9 axes. You are not  │
   │              labelling — you are rebuilding the Worldseed. │
   │                                                          ▼ │
   │ 4. RESOLVE   The seed unseals. You're scored on the CAUSAL │
   │              TAGS you recovered, not the labels you picked.│
   │                                                          ▼ │
   │ 5. LEARN     The full simulation chain is revealed, plus a │
   │              ledger of which causal tags you hit, missed,  │
   │              or invented. The next world is now readable.  │
   └─────────────────────────────────────────────────────────┘
```

This is forensic inference, not trivia recall. You are never asked to *remember*
a fact — you are asked to run a chain from effect (the body) to cause (the
world). The reveal always shows the chain, so a wrong guess teaches the rule.

---

## 2. The six instruments (what the player sees)

The player does not get handed facts — they operate **instruments** and read the
output, like using alien tools on a recovered specimen.

1. **Morphology scan** — body plan, symmetry, limbs, skin/armor, eyes, sensory
   organs, locomotion. *(Sensory ecology: a creature builds the senses its world
   rewards and discards the rest.)*
2. **Metabolism scan** — energy source, temperature range, chemistry/oxygen
   needs, scarcity and radiation adaptations. *(Metabolism and ecological
   tradeoffs.)*
3. **Behavioural echo** — glimpses of hunting, hiding, mating, migration, ritual,
   cooperation, deception, warfare, care-taking. *(Natural and sexual selection,
   kin selection, eusociality.)*
4. **Culture residue** — architectural fragments, myths, taboos, symbols, tools,
   burial patterns, communication traces. *(Niche construction, gene-culture
   coevolution.)*
5. **Singularity artifact** — evidence of how the species modified itself after
   gaining control over its own biology / embodiment. *(Self-domestication and
   cultural feedback loops.)*
6. **Planetary shadow** — indirect hints of gravity, light, atmosphere, seasons,
   storms, radiation, oceans, caves, moons, stellar behaviour. *(The planet read
   off the body that adapted to it.)*

On harder clearances some instruments go **offline** — you must infer that
dimension from the others, exactly like reconstructing an organism from partial
remains.

---

## 3. What the player reconstructs (the 9 axes)

| # | Axis | Question |
|---|---|---|
| 1 | **Planet type** | What world wrote the first draft? |
| 2 | **Star system** | What star set the tempo of deep time? |
| 3 | **Environmental pressures** | Which selection pressures did the most editing? *(multi)* |
| 4 | **Evolutionary pathway** | What lineage produced this body? |
| 5 | **Cognitive adaptations** | How did this mind learn to think? *(multi)* |
| 6 | **Cultural consequences** | What civilization emerged? *(multi)* |
| 7 | **Singularity?** | Did the species gain control over its own biology? |
| 8 | **Culture → biology** | How did culture reshape biology / the post-biological form? |
| 9 | **Could never escape** | What does the final form reveal it can never escape? |

The axes follow the causal pipeline, so a strong player reasons *forward* through
the chain even while reconstructing it backward from the body.

---

## 4. Causal scoring (rewards reasoning, not trivia)

This is the heart of the design. Scoring happens at the **causal tag** level, not
the label level.

- Every answer option across all 9 axes carries the causal **tags it implies**
  (e.g. "Red dwarf — dim, flare-prone" implies `red_dwarf`, `dim_light`,
  `long_timescale`).
- When you lock in, the engine unions the tags from *all* your selections into
  the seed you reconstructed, and compares it to the world's hidden true seed.
- **Match % = (tags you recovered − 0.35 × false leads) / total true tags**,
  clamped to 0–100. Points = match% × 1000 per world.

The consequence is exactly what causal reasoning deserves:

> Suppose the truth is a *tidally locked red dwarf world with violent flare
> radiation*. You guess "dark unstable world" (wrong planet label) but you also
> select **radiation pressure**, **darkness**, **synchronization**, and a **red
> dwarf** star. You recover `dim_light`, `radiation_pressure`, `darkness`,
> `red_dwarf`, `synchronization` — most of the seed — and score well **even
> though your planet label was wrong.** Naming the right *pressure* is what
> counts.

The reveal shows a **causal ledger**: which tags you hit (✓), missed (✗), and
invented as false leads. That ledger, not the point total, is the teacher.

**Ranks** (over a 5-world run, % of total seed recovered):
`< 40%` Drifter in the Dark · `40–60%` Field Xenologist · `60–76%` Forensic
Exobiologist · `76–90%` Civilization Coroner · `> 90%` Oracle of Dead Worlds.

---

## 5. Difficulty

| Level | Instruments online | What it tests |
|---|---|---|
| **Cadet** | all six | learning the trait→cause rules |
| **Field** | all six | full reconstruction at face value |
| **Coroner** | planetary shadow offline | infer the planet from the body alone |
| **Cold Case** | shadow + singularity offline | rebuild the deep history *and* the self-modification from morphology, metabolism, behaviour, and culture only |

Harder modes don't make the answer arbitrary — they remove *readings*, so you
triangulate from fewer instruments. Convergent evolution (two worlds, one wing)
means no single trait is decisive anyway; the expert reads the *combination*.

---

## 6. Trait → environment logic

The body is a transcript of physics and ecology. Reusable rules:

| Observed trait | Most likely cause | Why |
|---|---|---|
| Dense, low, compact; slow; compression tools | **High gravity** | Tall structures fall; mass is cheap, height lethal. |
| Gracile, oversized surfaces, fragile bones | **Low gravity / thin air** | Falls don't kill; lift surfaces are free. |
| Streamlined, finned, pressure-rated skin | **Ocean / high-pressure medium** | Drag and pressure dominate; no fixed "up". |
| One fixed-direction eye-cluster; split hot/cold body | **Tidal lock** | The sky never moves; you live on the terminator. |
| Heavy shielding, ablative/ceramic skin, error-correcting redundancy | **High radiation / flare star** | Molecular damage is the main killer; you armor and duplicate. |
| Hyper-acute prediction senses, twitch reflexes, paranoia | **Chaotic / multi-star world** | Survival = forecasting and overreaction. |
| Storage organs, dormancy, boom-bust cycle | **Seasonality / scarcity** | Feast-or-famine selects for caching and dormancy. |
| Burrowing, fireproofing, deep memory of "before" | **Catastrophe world** | Periodic resets select for refuge-seeking and surviving information. |
| Eusocial castes, sterile workers, chemical comms | **Eusociality** (kin selection) | Shared genes make self-sacrifice pay; the colony is the organism. |
| Honest, costly, hard-to-fake signals | **Synchronization-critical world** | Deception is too expensive when survival needs coordination. |
| Dwarfism/gigantism, lost defenses, hyper-specialization | **Island effect / isolation** | No predators or bounded resources warp size and erase costly traits. |

Senses follow **sensory ecology**: no eyes → darkness/murk; EM or dosimetric
sense → a radiation-loud world; dominant chemoreception → dense, slow medium.

---

## 7. Environment → culture logic

The same pressures that shaped the body shape the civilization. Culture is the
planet's second draft.

| Environment | Cultural attractor | Mechanism |
|---|---|---|
| Chaotic / unpredictable | Prediction systems, rigid coordination, **honesty norms** | Deception breaks synchronization; liars get the group killed. |
| Extreme light/dark cycles | Astronomy, prophecy, **fear of the sky**, mass ritual | The sky is the master variable; predicting it is power. |
| High gravity | Efficiency obsession, low architecture, mass-as-virtue | Every motion costs; waste is the cardinal sin. |
| Seasonal / scarce | Storage religion, reciprocity ethics, boom-bust politics | Surviving the lean season organizes the whole society. |
| Catastrophe-prone | Collapse-and-rebirth myth, **archival obsession**, refuge architecture | Civilization has died before; remembering across the reset is sacred. |
| Abundant / stable | Exploration, expansion, risk-seeking status games | Survival is solved, so novelty becomes the new selection pressure. |
| High predation | Caste/hierarchy, fortress culture, militarized loyalty | The out-group is lethal; cohesion and walls are survival tech. |

Culture is **niche construction** turned inward: the species reshapes its
environment, which changes selection pressures on the next generation —
**gene-culture coevolution**. Self-domestication begins here.

---

## 8. Culture → genetics / culture → post-biology logic

After a singularity a species rewrites its own substrate — but it rewrites
*toward* what its history made it want and *away* from what it made it fear. The
edit is a confession.

| Cultural pressure | Self-directed edit | The tell it leaves |
|---|---|---|
| Efficiency cult (high-g) | Fuse tools to body, strip waste | Bodies look engineered for load; nothing decorative survives. |
| Honesty / coordination | **Anti-deception biology**, broadcast internal state | They cannot lie even post-upload — they removed the hardware for it. |
| Fear of dark / forgetting | Distributed memory, longevity editing, redundant archives | They back themselves up obsessively; information death terrifies them. |
| Caste society | Engineered castes, germline-locked roles | Post-biological "individuals" still come in fixed functional types. |
| Catastrophe trauma | Substrate migration (upload), fireproof embodiment | They distrust any single point of failure, including their own bodies. |
| Purity / ritual taboo | **Resisted** modification; sacred unmodified form | The final form is conspicuously *un*-edited — the restraint is the culture. |

The rule the player internalizes: **post-biological does not mean post-history.**
The upload remembers the planet. The trauma is load-bearing.

---

## 9. Example world (what the player sees, Field difficulty)

> **Specimen XG-114 · unresolved final form**
>
> **Morphology scan** — Squat, four-fold radial body; centre of mass a hand-width
> off the ground. Strut-lattice skeleton, matte mineral hide like fired clay, no
> ornament. Low recessed eyes that read the ground, not the sky. It never jumps.
>
> **Metabolism scan** — Slow, dense, thermally stable chemistry; energy brutally
> conserved. Sealed integument suggests it evolved against high external pressure.
>
> **Behavioural echo** — Movement by sequential bracing. Speaks in low ground-
> vibration "drumspeech" — costly, hard to fake. Disputes settled by who moves the
> most mass with the least effort.
>
> **Culture residue** — Low, buried structures. Tools work by compression and
> leverage — wedges, presses, screw-threads — never swinging. The most honoured
> objects are simply the heaviest.
>
> **Singularity artifact** — The hide is wear-polished into the shapes of presses
> and levers; late remains show tools no longer carried but grown. Manipulators
> and instruments have fused into one undecorated surface.
>
> **Planetary shadow** — Nothing tall survives. Light traces faint and red-shifted;
> the sky barely registers in the sensory architecture.

Intended reading: *everything here is a gravity transcript under a dim star.*

---

## 10. Example reveal (after resolve)

> ### CAUSAL LEDGER — The Vaultwrights · **86% seed match**
>
> You reconstructed 12 of 14 causal tags · 1 false lead.
>
> ✓ high gravity ✓ gravity load ✓ red dwarf ✓ dim light ✓ long deep-time
> ✓ fluid/atmospheric pressure ✓ scarcity ✓ toolmaker lineage ✓ efficiency culture
> ✓ reached singularity ✓ fused tools to body ✓ cannot escape gravity
> ✗ slow cognition ✗ spatial cognition · ~~dense atmosphere~~ *(false lead)*
>
> **Axis verdicts:** Planet ✓ exact · Star ✓ exact · Pressures ~ close · Evolution
> ✓ exact · Cognition ✗ off · Culture ✓ exact · Singularity ✓ exact · Feedback ✓
> exact · Could never escape ✓ exact.
>
> **The simulation, unsealed:** dense rock under a dim red dwarf → height lethal,
> mass cheap, eyes abandon the sky → energy scarcity makes waste the cardinal sin →
> given self-control they fuse tool to body. *They did not transcend gravity. They
> sanctified it.*

---

## 11. Example world library

Six seed worlds, each a closed causal proof (shipped in `data/xenoguesser.ts`):

1. **The Vaultwrights** — high-gravity rock, red dwarf. Efficiency-as-morality;
   fused tools into the body. *Reads as:* gravity all the way down.
2. **The Tide-Choir** — tidally locked red dwarf. Live on the terminator; one
   fixed-direction sensorium; astronomy-as-religion; edited for longevity so the
   calendar never breaks. *Reads as:* a sky that never moves becomes a god.
3. **The Sundered Hum** — chaotic binary, volcanic world. Eusocial, hyper-
   predictive, costly honest signalling; engineered away the ability to lie.
   *Reads as:* a world too unpredictable to permit deception.
4. **The Ashforged** — volcanic world, dying star. Burrowers, fireproof,
   collapse-rebirth myth, archival obsession; uploaded to survive the next reset.
   *Reads as:* a civilization that has already died and refuses to forget.
5. **The Mirrorkin** — global ocean, sun-like star, post-singularity. Synthetic
   bodies that *kept* the aquatic form out of reverence; sensory augmentation.
   *Reads as:* you can leave the ocean but it stays in the design language.
6. **The Long Patient** — low-gravity, thin-atmosphere, blue-white giant. Gracile,
   radiation-hardened, patient, archival; edited for longevity to out-wait the
   star. *Reads as:* a fragile body under a violent star learns patience.

---

## 12. Replayability without alien slop

Random aliens are noise. A Xenoguesser world is only good if it is a **closed
causal proof** — every instrument reading must trace to a Worldseed tag, and the
tags must form one coherent world.

1. **Seed-first, not trait-first.** You never roll random traits. You roll a
   *Worldseed* (planet + star + pressures), then *derive* the body, cognition,
   culture, and self-modification from the rule tables (§6–8). The final form is
   the **consequence** of the seed, so it is always solvable.
2. **Every reading is load-bearing.** A generated world is rejected if any
   instrument reading doesn't trace to a seed tag, or if two readings imply
   contradictory worlds — unless the contradiction is an intentional convergent
   decoy.
3. **Convergence as designed difficulty.** Harder worlds inject *one* trait two
   worlds could explain; the player triangulates from the rest. Principled, not
   arbitrary — it teaches that single traits don't identify worlds.
4. **Seeded daily challenge.** A date-seed generates the same run for everyone →
   leaderboards and shared post-mortems. Reproducible, so it's fair.
5. **Curated > generated for the core set.** Hand-authored "named" worlds anchor
   the quality bar; procedural worlds fill the long tail but are validated against
   the rule tables before they're ever shown.
6. **Themed seed packs.** "Tidally Locked Worlds," "After the Singularity,"
   "Eusocial Empires," "Dead Stars" — each constrains the seed-roll to a region of
   the possibility space, so variety comes from new corners of a coherent universe,
   never from noise.

The anti-slop rule in one line: **seed worlds, derive bodies, and reject any
world that isn't a closed causal proof.** Difficulty comes from taking
instruments offline and adding principled convergent decoys — never from making
the answer arbitrary.
