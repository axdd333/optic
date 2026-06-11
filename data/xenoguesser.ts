// Xenoguesser — a hyperspace inference engine.
// Design rationale lives in docs/xenoguesser.md.
//
// Central architecture: every world begins as a hidden WORLDSEED — a set of
// causal *tags* (gravity, light, chemistry, catastrophe, predation, …). The
// engine conceptually simulates that seed forward:
//
//   worldseed → ecology → body plan → senses → cognition → social structure
//             → culture → technology → self-modification → final form
//
// The player only sees the final form, read through six instruments. They then
// reconstruct the seed across nine axes. Scoring happens at the TAG level, not
// the label level: naming the right *pressure* earns credit even if the exact
// planet category is wrong. The final form cannot lie, because every trait is
// downstream of an earlier tag.

export type Tag = string;

// Human-readable labels for the causal tags, used by the reveal ledger.
export const TAG_LABELS: Record<Tag, string> = {
  // planetary shadow
  high_gravity: 'high gravity',
  low_gravity: 'low gravity',
  dense_atmosphere: 'dense atmosphere',
  thin_atmosphere: 'thin atmosphere',
  dim_light: 'dim light',
  harsh_light: 'harsh light',
  chaotic_light: 'chaotic light',
  fixed_sky: 'fixed sky (tidal lock)',
  thermal_gradient: 'permanent thermal gradient',
  extreme_seasons: 'extreme seasons',
  aquatic_world: 'ocean world',
  volcanic_world: 'volcanic world',
  arid_world: 'arid world',
  // stellar / time
  red_dwarf: 'red dwarf',
  sunlike: 'sun-like star',
  binary_star: 'binary star',
  blue_giant: 'blue-white giant',
  dying_star: 'dying / variable star',
  long_timescale: 'long deep-time',
  short_timescale: 'short, violent timescale',
  // pressures
  gravity_load: 'gravity load',
  radiation_pressure: 'radiation',
  scarcity: 'scarcity',
  seasonality_pressure: 'seasonality',
  catastrophe: 'catastrophe cycles',
  predation: 'predation',
  darkness: 'darkness',
  synchronization: 'synchronization-critical',
  pressure_medium: 'fluid / atmospheric pressure',
  isolation: 'isolation',
  instability: 'climate instability',
  // lineage
  toolmaker: 'toolmaker lineage',
  eusocial: 'eusocial colony',
  symbiosis: 'symbiosis',
  aquatic_origin: 'aquatic origin',
  sessile_origin: 'sessile origin',
  ambush_lineage: 'ambush-predator lineage',
  island_effect: 'island effect',
  // cognition
  prediction_cognition: 'predictive cognition',
  collective_cognition: 'collective cognition',
  slow_cognition: 'slow, deliberate cognition',
  memory_cognition: 'memory-centered cognition',
  spatial_cognition: 'spatial cognition',
  chemical_cognition: 'chemical cognition',
  // culture
  efficiency_culture: 'efficiency culture',
  astronomy_prophecy: 'astronomy & prophecy',
  honesty_norms: 'honesty norms',
  archival_culture: 'archival culture',
  caste_culture: 'caste & hierarchy',
  expansion_culture: 'expansion culture',
  purity_culture: 'purity culture',
  // singularity / feedback
  reached_singularity: 'reached singularity',
  pre_singularity: 'pre-singularity',
  tool_fusion: 'fused tools to body',
  caste_engineering: 'engineered castes',
  substrate_upload: 'substrate upload',
  longevity_edit: 'longevity editing',
  sensory_aug: 'sensory augmentation',
  anti_deception: 'engineered anti-deception',
  resisted_modification: 'resisted modification',
  // what it could never escape
  bound_gravity: 'cannot escape gravity',
  bound_dark: 'cannot escape the dark',
  bound_chaos: 'cannot escape chaos',
  bound_forgetting: 'cannot escape forgetting',
  bound_sea: 'cannot escape the sea',
  bound_colony: 'cannot escape the colony',
  bound_star: 'cannot escape the star',
};

// ---------------------------------------------------------------------------
// The nine forensic axes. Every option carries the causal tags it *implies* —
// that mapping is what lets scoring reward causal reasoning over label trivia.
// ---------------------------------------------------------------------------

