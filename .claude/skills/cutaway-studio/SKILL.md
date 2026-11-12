---
name: cutaway-studio
description: Make a 75-85 second vertical "how it works" 3D engineering cutaway video (the "If you… But… So…" format) end to end - proven topic, script, ElevenLabs voice with word timings, free Google Flow keyframes, Higgsfield start-to-end-frame clips, auto-assembled MP4 with one-word captions, posting pack. Use when the viewer asks to make, continue or test a cutaway video, or says "next video".
---

# Cutaway Studio

The tool lives in `cutaway-studio/` in this repo. Run every command from that folder:
`python3 -m cutaway <command> <slug>`. Each video is `cutaway-studio/projects/<slug>/video.json`.
Start every session with `python3 -m cutaway status <slug>`: it says where the video is up to.

## Four approvals: never skip them
1. **Script**: the viewer approves the script (after `lint` passes and facts are checked).
2. **Voice**: the viewer listens to `audio/voice.mp3` once on a phone and approves it.
3. **Frames**: the viewer approves the keyframes (contact sheet) before any clip is paid for.
4. **Spend**: before any paid call, show the exact estimate and wait for "yes". Then pass that
   amount with `--approve-usd`. The tool refuses without it and refuses anything over the
   video's `budget.cap_usd`. Never raise the cap without the viewer saying so.

Keep checkpoint messages short (the viewer is often on their phone): decision first, then
"Reply **approve** or tell me what to change".

## Keys (one-time)
Keys live in environment variables or `~/.cutaway/keys.env` (`HF_KEY=keyid:secret` or `HF_API_KEY_ID` + `HF_API_KEY_SECRET`,
`ELEVENLABS_API_KEY`, optional `GEMINI_API_KEY`). Never ask for a key in chat and never print one.
In a cloud session, use the credential form (request_credential) for api.higgsfield.ai and
api.elevenlabs.io instead.

## Step 1: Topic
Pick from topics proven in this exact format (2026 research in cutaway-studio/README.md): landfill,
elevator brake, skyscraper water, bunker under a house, car vending tower, tunnel under a river,
runaway truck ramp, buried tunnel-boring machines. Prefer real hidden systems people see every day,
water-related first. Avoid pure fantasy escalation ("my house becomes a castle"): those flopped.
Audience is US/UK (Creator Rewards pays most there): no region-only words.

## Step 2: Script (approval 1)
Write `video.json` (copy `projects/elevator/video.json` as the template). The formula:
- Line 1: **"If you [one crude physical action], you have a [thing]."** Words a 10-year-old knows.
- First **"But"** within 16 words (~3.5 s), with an everyday trigger ("as soon as it rains",
  "by morning") and a problem you can picture, ideally about YOU ("you drop five floors").
- 6-8 **But → So** pairs. Each fix causes the next problem. Each problem is vivid or funny.
- **Every part is built by a "So" line before any line uses it** (list them in `parts`).
- Name real parts: "This is a counterweight." / "These are buffers."
- One or two **everyday reveals**: "That's why…", "And that beep…? The elevator is weighing you."
- End: **"Congratulations! You've built a [thing] that…"** then a share line.
- 290-315 words (~78-85 s at their speed; over 60 s for Creator Rewards). Short sentences.
Then `python3 -m cutaway lint <slug>` must show no ERROR. Fact-check every claim with sources and
show the viewer a table of claims (true / simplified). Present the script, wait for approval.

## Step 3: Voice (approval 2)
`python3 -m cutaway voices` to list voices (first video: offer 3 clear, fast, friendly voices).
`python3 -m cutaway voice <slug> --voice-id <id>` makes `audio/voice.mp3` plus exact word timings.
Target 220-245 wpm (the tool prints it); adjust `voice.speed` (0.7-1.2) rather than rewriting.
Ask the viewer to listen once and approve. Redo only if they flag something.

## Step 4: Keyframes in Google Flow (free) (approval 3)
`python3 -m cutaway frames prompts <slug>` prints each frame's prompt and the reference files.
- Make frames **in order**. F01 has no references; each later frame attaches the files listed
  (previous frame + F01 as the anchor). Check each frame before making the next: a bad frame
  poisons everything built on it.
- Flow MCP: `flow_generate` with `project: "<slug>-frames"`, `type: "image"`,
  `model: "Nano Banana Pro"` (or "Nano Banana 2" if Pro is unavailable), `aspect_ratio: "9:16"`,
  the printed prompt, and `reference_images` = the printed file paths (max 3). **One Flow job at a
  time.** Fetch finished images with `flow_download` (never regenerate because a download failed).
- Then `python3 -m cutaway frames import <slug> <FRAME_ID> <downloaded file>` (counts the free use).
- Free allowance is a daily limit (~20, learned automatically). If Flow says the limit is reached,
  run `python3 -m cutaway quota limit-hit` and ask: "Wait until tomorrow (free) or make the rest
  with Gemini (~$0.15 each)?" Paid route: `frames gemini <slug> <ID> --approve-usd 0.15`.
- Schedule: make the next video's frames a day ahead so the daily limit never blocks a post.
- Show the viewer one contact sheet of all frames; wait for approval.
- If Flow refuses a frame on policy grounds, soften the picture (never the facts) and retry twice.

## Step 5: Free draft
`python3 -m cutaway assemble <slug> --draft` builds the whole video from stills with slow push-ins,
the real voice and one-word captions. Watch it for timing and "say it, see it": the thing named
must be on screen when its word is spoken. Fix frames or clip line-grouping now, while it's free.

## Step 6: Clips on Higgsfield (approval 4: spend)
`python3 -m cutaway timing <slug>` shows each clip's length and a planning cost.
**First video only - model test:** run just one join clip (e.g. `--only C03`) on `wan3`, `seedance2`
and `kling-o3`, show the three side by side, let the viewer pick; set `video.model` in video.json.
Then: `python3 -m cutaway clips estimate <slug>` → tell the viewer the TOTAL → on "yes":
`python3 -m cutaway clips run <slug> --approve-usd <TOTAL>`.
- Re-running is safe: finished clips are skipped and idempotency keys stop double charges.
- Failed/NSFW clips are not charged; soften that clip's motion text and re-run `--only <ID>`.
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
