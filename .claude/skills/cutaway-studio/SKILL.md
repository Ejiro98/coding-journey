---
name: cutaway-studio
description: Make a 75-85 second vertical "how it works" 3D engineering cutaway video (the "If you… But… So…" format) end to end - proven topic, script, ElevenLabs voice with word timings, free Google Flow keyframes, Higgsfield start-to-end-frame clips, auto-assembled MP4 with one-word captions, posting pack. Use when the viewer asks to make, continue or test a cutaway video, or says "next video".
---

# Cutaway Studio

The tool lives in `cutaway-studio/` in this repo. Run every command from that folder:
`python3 -m cutaway <command> <slug>`. Each video is `cutaway-studio/projects/<slug>/video.json`.
Start every session with `python3 -m cutaway status <slug>`: it says where the video is up to.

**Read `LESSONS.md` (next to this file) before writing a script or a shot plan.** Check the plan
against every lesson and tell the viewer which ones you checked. Whenever a still is remade, a clip
is paid for twice, or the viewer points out a mistake, add a lesson there (what happened, cost, the
rule that prevents it) and commit it, so the next video doesn't repeat it.

## Five approvals: never skip them
1. **Script**: the viewer approves the script (after `lint` passes and facts are checked).
2. **Voice**: the viewer listens to `audio/voice.mp3` once on a phone and approves it.
3. **Frames**: the viewer approves the keyframes (contact sheet) before any clip is paid for.
4. **Free draft**: the viewer watches the FREE draft (stills + real voice + captions) and approves
   the story, timing and pictures. **No money is spent on clips before this.**