export type AxisId =
  | 'planet'
  | 'star'
  | 'pressures'
  | 'evolution'
  | 'cognition'
  | 'culture'
  | 'singularity'
  | 'feedback'
  | 'escape';

export interface AxisOption {
  key: string;
  label: string;
  tags: Tag[];
}

export interface Axis {
  id: AxisId;
  title: string;
  prompt: string;
  multi: boolean;
  options: AxisOption[];
}

export const AXES: Axis[] = [
  {
    id: 'planet',
    title: 'Planet type',
    prompt: 'What world wrote the first draft?',
    multi: false,
    options: [
      { key: 'highg', label: 'High-gravity rock', tags: ['high_gravity', 'gravity_load'] },
      { key: 'lowg', label: 'Low-gravity dwarf', tags: ['low_gravity', 'thin_atmosphere'] },
      { key: 'ocean', label: 'Global ocean', tags: ['aquatic_world', 'pressure_medium'] },
      { key: 'tidelocked', label: 'Tidally locked world', tags: ['fixed_sky', 'thermal_gradient', 'dim_light'] },
      { key: 'tilt', label: 'Extreme axial tilt', tags: ['extreme_seasons', 'seasonality_pressure', 'instability'] },
      { key: 'volcanic', label: 'Volcanic / geologically violent', tags: ['volcanic_world', 'catastrophe'] },
      { key: 'arid', label: 'Arid scarcity world', tags: ['arid_world', 'scarcity'] },
      { key: 'toxic', label: 'Thick toxic atmosphere', tags: ['dense_atmosphere', 'pressure_medium'] },
    ],
  },
  {
    id: 'star',
    title: 'Star system',
    prompt: 'What star set the tempo of deep time?',
    multi: false,
    options: [
      { key: 'reddwarf', label: 'Red dwarf — dim, flare-prone, long-lived', tags: ['red_dwarf', 'dim_light', 'long_timescale'] },
      { key: 'sunlike', label: 'Sun-like single star', tags: ['sunlike'] },
      { key: 'binary', label: 'Binary / multiple star — chaotic light', tags: ['binary_star', 'chaotic_light', 'instability'] },
      { key: 'giant', label: 'Blue-white giant — harsh, short-lived', tags: ['blue_giant', 'harsh_light', 'radiation_pressure', 'short_timescale'] },
      { key: 'dying', label: 'Aging / variable star', tags: ['dying_star', 'instability'] },
    ],
  },
  {
    id: 'pressures',
    title: 'Environmental pressures',
    prompt: 'Which selection pressures did the most editing? (choose all that fit)',
    multi: true,
    options: [
      { key: 'gravity', label: 'Gravity / load', tags: ['gravity_load'] },
      { key: 'radiation', label: 'Radiation', tags: ['radiation_pressure'] },
      { key: 'scarcity', label: 'Scarcity', tags: ['scarcity'] },
      { key: 'seasonality', label: 'Seasonality', tags: ['seasonality_pressure'] },
      { key: 'catastrophe', label: 'Catastrophe / resets', tags: ['catastrophe'] },
      { key: 'predation', label: 'Predation', tags: ['predation'] },
      { key: 'darkness', label: 'Darkness / poor light', tags: ['darkness', 'dim_light'] },
      { key: 'synchronization', label: 'Synchronization-critical survival', tags: ['synchronization'] },
      { key: 'apressure', label: 'Fluid / atmospheric pressure', tags: ['pressure_medium'] },
      { key: 'isolation', label: 'Isolation / island effect', tags: ['isolation', 'island_effect'] },
      { key: 'instability', label: 'Climate instability', tags: ['instability'] },
    ],
  },
  {
    id: 'evolution',
    title: 'Evolutionary pathway',
    prompt: 'What lineage produced this body?',
    multi: false,
    options: [
      { key: 'toolmaker', label: 'Generalist toolmaker', tags: ['toolmaker'] },
      { key: 'eusocial', label: 'Eusocial colony / superorganism', tags: ['eusocial', 'collective_cognition'] },
      { key: 'symbiotic', label: 'Symbiosis / merged organisms', tags: ['symbiosis'] },
      { key: 'aquatic', label: 'Aquatic-to-land transition', tags: ['aquatic_origin'] },
      { key: 'sessile', label: 'Sessile (rooted) to mobile', tags: ['sessile_origin'] },
      { key: 'ambush', label: 'Ambush-predator lineage', tags: ['ambush_lineage', 'predation'] },
      { key: 'island', label: 'Island dwarfism / gigantism', tags: ['island_effect', 'isolation'] },
    ],
  },
  {
    id: 'cognition',
    title: 'Cognitive adaptations',
    prompt: 'How did this mind learn to think? (choose all that fit)',
    multi: true,
    options: [
      { key: 'prediction', label: 'Prediction & forecasting', tags: ['prediction_cognition'] },
      { key: 'collective', label: 'Collective / distributed mind', tags: ['collective_cognition'] },
      { key: 'slow', label: 'Slow, deliberate, energy-frugal', tags: ['slow_cognition'] },
      { key: 'memory', label: 'Memory & archive obsession', tags: ['memory_cognition'] },
      { key: 'spatial', label: 'Spatial / structural reasoning', tags: ['spatial_cognition'] },
      { key: 'chemical', label: 'Chemical / scent-based reasoning', tags: ['chemical_cognition'] },
    ],
  },
  {
    id: 'culture',
    title: 'Cultural consequences',
    prompt: 'What civilization emerged? (choose all that fit)',
    multi: true,
    options: [
      { key: 'efficiency', label: 'Efficiency cult — waste is sin', tags: ['efficiency_culture'] },
      { key: 'prophecy', label: 'Astronomy & prophecy — fear of the sky', tags: ['astronomy_prophecy'] },
      { key: 'honesty', label: 'Honesty & coordination — deception taboo', tags: ['honesty_norms'] },
      { key: 'archival', label: 'Collapse & archive — remember the reset', tags: ['archival_culture'] },
      { key: 'caste', label: 'Caste & hierarchy — fortress loyalty', tags: ['caste_culture'] },
      { key: 'expansion', label: 'Exploration & expansion — risk-seeking', tags: ['expansion_culture'] },
      { key: 'purity', label: 'Ritual purity — sacred unchanged form', tags: ['purity_culture'] },
    ],
  },
  {
    id: 'singularity',
    title: 'Singularity?',
    prompt: 'Did the species gain control over its own biology?',
    multi: false,
    options: [
      { key: 'reached', label: 'Yes — crossed the threshold', tags: ['reached_singularity'] },
      { key: 'partial', label: 'Partial — early self-modification only', tags: ['reached_singularity'] },
      { key: 'no', label: 'No — still purely biological', tags: ['pre_singularity'] },
    ],
  },
  {
    id: 'feedback',
    title: 'Culture → biology',
    prompt: 'How did culture reshape biology or the post-biological form?',
    multi: false,
    options: [
      { key: 'toolfusion', label: 'Fused tools into the body', tags: ['tool_fusion'] },
      { key: 'castegen', label: 'Engineered locked castes', tags: ['caste_engineering'] },
      { key: 'upload', label: 'Migrated to a digital / synthetic substrate', tags: ['substrate_upload'] },
      { key: 'longevity', label: 'Longevity & distributed-memory editing', tags: ['longevity_edit'] },
      { key: 'sensory', label: 'Sensory augmentation', tags: ['sensory_aug'] },
      { key: 'antilie', label: 'Engineered away the ability to deceive', tags: ['anti_deception'] },
      { key: 'minimal', label: 'Resisted modification — kept the sacred form', tags: ['resisted_modification'] },
    ],
  },
  {
    id: 'escape',
    title: 'Could never escape',
    prompt: 'What does the final form reveal it could never escape?',
    multi: false,
    options: [
      { key: 'gravity', label: 'The weight of its world', tags: ['bound_gravity'] },
      { key: 'dark', label: 'The dark / the sky', tags: ['bound_dark'] },
      { key: 'chaos', label: 'Chaos & unpredictability', tags: ['bound_chaos'] },
      { key: 'forgetting', label: 'Forgetting / information death', tags: ['bound_forgetting'] },
      { key: 'sea', label: 'The sea it came from', tags: ['bound_sea'] },
      { key: 'colony', label: 'The colony it can never leave', tags: ['bound_colony'] },
      { key: 'star', label: 'The star that would not stop burning', tags: ['bound_star'] },
    ],
  },
];

