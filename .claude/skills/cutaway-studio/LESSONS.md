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
