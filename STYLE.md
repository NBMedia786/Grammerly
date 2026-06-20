# Mysterious 7 — VO Script House Style

Derived from deep analysis of the sample scripts (Ariya Paige, Jesika Taylor-Sullivan = polished
finals/gold standard; Eli Hart, Jermaine Bennett, "Elias Otero" = first drafts). This is what the
proofreading tool grades toward: it treats this style as **correct** and only flags genuine
mechanical errors. The keystone is a shared deny-list + confidence gate in `prompts/8.yaml`.

## 1. Voice & register
Emotive, ominous true-crime narration written for **spoken delivery**. Precise factual anchors
(full names, exact dates, addresses, ages, dollar amounts) amid visceral emotional adjectives
("gut-wrenching", "gruesome", "chilling"). American (US) English. Speech is **paraphrased**, never
directly quoted (only a single contested word may get quote marks, e.g. 'provoked').

## 2. Story architecture
A withholding/recontextualization escalation arc, anchored to the investigators:
**Cold-open hook → crime scene → investigation → interrogation(s) → evidence → motive → sentencing.**
Bare section-label headers double as scene slugs ("Intro", "Police at crime scene",
"Interrogation 1", "Motive", "Sentencing"). Scripts **end abruptly on the legal outcome** — no
reflective outro or CTA in the narration.

## 3. Tense (the signature)
- **Live action → historical PRESENT** ("officers arrive", "detectives find").
- **Dated legal outcomes → PRESENT too** ("On November 8, 2024, Rhonda Jewell is found guilty";
  "the court upholds his sentence"). A date does not make it past.
- **Backstory → PAST / PAST-PERFECT**, anchored by time markers ("Just hours earlier", "had picked
  up", "had called").
- **Foreshadowing → future inside a present frame** ("with no idea that they are about to uncover…",
  "a detail investigators would later find noteworthy").
- Fixes only ever move **toward present**; never push correct present narration into past.

## 4. Sentence craft (all intentional — never "corrected")
Sentence-initial conjunctions (But/And/However/Then/So/Meanwhile); fragments for effect
("It was planned."); comma splices for breathless pacing; participial/absolute openers
("Responding to the call, officers rush in"); passive voice in procedural beats ("the body is
pulled from the tub"); a short hammer sentence after a long one; rhetorical questions; colons
before a reveal.

## 5. Punctuation
- **Em-dash (—)** is a common closed/unspaced reveal-pivot — but **its absence is equally fine**
  (Ariya, a clean final, uses none). Neither presence nor absence is a defect.
- **Mixed straight/curly quotes** are not flagged (both finals mix them).
- **No quotation marks around paraphrased speech** — do not add them.
- Bracketed VO delivery cues — `[tense]`, `[sombre, tense]`, `[high emotion]`, `[fast]` — are a
  direction system; left structurally alone (but a British spelling *inside* one is flagged).

## 6. Hooks & cliffhangers
- **Intro:** present-tense cold open (innocent scene or in-medias-res shock) undercut by a
  withholding twist promise ("…with no idea what has already happened inside").
- **Section enders pull forward:** "What they find next is truly gut-wrenching.", "but that's not
  all", "something doesn't quite add up", open questions ("Who is Jermaine protecting?").
- Techniques: dramatic irony ("little did they know"), withholding the reveal, recontextualization
  ("this wasn't random — it was planned"), escalation ("their nightmare isn't over").

## 7. What the tool FLAGS (genuine errors only)
- **Spelling:** British forms (hospitalisation→hospitalization, sombre→somber, vandalise, towards),
  including inside VO cues ([Sombre]→[Somber]); garbled terms (CRP→CPR, examin→examine);
  name/spelling inconsistency within a script (Otero/OTREO, Julissa/Julisa).
- **Grammar:** double conjunctions ("And but"), doubled/garbled verbs, missing subject, missing
  article ("shifted to hospital"→"to the hospital"), past-perfect dropped across a compound
  ("had picked up… and took"→"and taken"), dangling participles, real run-ons, word misuse
  ("terrific incident"→"terrible").
- **Punctuation:** spaced hyphen used as a dash (" - "→"—"), double commas/periods/spaces,
  orphaned lone ".", over-long ellipses ("…..").
- **Tense:** unmotivated present/past flip-flop within one live beat with no time marker.
- **Draft artifacts:** stacked alternate intros, inline editor TODOs/links, production debris.

## 8. What the tool NEVER flags (house style)
Present-tense narration; sentence-initial conjunctions; fragments; comma splices; passive in
procedural beats; em-dash presence/absence; paraphrased speech without quotes; mixed straight/curly
quotes; numerals/digits; VO cues; section headers; wordiness/redundancy/repetition or any
subjective style/flow opinion. **When it's a judgment call, the tool stays silent.**