const AXIS_BY_ID: Record<AxisId, Axis> = Object.fromEntries(
  AXES.map((a) => [a.id, a]),
) as Record<AxisId, Axis>;

export function optionLabel(axisId: AxisId, key: string): string {
  return AXIS_BY_ID[axisId]?.options.find((o) => o.key === key)?.label ?? key;
}

// ---------------------------------------------------------------------------
// Worlds. Authored as a set of correct option keys per axis (`truth`); the
// hidden tag-seed is DERIVED from those options so a perfect set of guesses
// always scores 100% and the world is internally consistent by construction.
// Instruments are what the player sees; chain is the simulation shown on reveal.
// ---------------------------------------------------------------------------

export type InstrumentId =
  | 'morphology'
  | 'metabolism'
  | 'behavior'
  | 'culture'
  | 'singularity'
  | 'shadow';

export interface Instrument {
  id: InstrumentId;
  label: string;
  reading: string;
}

export interface ChainStage {
  stage: string;
  text: string;
}

interface WorldDef {
  id: string;
  codename: string;
  truth: Record<AxisId, string[]>;
  /** Tags the seed carries that no single correct option exposes. */
  extraTags?: Tag[];
  instruments: Instrument[];
  chain: ChainStage[];
  verdict: string;
}

export interface Worldseed extends WorldDef {
  trueTags: Tag[];
}