5. **Spend, in small steps**: clips are made 2 at a time (`--next 2`), checked, then continued.
   Before each step show the exact estimate and wait for "yes"; pass it with `--approve-usd`.
   The tool refuses without it and refuses anything over the video's `budget.cap_usd`
   (default $7: the viewer's limit per video INCLUDING retries). Never raise the cap without
   the viewer saying so.

Keep checkpoint messages short (the viewer is often on their phone): decision first, then
"Reply **approve** or tell me what to change".

## Keys (one-time)
Keys live in environment variables or `~/.cutaway/keys.env` (`HF_KEY=keyid:secret` or `HF_API_KEY_ID` + `HF_API_KEY_SECRET`,
`ELEVENLABS_API_KEY`, optional `KIE_API_KEY` and `GEMINI_API_KEY`). Never ask for a key in chat and never print one.
In a cloud session, use the credential form (request_credential) for api.higgsfield.ai and
api.elevenlabs.io instead.

## Step 1: Topic
Pick from topics proven in this exact format (2026 research in cutaway-studio/README.md): landfill,
elevator brake, skyscraper water, bunker under a house, car vending tower, tunnel under a river,
runaway truck ramp, buried tunnel-boring machines. Prefer real hidden systems people see every day,
water-related first. Avoid pure fantasy escalation ("my house becomes a castle"): those flopped.
Audience is US/UK (Creator Rewards pays most there): no region-only words.

## Step 2: Script (approval 1)
Write `video.json` (copy `projects/landfill/video.json` as the template). **Narrate like the
proven videos, not a new style** (read `cutaway-studio/README.md` and the transcripts first). The formula:
- Line 1: **"If you [one crude physical action], you have a [thing]."** Words a 10-year-old knows.
- First **"But"** within 16 words (~3.5 s), with an everyday trigger ("as soon as it rains",
  "by morning") and a problem you can picture, ideally about YOU ("you drop five floors").
- 6-8 **But → So** pairs. Each fix causes the next problem. Problems come from **real forces**
  (rain, gravity, wind, weight, people) and their real consequences, never cartoon events.
- **"Now…" result lines** after key fixes, exactly like the proven scripts ("Now the water moves.",
  "Now the rain runs around the chimney.", "Now it can only move straight up and down."): the
  viewer must SEE each fix working before the next problem.
- Humour only from vivid true consequences ("your street becomes a swimming pool", "your drain
  becomes a fountain"), never invented gags (glowing motors, meters spinning, people falling over).
- **Every part is built by a "So" line before any line uses it** (list them in `parts`).
- Name real parts: "This is a counterweight." / "These are buffers."
- One or two **everyday reveals**: "That's why…", "And that beep…? The elevator is weighing you."
- End: run the whole system once ("Bury the pipes, pave the road, and let it rain." / "Now press
  the button…"), then **"Congratulations! You've built a [thing] that…"** and a share line.
- **Facts must survive a check**: every claim is physically true or a fair simplification; prefer
  the real mechanism (a drum or a counterweight is needed before a grooved wheel can lift anything).
- **250-300 words** (their videos: 235-327, newest 235-287). After the voice, the video must be
  over 60 s for Creator Rewards: if it's under 61 s, lower `voice.speed` (e.g. 1.0) and remake it.
- Fixes can start "So you…" or with a plain verb like theirs ("Give it a slight slope", "Add a
  pumping station", "Build a footing"). Name parts: "This is a cofferdam." / "That's a dune."
- Two proven story shapes: **build in place** (drainage, roof, bridge, beach, landfill: one master
  view, layers added) or **follow the flow** (sewer, power grid: the camera travels with the water
  or power). Pick the one that fits the topic.
- **Every problem has a visible cause first** (the box can't swing until we've said nothing holds it
  steady). **Every mechanism with two ends shows both ends** (the governor rope is a loop between a
  top wheel and a bottom wheel, not a rope to nowhere).
Then `python3 -m cutaway lint <slug>` must show no ERROR. Fact-check every claim with sources and
show the viewer a table of claims (true / simplified). Present the script, wait for approval.

## Shot plan rules (measured from 7 Hidden By Design videos + the viewer's elevator notes)
- **Stills are cheap, clips are expensive, failed videos are the most expensive. When in doubt, add a
  still.** (A still is free on Flow or ~$0.09 on kie.ai; a 4 s clip is ~$0.27 on Kling, ~$1 on
  Seedance; a failed video is $5+.) Every clip starts on a reviewed still and ENDS on a reviewed still
  (`to`), so the model only fills in the motion between two pictures that are already right.
  The only exception is a `"hold": true` clip where nothing new stays on screen afterwards (wind,
  rain running off, a flicker, people walking); `lint` warns about any other clip without `to`.
  The hook and the problem lines (the first ~8 s) always get their own stills. More stills also make
  the free draft look like the final video, so problems show up while they're still free to fix.
- **Beats of ~3-4 s, ONE change per clip** (~18-20 clips per video). One line ≈ one clip; split a
  long line with a cue word. Motion text: one short sentence or two.
- **Camera locked for most clips** on a "master" view. Give every frame a `view` name and a `zoom`
  (master = 1). A clip that changes view needs a `move` (dolly-in, pull-back, pan, follow) and at
  most ~2x zoom; bigger jumps make the model cut. Return to the master view after a close look.
- `lint` checks all of this (shot checks) and blocks oversized moves.
- **A moved frame keeps the same objects in the same orientation**: say "the same pipe, still
  running left to right, camera twice as close", never "look along the pipe" (image models then
  turn the object to face the camera, as happened in the drainage test).
- **Physics check on every keyframe: where does everything end up?** Water must drain somewhere
  real (a channel, a river, a tank), pipes must connect at both ends, loads must rest on something.
  A pipe ending in the middle of the soil fails the frame.
- **Setting, never white space**: the `style` puts the cutaway in a real place (street, neighbouring
  buildings, trees, cars, residents inside). Keep it identical in every wide frame.
- **Parts can't appear early**: give every frame a `state` (the line whose result it shows) and every
  part a `looks` description; the prompt then lists everything NOT BUILT YET as "do not draw".
  Mark wide frames `"wide": true` so built parts are listed as must-be-visible.
- **One continuous scene, like the proven videos**: everything happens in the same cutaway; the
  camera only glides, pushes in or pulls back (no cuts to separate rooms). `video.chain` is on,
  so each clip starts from the previous clip's last frame; `"cut": true` is a last resort.
  Use `to` keyframes to anchor each build step's end state.
- **Physically possible only**: nothing rewinds, teleports, glows or appears from nowhere; parts
  are lowered, slid or bolted in. If the story breaks the machine (ropes snap), put that test LAST
  so nothing has to be magically repaired. Put "only physically possible events" in `rules`.
- **Action on the word**: give problem clips a `cue` word ("snaps", "swings") so the cut and the
  action land on that word, and the prompt says the action starts immediately. Don't use a cue if
  it leaves the clip under ~2 s (check `timing`).
- **Physics rules every clip must obey** go in `rules` (e.g. the counterweight always moves
  opposite to the box at the same speed; built parts never disappear; the street stays the same).
- **Show the fix WORKING**: after a part is built, show the result (the box gliding straight on the
  rails; the box actually stopped and hanging safely). Small mechanisms get wide → close-up → wide.
- **People are alive**: describe continuous action ("keeps walking steadily, eyes on his phone"),
  a reaction, and a payoff. Never a person just standing in frame.
- **The ending shows the whole system working** (a button press, the box rising while the
  counterweight sinks), in the same camera angle as the build.

## Step 3: Voice (approval 2)
`python3 -m cutaway voices` to list voices (first video: offer 3 clear, fast, friendly voices).
`python3 -m cutaway voice <slug> --voice-id <id>` makes `audio/voice.mp3` plus exact word timings.
Target 220-245 wpm (the tool prints it); adjust `voice.speed` (0.7-1.2) rather than rewriting.
Ask the viewer to listen once and approve. Redo only if they flag something.

## Step 4: Keyframes in Google Flow (free) (approval 3)
`python3 -m cutaway frames prompts <slug>` prints each frame's prompt and the reference files.
- **Big changes** (a pit filling up, a mound appearing): set `"big_change": true` on that still, lead its
  `shows` with the change in one sentence, and keep extras out. Otherwise the usual "keep everything
  identical" prompt makes the model refuse the change.
- **The first still sets the shape every later still must copy, so keep it simple:** one clean
  box-shaped space with straight edges and a clear cut face, few vehicles, nothing that isn't in the
  story. Awkward steps and corners in it cause failed tries for the rest of the video.
- Make frames **in order**. F01 has no references; each later frame attaches the files listed
  (previous frame + F01 as the anchor). Check each frame before making the next: a bad frame
  poisons everything built on it.
- Flow MCP: `flow_generate` with `project: "<slug>-frames"`, `type: "image"`,
  `model: "Nano Banana Pro"` (or "Nano Banana 2" if Pro is unavailable), `aspect_ratio: "9:16"`,
  the printed prompt, and `reference_images` = the printed file paths (max 3). **One Flow job at a
  time.** Fetch finished images with `flow_download` (never regenerate because a download failed).
- Then `python3 -m cutaway frames import <slug> <FRAME_ID> <downloaded file>` (counts the free use).
- Free allowance is a daily limit (~20, learned automatically). If Flow says the limit is reached,
  run `python3 -m cutaway quota limit-hit` and ask: "Wait until tomorrow (free), or make the
  remaining N frames on kie.ai for about $0.09 each (~$X total)?" Paid routes, cheapest first:
  1. `frames kie <slug> <ID> --approve-usd 0.09` (Nano Banana Pro on kie.ai; logs the real charge)
  2. `frames gemini <slug> <ID> --approve-usd 0.15` (only if kie.ai is down or out of credits)
  Paid frames count toward the video's $7 cap, so say the running total.
- Schedule: make the next video's frames a day ahead so the daily limit never blocks a post.
- **Every still is reviewed by a separate reviewer before it is used. Never mark your own work.**
  The maker wants the still to pass, so it explains faults away ("a little fuller than half").
  After each still is generated:
  0. Before making a still, read its questions: each must be answerable from this picture (nothing
     buried, nothing that belongs to another still; use `line_part` when the still shows only part of
     its line). Fix a bad question first: it will fail every try and push the remakes the wrong way.
  1. `python3 -m cutaway frames check <slug> <ID>` prints that still's yes/no questions (its line,
     its own `checks`, every part that must be there or must not, continuity, sharpness).
  2. Start a NEW subagent (Agent tool) as the reviewer. Give it ONLY: the image path, the paths of
     the reference stills, and the questions. Tell it: "Open the images at full size and crop/zoom
     into each area you judge. Answer every question with PASS or FAIL plus what you actually
     see. Judge \"does it show…\" questions as a viewer on a phone would see the picture at normal
     size; zoom in for counts, connections and MUST-BE-NO questions, where any doubt is FAIL. You
     did not make this image and nothing depends on it passing."
     Don't tell it what you hoped the image shows.
  3. All PASS → `frames import <slug> <ID> <file> --reviewed` (the tool refuses without
     `--reviewed`). Any FAIL → remake with the FAILED answers added to the prompt as plain
     instructions. Paid stills (kie/gemini) are saved straight away; review them the same way.
  4. Three failed tries on one still → stop. First ask: is the QUESTION the problem? Image models
     can't draw degrees ("soaked", "slightly", "half") or fine detail reliably; rewrite such a
     question as something visible ("black liquid collected at the bottom", "liner wall showing all round").
     If a try already passes every question a viewer would care about, show it to the viewer as the
     candidate. Add a lesson, and show the viewer the tries with the failed answers.
  Don't wait for the viewer between stills: they approve the contact sheet once, at the end,
  with the reviewer's answers for each still.
- Show the viewer one contact sheet of all frames; wait for approval.
- If Flow refuses a frame on policy grounds, soften the picture (never the facts) and retry twice.

## Step 5: Free draft (approval 4) - nothing is paid for before this is approved
`python3 -m cutaway assemble <slug> --draft` builds the whole video from the keyframes with slow
push-ins, the real voice and one-word captions. Before showing the viewer, check it yourself:
"say it, see it" (the thing named is on screen when its word is spoken), every keyframe obeys its
NOT BUILT YET list, the setting is a real place, the counterweight is always opposite the box.
Then send it and ask: **"Reply approve, or tell me what to change. No money has been spent yet."**
Fix frames, motion text or line grouping now, while it's free.

## Step 6: Clips on Higgsfield (approval 5: spend, two clips at a time)
`python3 -m cutaway timing <slug>` shows each clip's length and a planning cost.
**Model test before the first full video on a model, and whenever trying a new one:**
`python3 -m cutaway compare <slug> --estimate` (default: wan3, kling-o3, seedance2, seedance25 at
480p, ~$2.40 for 2 clips each; motion is what's tested, 480p is half price) → tell the viewer
the total → on "yes": `... --approve-usd <TOTAL>`. It makes the first two clips (one locked-camera
change, one camera move) on each model, each with its own chain, and joins them into
`compare/side_by_side.mp4`. The viewer picks; set `video.model`. `projects/drain-test` recreates
two beats of their drainage video for exactly this purpose (never post it).
**Default model: Kling O3** (won the drainage test with Wan 3.0: both did a locked change and a 2x
camera move with no cuts; Kling is the cheapest at 720p). **Hard shots** (several objects doing a
physical action, e.g. a bulldozer crushing and covering trash): a clip can set `"model":
"seedance25"` (and optionally `"resolution"`) to override the video's model. Only do that after the
project's hard-shot test, run at the video's resolution (`--resolution 720p`) so the winning clip can go straight into the video (see `tests` in video.json, e.g. `compare landfill --models
kling-o3,seedance25 --clips C08`) shows Seedance is clearly better, and only for 2-3 clips.
Real 720p prices (Higgsfield, Nov 2026, per output second): Kling O3 std $0.068, Wan 3.0 $0.075,
Seedance 2.0 $0.174, Seedance 2.5 $0.265. A ~70 s video costs ~$5 on Kling O3 or Wan 3.0, ~$12
on Seedance 2.0 and ~$19 on Seedance 2.5. Under the $7 cap only Kling O3 or Wan 3.0 fit, so
Seedance needs the viewer to raise the cap first. `timing` prices at the project's resolution and
at the rate actually charged; `clips estimate` is always the real number.
Then repeat until all clips are made:
1. `python3 -m cutaway clips estimate <slug> --next 2` → tell the viewer the amount → on "yes":
2. `python3 -m cutaway clips run <slug> --next 2 --approve-usd <AMOUNT>`
3. **Check both clips yourself before continuing** (last frame + a few frames each): the action
   happens on its cue word; it continues smoothly from the previous clip; physics rules hold
   (counterweight opposite the box, nothing impossible); people move; nothing built disappears;
   no part from the NOT BUILT YET list appears. Show the viewer the two clips.
4. If a clip fails the check: delete `clips/<ID>.mp4`, make its `motion` text more specific, and
   re-run step 1. Because the next clips aren't made yet, only that clip is paid for again.
   Add a lesson to `LESSONS.md` for every remade clip (what went wrong, what it cost, the fix).
- Keep a running total against the $7 cap and say it in every checkpoint ("$2.10 of $7 used").
- Re-running is safe: finished, up-to-date clips are skipped and idempotency keys stop double charges.
- Failed/NSFW clips are not charged; make that clip's motion text gentler and re-run.
- Files on Higgsfield are deleted after 7 days; the tool downloads immediately.

## Step 7: Final video
`python3 -m cutaway assemble <slug>` → `final/<slug>.mp4` (1080x1920). Watch it muted (pictures
alone must make sense) and listen eyes-closed (words alone must make sense). Optional sound
effects: add `{"file": "sfx/snap.wav", "line": "2", "word": "snaps", "gain_db": -8}` entries to
`sfx` in video.json (files inside the project folder) and re-assemble; music: `"music": {"file": …,
"gain_db": -18}`.

## Step 8: Posting pack
Caption = the question from video.json (`caption`), 3-5 hashtags (no #fyp/#viral), cover = the
first frame (the hook visual), TikTok AI-generated label ON, post as a Reel on Instagram too and
crosspost to Facebook. Don't delete a slow starter. Plan a Part 2 if it takes off.

## Rules that save money
- Never spend without the viewer's "yes" in this conversation; use the exact estimate.
- Never edit costs, the ledger or the cap to get past the guard.
- If a step fails, resume from that step; approved work is kept.
- Run the tests after changing the tool: `python3 -m unittest discover -s tests`.
