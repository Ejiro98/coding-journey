# Lessons (read before planning any video; add to it after every remake)

Each lesson came from a real mistake that cost time or money. Before approval 1 (script) and
again before approval 3 (stills), check the plan against every line below and say which ones
you checked. When something new goes wrong, add a lesson at the end of its section in the same
form: **what happened (video, cost) → the rule that prevents it**. If code could catch it, also
tell the viewer so a `lint` check can be added (several below are already enforced: marked [lint]).

## Script
- Elevator v1: the script drifted from what works and the visuals didn't match the words →
  copy the Hidden By Design narration shape closely: "If you… you've built…", "But…", "So…",
  "Now…", "This is a…", "Congratulations!". No new formats. [lint: hook, But timing, ending]
- Landfill draft: "the next hole" and "seeps" confused the viewer → the story stays in ONE place
  and builds on itself; plain words a 12-year-old knows. [lint: UNCOMMON words]
- Elevator v1: cartoon events (things that couldn't happen) → every line must survive a fact
  check; only real forces and real machines.
- Creator Rewards needs over 60 s → voice must be over 61 s; if not, remake at speed 1.1.

## Stills
- Elevator v1: white/empty background → always a real place (street, town, building). [style]
- Elevator v1: parts appeared before the script built them → NOT BUILT YET list in every
  prompt, and check each still for it. [automatic]
- Drain test: a zoomed still flipped the pipe's direction → a moved/zoomed still says which way
  things run ("pipes still running left to right") and is checked against the wide still.
- Landfill L06 (first version): the line said "the wind has nothing to grab" but trash was still
  visible on top → each still must SHOW the answer to its line. Read the line, then look at the
  still and ask: would a viewer see this result with the sound off?
- Landfill L07: the fill level jumped while a different thing was being built → the fill level,
  buildings and pipes stay exactly the same unless the line changes them. Write "still half
  full", "engine building still at the right edge" into every later still.
- Landfill L09/L10: the engine building and gas pipes would have vanished at the end → list
  everything already built that must stay; anything built never disappears.
- Landfill L06: the drainage pipe lost its link to the pump box and the pit came out nearly
  full instead of half → connections (pipe to pump, wires to town) go into the part's `looks`
  so every later still repeats them; give the fill level a visible measure ("liner wall shows
  above the soil all the way round"); attach the still where a connection is clearest as a reference.
- Landfill L07 (2 failed tries): "joined at the top by a horizontal pipe" became tall goalposts
  with one pipe left unconnected, and the pipes went down into the gravel → give heights against
  something visible ("knee-high above the soil"), say where things stop ("well above the gravel"),
  and say ALL for connections ("connects to ALL FOUR pipes, the leftmost included").
- Landfill L07: the image turned grainy after several stills made from stills → always attach the
  clean first still (L01) as a reference too, and remake any still that has lost sharpness.
- Landfill L06/L07: the maker passed its own stills ("a little fuller than half", pipe link not
  checked) → a separate reviewer agent answers `frames check` questions; specific yes/no questions
  per still, written before the still is made, not a general checklist.
- Landfill L01r (3 failed tries): the questions asked for a degree ("bottom of the trash soaked
  dark") that image models can't draw reliably, and one try leaked liquid below the pit early →
  ask only for things a viewer can point at ("black liquid collected at the bottom, under the trash"); put one change in each
  still and save the next change for the next still (the leak belongs in L01g).
- Landfill L03b/L06 (5 failed tries): the questions asked for things the still can't show: the
  whole line ("juice gets pumped away") when that half belongs to the close-up, and a pipe joint
  that is really buried under the fill. Adding the failed answer to the remake made it worse
  (the model drew juice leaking through the liner) → a still that shows only part of its line gets
  `line_part`; questions only ask about parts that would really be visible; before adding a
  failed answer to a prompt, check it isn't asking for something impossible.
- Landfill L06 try 2: asked for "a pipe up the side slope", the model drew a second pipe up the
  front cut face that ends in mid-air → pin every part to a place in a named still ("ONE riser at the
  BACK-RIGHT corner, exactly where it is in L03") and add "MUST BE NO: any other pipe?".
- Landfill L01g: the question demanded a shape ("wider at the bottom") no viewer would miss → only
  require what matters to the story (liquid goes DOWN from the pit INTO the water).
- Landfill L01r (kie.ai, 3 tries, $0.27; the viewer accepted try 3): try 1 drew the black liquid as a flat black sheet
  (reads as a liner), try 2 as a slab sticking out of the cut face and dripping into the soil (my fix had added "drips
  running from the bags"). All three prompts said "a shallow pool of black liquid", and the accepted try 3 also said
  "a shallow, glossy puddle", so the word "pool" was NOT the problem. What changed in try 3: it said where the liquid
  stops ("INSIDE the pit, set back from the cut-away face, with a lip of brown dirt between it and the cut face; nothing
  drips; the soil below is clean brown") and dropped the word "drips" → when a liquid must stay put, say where it stops
  and what stays clean; don't mention drips or running unless the still should show them.
- Landfill L03b try 2 (kie.ai): adding five sentences of fixes made the edit drift (camera moved, groundwater band and
  bulldozer vanished, juice leaked through the liner) → keep fixes to one or two short sentences per failed answer;
  on kie.ai, attach the single closest reference first.
- Landfill (kie.ai): each remake overwrote the previous try (same filename), so failed tries had to be fetched back from
  kie.ai by task id → keep every try (tries/<ID>_tryN) until the still passes.
- Landfill L03b (3 failed tries on kie.ai, $0.27) and L06 (2 failed tries): the questions asked a WIDE still to show the
  juice going into the pipes, and to follow the pipe from the gravel to the pump box "with no gap" after trash or soil had
  covered the joint. Every try that drew juice leaked it through the liner; the try without juice failed the line
  question; and the buried joint can never be seen → a wide still only asks what is visible at that scale (liquid into a
  pipe belongs to the close-up, L04); once fill covers a connection, ask for its visible ends (pipe in the gravel at the
  cut face, riser coming out at the corner and into the box), not the hidden middle.
- Landfill L01g (3 tries on kie.ai, $0.27): try 2 passed every question except "the trail widens as it goes down" (a
  degree); the extra sentence for try 3 fixed the trail but reshaped the pit floor into a square slab → don't ask for a
  shape degree ("widening"); ask for what a viewer reads ("one unbroken dark trail from the pit to the blue band").
- Landfill L06 (3 tries with the back-right riser prompt, $0.27): every try filled the small front-right step beside the
  cut face flush to the rim, even when the prompt named that step; try 4 failed nothing else → image models treat the
  corner next to a cut-away as part of the cut. For fill-level questions, name the walls a viewer sees (back, left,
  right), not "all the way round".
- Landfill L01b try 2: the remake added a green box (like the later pump box) and dropped the parked bulldozer → when a
  still adds machines, say "add only X and Y; everything else on the rim stays as in <ref>".
- Landfill L06 (5 tries) and L01b (3 tries): most failures came from awkward shapes in the FIRST
  still (a small front-right step beside the cut, a soft pit-bottom edge) that every later still has
  to copy, and from the model adding or removing machines → make the first still simple: one clean
  box-shaped pit with straight edges and a clear cut face, few vehicles, nothing at the rim that
  isn't in the story. It sets the shape for 15+ stills.
- Judge single failed points at phone size: a sliver no viewer would notice (L06 step) or a soft edge
  (L01b) is not worth more tries; a wrong fact (pipe to nowhere, liquid through the liner) always is.
- Landfill L07 (3 tries on kie.ai, $0.27): any mention of the gas pipes going down into the trash drew them as tall
  goalposts standing in the open cut-away (tries 1-2, plus a fill-level jump and a dropped pipe). A short, visible-only
  prompt ("four knee-high stubs on the soil top, one pipe lying flat joining them") fixed that, but the header was then
  joined to the leachate riser, because both end at the right rim → describe only what shows above ground, and never
  send two different systems (gas, leachate) to the same corner: give each its own side of the pit.
- Landfill L08 (3 tries on kie.ai, $0.27): every try drew the engine building and new poles, but never wires between
  them, even when asked for "a thick black cable from the wall to a pole right against the building" → power wires are
  too thin to draw or see at this scale; show electricity with something big (a row of poles from the building to the
  houses, or a transformer box) and don't make a still pass or fail on wires.
- Landfill L08b (3 tries on kie.ai, $0.27): raising the fill from half to the rim in one edit failed. kie.ai kept L08's
  fill level (tries 2-3) or dropped the gas header (try 1); each added fix sentence made it drift further (try 3 lost the
  gravel, drain pipe and clay, and grew a stray pipe) → a big change in fill level is the still's ONE change: lead the
  prompt with it, keep the rest to "everything else exactly as in L08", and don't stack fix sentences. If it still
  won't move, split it into two stills (three-quarters full, then full).
- Check every still before making the next (a bad still poisons every frame built on it).

## Clips (where the money goes)
- Elevator v2 ($20+, still not right): clips with two or three actions jumped and dropped
  objects → ONE change per clip; split a line into two clips with a cue word. [lint: long motion]
- Elevator v2: big camera moves made the model cut → camera moves at most about 2x, then back
  to the master view. [lint: zoom ratio, move type]
- Landfill C13/C04/C06: a clip that builds something new had no end still, so the model would
  decide where it ends and every later clip inherits it → every clip that changes what is built
  ends on a keyframe ('to'). Short events (rain, wind, a flicker) don't need one. [lint: no end keyframe]
- Viewer's rule (landfill): more stills cost less than a failed video → every clip ends on a
  reviewed still unless it is a `hold`; the hook/problem clips (C02, C03) got their own stills. [lint]
- Drain test: Seedance failed twice with no reason saved → keep the failure reason
  (`error.json`), first and last frames the same size (done automatically).
- Landfill bulldozer test ($0.93): Kling skipped the crushing step and turned white gulls into dark
  birds; Seedance 2.5 showed both steps → Seedance for clips where a machine does a multi-step job
  (C08, C11), Kling for the rest. Both models popped the bulldozer in from nowhere → a machine must
  be in the start still (parked at the rim) or the motion says where it drives in from; once it
  arrives it stays parked in later stills until a time-lapse clip removes it.
- The test ran Seedance at 480p, so the paid test clip couldn't be used in the 720p video → run
  hard-shot tests at the video's resolution; the winning clip then IS the real clip (copy
  `compare/<model>/<clip>.mp4` to `clips/<clip>.mp4`) and nothing is paid twice.
- Any clip: the action must start on its cue word, and the thing named must be on screen when
  the word is spoken ("say it, see it").

## Money
- Elevator v1 ($15) and v2 ($20+): money spent before the story was right → free draft first,
  then 2 clips at a time with the estimate approved each time. Never skip.
- Planning prices were 480p rates; 720p is double → `clips estimate` is the only real number.
- Hard shots: test the cheap model against Seedance on ONE clip (~$1) before deciding, never
  switch a whole video to an expensive model.
- After each video, run `python3 -m cutaway ledger <slug>` and add a lesson for
  every item that was paid for more than once.