const INSTRUMENT_ORDER: InstrumentId[] = [
  'morphology',
  'metabolism',
  'behavior',
  'culture',
  'singularity',
  'shadow',
];

function deriveTags(def: WorldDef): Tag[] {
  const set = new Set<Tag>(def.extraTags ?? []);
  for (const axis of AXES) {
    for (const key of def.truth[axis.id] ?? []) {
      const opt = axis.options.find((o) => o.key === key);
      opt?.tags.forEach((t) => set.add(t));
    }
  }
  return [...set];
}

const WORLD_DEFS: WorldDef[] = [
  {
    id: 'xg-114',
    codename: 'The Vaultwrights',
    truth: {
      planet: ['highg'],
      star: ['reddwarf'],
      pressures: ['gravity', 'apressure', 'scarcity'],
      evolution: ['toolmaker'],
      cognition: ['slow', 'spatial'],
      culture: ['efficiency'],
      singularity: ['reached'],
      feedback: ['toolfusion'],
      escape: ['gravity'],
    },
    instruments: [
      { id: 'morphology', label: 'Morphology scan', reading: 'Squat, four-fold radial body; centre of mass a hand-width off the ground. Strut-lattice skeleton, matte mineral hide like fired clay, no ornament. Low recessed eyes that read the ground, not the sky. It settles rather than stands and never leaves itself unsupported.' },
      { id: 'metabolism', label: 'Metabolism scan', reading: 'Slow, dense, thermally stable chemistry. Energy budget is brutally conserved — every motion is metabolically accounted for. Sealed integument suggests it evolved against high external pressure. Few large meals, long fasts.' },
      { id: 'behavior', label: 'Behavioural echo', reading: 'Movement by sequential bracing; it never jumps. Speaks in low ground-vibration "drumspeech" that carries through rock and is costly to fake. Disputes are settled by who can move the most mass with the least effort.' },
      { id: 'culture', label: 'Culture residue', reading: 'Low, thick-walled, partly buried structures. Tools work by compression and leverage — wedges, presses, screw-threads — never by swinging or throwing. The most honoured objects are simply the heaviest.' },
      { id: 'singularity', label: 'Singularity artifact', reading: 'The hide is wear-polished into the exact shapes of presses and levers. Late-stage remains show tools no longer carried but grown — the manipulators and the instruments have fused into one undecorated surface.' },
      { id: 'shadow', label: 'Planetary shadow', reading: 'Nothing tall survives in the record; every structure hugs the floor. Light traces are faint and red-shifted; the sky barely registers in the sensory architecture. A heavy, dim, patient world.' },
    ],
    chain: [
      { stage: 'Worldseed', text: 'A dense rock under a dim red dwarf. High gravity, thick air, thin resources, deep time.' },
      { stage: 'Ecology → body', text: 'Height is lethal and mass is cheap, so bodies stay low, broad, and strut-braced; eyes abandon a sky no one needs.' },
      { stage: 'Cognition → culture', text: 'Energy scarcity makes waste the cardinal sin. Slow spatial minds build an ethic where efficiency is morality and "heavy" means "real".' },
      { stage: 'Self-modification → final form', text: 'Given control over their bodies, they edit toward the press and the lever until the tool is the body. They did not transcend gravity — they sanctified it.' },
    ],
    verdict: 'A heavy world makes a heavy body, a heavy body makes a heavy ethic, and a heavy ethic given the power to self-edit makes a heavier body.',
  },
  {
    id: 'xg-207',
    codename: 'The Tide-Choir',
    truth: {
      planet: ['tidelocked'],
      star: ['reddwarf'],
      pressures: ['darkness', 'seasonality', 'scarcity'],
      evolution: ['toolmaker'],
      cognition: ['prediction', 'memory'],
      culture: ['prophecy'],
      singularity: ['reached'],
      feedback: ['longevity'],
      escape: ['dark'],
    },
    instruments: [
      { id: 'morphology', label: 'Morphology scan', reading: 'Tall, broken-bilateral body leaning permanently to one side. One flank pale and heat-shedding, the other dark and insulated — a thermal boundary made flesh. A single dominant eye-cluster fixed toward one horizon.' },
      { id: 'metabolism', label: 'Metabolism scan', reading: 'Split thermal regulation: it runs hot on one side and cold on the other simultaneously. Reproduction and growth are gated to narrow windows; metabolism tracks a celestial clock, not a daily one.' },
      { id: 'behavior', label: 'Behavioural echo', reading: 'Lateral, crab-like migration along a single band of terrain — never toward the burning side, never toward the frozen side. Speech is light-pulses timed to celestial events; to mis-time a phrase is to lie about the sky.' },
      { id: 'culture', label: 'Culture residue', reading: 'Vast horizon-aligned observatories. Prophets hold power. Drifting toward the dark side is the ultimate taboo. The calendar is sacred and stored in many redundant copies.' },
      { id: 'singularity', label: 'Singularity artifact', reading: 'Evidence of deliberate lifespan extension and distributed memory — they re-engineered themselves so that no generation could ever lose the calendar. The clock outlives the body by design.' },
      { id: 'shadow', label: 'Planetary shadow', reading: 'The sky in every record never moves. A permanent terminator divides fire from frost; the habitable world is a thin ring. Light is dim and unchanging in colour — a close orbit around a faint star.' },
    ],
    chain: [
      { stage: 'Worldseed', text: 'A planet tidally locked to a dim red dwarf: permanent day, permanent night, a thin liveable ring between them.' },
      { stage: 'Ecology → body', text: 'Life clings to the terminator. Bodies split into hot and cold halves and fix their gaze on an unmoving sky.' },
      { stage: 'Cognition → culture', text: 'The sky is the master variable, so predicting it becomes power. Astronomy hardens into prophecy and the calendar becomes a god.' },
      { stage: 'Self-modification → final form', text: 'They edit for longevity and distributed memory so the calendar can never break. A sky that never moves becomes a god that never moves.' },
    ],
    verdict: 'A sky that never moves becomes a god that never moves; they worship the calendar that keeps them between fire and frost.',
  },
  {
    id: 'xg-330',
    codename: 'The Sundered Hum',
    truth: {
      planet: ['volcanic'],
      star: ['binary'],
      pressures: ['synchronization', 'predation', 'catastrophe', 'instability'],
      evolution: ['eusocial'],
      cognition: ['prediction', 'collective'],
      culture: ['honesty'],
      singularity: ['reached'],
      feedback: ['antilie'],
      escape: ['chaos'],
    },
    instruments: [
      { id: 'morphology', label: 'Morphology scan', reading: 'Small, near-identical individuals in dense clusters with visible castes. Hyper-alert posture, twitch-fast reflexes. The skin involuntarily broadcasts stress, intent, and health — internal state is physically impossible to hide.' },
      { id: 'metabolism', label: 'Metabolism scan', reading: 'High-tempo, high-burn metabolism tuned for rapid response. No individual is built to survive alone; metabolic load is shared across the cluster. Energy spikes track environmental shocks.' },
      { id: 'behavior', label: 'Behavioural echo', reading: 'The cluster moves as one organism. Communication is continuous, costly, and unfakeable; a member who falls silent is assumed lost. Sterile workers die for the group without hesitation.' },
      { id: 'culture', label: 'Culture residue', reading: 'Rigid coordination protocols, elaborate prediction engines, paranoid early-warning networks. Deception has no foothold — every social technology assumes the world will lurch without warning.' },
      { id: 'singularity', label: 'Singularity artifact', reading: 'Post-biological members have fully transparent internals. They did not merely outlaw lying — they engineered away the hardware for it. Honesty is now anatomy.' },
      { id: 'shadow', label: 'Planetary shadow', reading: 'Light flickers chaotically in the record; climate lurches without pattern. Multiple light sources cast shifting shadows, and the ground itself is unstable. A world that punishes anyone who cannot predict it.' },
    ],
    chain: [
      { stage: 'Worldseed', text: 'A geologically violent planet under a binary star: chaotic light, lurching climate, recurrent disaster.' },
      { stage: 'Ecology → body', text: 'Survival demands perfect group synchronization. Kin-selected eusocial clusters form; the colony, not the individual, becomes the unit of life.' },
      { stage: 'Cognition → culture', text: 'When timing is survival, a liar gets everyone killed. Costly honest signalling and prediction engines make deception too expensive to tolerate.' },
      { stage: 'Self-modification → final form', text: 'They engineer away the ability to deceive entirely. A world too unpredictable to permit lies builds a species that cannot lie.' },
    ],
    verdict: 'A world too unpredictable to permit deception builds a species that engineered away its own ability to lie.',
  },
  {
    id: 'xg-451',
    codename: 'The Ashforged',
    truth: {
      planet: ['volcanic'],
      star: ['dying'],
      pressures: ['catastrophe', 'radiation', 'seasonality'],
      evolution: ['toolmaker'],
      cognition: ['memory', 'slow'],
      culture: ['archival'],
      singularity: ['reached'],
      feedback: ['upload'],
      escape: ['forgetting'],
    },
    instruments: [
      { id: 'morphology', label: 'Morphology scan', reading: 'Compact, armoured, built to seal and burrow; limbs fold flat into a closed shell. Ceramic, ablative integument that chars and regrows, scarred in layers like geological strata of survived disasters.' },
      { id: 'metabolism', label: 'Metabolism scan', reading: 'Dormancy-capable: it can suspend life through a catastrophe and revive after. Metabolism is tuned to outlast events, not flee them. Tolerant of heat and radiation that would sterilise most chemistries.' },
      { id: 'behavior', label: 'Behavioural echo', reading: 'Burrows and seeks refuge; moves toward shelter, not toward food. Every important message is repeated through multiple channels — behaviour optimised to survive noise and loss, not to be efficient.' },
      { id: 'culture', label: 'Culture residue', reading: 'Deep vaults of redundant records. Cyclical collapse-and-rebirth mythology; time is a wheel, not a line. Burial sites are also archives — the dead are kept as data.' },
      { id: 'singularity', label: 'Singularity artifact', reading: 'They migrated into distributed digital substrates so that no single disaster could end them. The upload is not transcendence — it is a backup. They fear a single point of failure, including their own bodies.' },
      { id: 'shadow', label: 'Planetary shadow', reading: 'Layered ash and impact horizons in the record; the surface has been reset many times. Stellar output flickers and fades — an aging star compounding a violent world.' },
    ],
    chain: [
      { stage: 'Worldseed', text: 'A volcanic world under an aging, variable star: periodic resets, radiation, harsh boom-and-bust seasons.' },
      { stage: 'Ecology → body', text: 'Recurrent catastrophe selects for armour, burrowing, dormancy, and bodies that ride out the apocalypse rather than escape it.' },
      { stage: 'Cognition → culture', text: 'Civilization has died before. Remembering across the reset becomes the highest value; memory-centred minds build an archival, cyclical culture.' },
      { stage: 'Self-modification → final form', text: 'They migrate to distributed substrates so nothing can ever fully end them. A civilization that has already died refuses, above all, to forget.' },
    ],
    verdict: 'A civilization that has already died and refuses to forget — to it, information death is the only real death.',
  },
  {
    id: 'xg-588',
    codename: 'The Mirrorkin',
    truth: {
      planet: ['ocean'],
      star: ['sunlike'],
      pressures: ['apressure', 'predation', 'darkness'],
      evolution: ['aquatic'],
      cognition: ['collective', 'spatial'],
      culture: ['purity'],
      singularity: ['reached'],
      feedback: ['sensory'],
      escape: ['sea'],
    },
    instruments: [
      { id: 'morphology', label: 'Morphology scan', reading: 'Synthetic, reconfigurable bodies — yet every configuration is streamlined, finned, neutrally buoyant. With the freedom to be anything, they remain shaped for a medium they no longer live in. Lateral-line senses for pressure and flow.' },
      { id: 'metabolism', label: 'Metabolism scan', reading: 'Engineered energy systems, but thermal and pressure tolerances still centre on deep, temperate water. They feel the medium around them more than they look at it.' },
      { id: 'behavior', label: 'Behavioural echo', reading: 'Fluid fission-fusion grouping; schools form and dissolve. Communication is whole-body bioluminescent broadcast of enormous bandwidth — the way deep-water signalers once spoke across darkness.' },
      { id: 'culture', label: 'Culture residue', reading: 'They template new bodies on ancestral aquatic forms by choice. Lineages and "schools" are preserved as sacred social memory. The old shape is holy; to abandon it is taboo.' },
      { id: 'singularity', label: 'Singularity artifact', reading: 'Heavy sensory augmentation layered onto a deliberately preserved aquatic body plan. They upgraded their senses while refusing to abandon the form of home. The reverence is the modification.' },
      { id: 'shadow', label: 'Planetary shadow', reading: 'No fixed "down" in the posture; pressure-rated surfaces; bioluminescence implying dark depths and a long predator/prey light arms race. A deep ocean under a stable, sun-like star.' },
    ],
    chain: [
      { stage: 'Worldseed', text: 'A global ocean under a stable sun-like star — deep, dark, high-pressure water full of predators that hunt by light.' },
      { stage: 'Ecology → body', text: 'Streamlined finned bodies, flow senses, and bioluminescent signalling evolve in the dark high-pressure depths.' },
      { stage: 'Cognition → culture', text: 'Fluid, spatial, collective minds build a fission-fusion society that comes to revere the ancestral form itself.' },
      { stage: 'Self-modification → final form', text: 'They augment their senses but keep the body of the sea out of reverence. You can leave the ocean — the ocean stays in the design language.' },
    ],
    verdict: 'You can leave the ocean, but the ocean stays in the design language; they kept its body out of reverence, not necessity.',
  },
  {
    id: 'xg-642',
    codename: 'The Long Patient',
    truth: {
      planet: ['lowg'],
      star: ['giant'],
      pressures: ['radiation', 'scarcity', 'seasonality'],
      evolution: ['toolmaker'],
      cognition: ['slow', 'memory'],
      culture: ['archival'],
      singularity: ['reached'],
      feedback: ['longevity'],
      escape: ['star'],
    },
    instruments: [
      { id: 'morphology', label: 'Morphology scan', reading: 'Tall, gracile, elongated — improbably thin limbs holding large sail-like membranes that would snap under any real gravity. Dense radiation-hardened integument over the light frame: heavy shielding on a fragile skeleton.' },
      { id: 'metabolism', label: 'Metabolism scan', reading: 'Energy-frugal, slow-burning chemistry in thin air; haste is metabolically unaffordable. Cells carry heavy repair and error-correction machinery against constant radiation damage.' },
      { id: 'behavior', label: 'Behavioural echo', reading: 'Slow, gliding, conserving motion. Dosimetric sense organs register radiation flux directly — it can feel a flare coming and shelters rather than races. Speech is long messages with long pauses.' },
      { id: 'culture', label: 'Culture residue', reading: 'Risk-averse, contemplative, archival. Heavy shelter-building against the sky. Status comes from patience and the long memory, not from conquest or speed.' },
      { id: 'singularity', label: 'Singularity artifact', reading: 'Their central self-directed projects are longevity and radiation-hardening — editing the body to wait out a star they cannot fight. They chose to endure rather than escape.' },
      { id: 'shadow', label: 'Planetary shadow', reading: 'Fragile oversized forms imply low gravity and thin air. Pervasive radiation shielding and flare-anticipation imply a brilliant, harsh, short-lived star flooding the world with hard light.' },
    ],
    chain: [
      { stage: 'Worldseed', text: 'A low-gravity, thin-atmosphere world under a brilliant blue-white giant: weak weight, harsh light, relentless radiation, little time.' },
      { stage: 'Ecology → body', text: 'Weak gravity allows gracile sail-bodies; the violent star forces heavy shielding and frugal, slow metabolism.' },
      { stage: 'Cognition → culture', text: 'You cannot out-build the radiation, so you out-wait it. Slow memory-minds build a patient, archival, risk-averse culture.' },
      { stage: 'Self-modification → final form', text: 'They edit for longevity and radiation-hardening to endure a star they cannot defeat. A fragile body under a violent star learns patience as a survival strategy.' },
    ],
    verdict: 'A fragile body under a violent star learns patience; they could not out-build the radiation, so they out-waited it.',
  },
];

export const WORLDS: Worldseed[] = WORLD_DEFS.map((def) => ({
  ...def,
  instruments: INSTRUMENT_ORDER.map(
    (id) => def.instruments.find((i) => i.id === id)!,
  ),
  trueTags: deriveTags(def),
}));

// ---------------------------------------------------------------------------
// Causal scoring. The score is a TAG overlap between the seed the player
// reconstructed and the hidden true seed — right pressure, wrong label still
// scores. See docs/xenoguesser.md §5.
// ---------------------------------------------------------------------------

export const PER_WORLD_MAX = 1000;
const FALSE_LEAD_WEIGHT = 0.35; // how much a wrong causal tag costs

export type Picks = Record<AxisId, string[]>;

export function emptyPicks(): Picks {
  return {
    planet: [],
    star: [],
    pressures: [],
    evolution: [],
    cognition: [],
    culture: [],
    singularity: [],
    feedback: [],
    escape: [],
  };
}

export function collectGuessTags(picks: Picks): Set<Tag> {
  const tags = new Set<Tag>();
  for (const axis of AXES) {
    for (const key of picks[axis.id] ?? []) {
      const opt = axis.options.find((o) => o.key === key);
      opt?.tags.forEach((t) => tags.add(t));
    }
  }
  return tags;
}

export type AxisVerdict = 'exact' | 'partial' | 'off' | 'blank';

export function axisVerdict(world: Worldseed, axisId: AxisId, picked: string[]): AxisVerdict {
  if (!picked.length) return 'blank';
  const truth = new Set(world.truth[axisId] ?? []);
  const hit = picked.filter((k) => truth.has(k)).length;
  if (hit === 0) return 'off';
  if (hit === truth.size && picked.length === truth.size) return 'exact';
  return 'partial';
}

export interface WorldScore {
  hitTags: Tag[];
  missedTags: Tag[];
  falseTags: Tag[];
  matchPct: number; // 0..100
  points: number; // 0..PER_WORLD_MAX
}

export function scoreWorld(world: Worldseed, picks: Picks): WorldScore {
  const guess = collectGuessTags(picks);
  const truthSet = new Set(world.trueTags);
  const hitTags = world.trueTags.filter((t) => guess.has(t));
  const missedTags = world.trueTags.filter((t) => !guess.has(t));
  const falseTags = [...guess].filter((t) => !truthSet.has(t));
  const raw =
    (hitTags.length - FALSE_LEAD_WEIGHT * falseTags.length) / world.trueTags.length;
  const frac = Math.max(0, Math.min(1, raw));
  return {
    hitTags,
    missedTags,
    falseTags,
    matchPct: Math.round(frac * 100),
    points: Math.round(frac * PER_WORLD_MAX),
  };
}

export const ROUNDS = 5;

export function rankFor(total: number): string {
  const max = ROUNDS * PER_WORLD_MAX;
  const f = total / max;
  if (f >= 0.9) return 'Oracle of Dead Worlds';
  if (f >= 0.76) return 'Civilization Coroner';
  if (f >= 0.6) return 'Forensic Exobiologist';
  if (f >= 0.4) return 'Field Xenologist';
  return 'Drifter in the Dark';
}

// Deterministic shuffle so a seed yields a reproducible run (daily challenge).
export function seededRun(seed: number): Worldseed[] {
  const arr = [...WORLDS];
  let s = seed || 1;
  for (let i = arr.length - 1; i > 0; i--) {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    const j = s % (i + 1);
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr.slice(0, ROUNDS);
}
