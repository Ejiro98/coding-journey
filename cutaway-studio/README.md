# Cutaway Studio

Turns a script into a finished 1080x1920 "how it works" engineering cutaway video, the
"If you… But… So… Congratulations!" format behind accounts like Hidden By Design.

```
script (Claude) ──► voice + word timings (ElevenLabs)
                ──► keyframes, each = previous + one change (Google Flow, free; Gemini fallback)
                ──► clips joining frame to frame (Higgsfield API, pay per second)
                ──► MP4 with one-word captions, voice, sound effects (ffmpeg)
```

Claude runs it through the `cutaway-studio` skill (`.claude/skills/cutaway-studio/SKILL.md`) with
four approvals per video: script, voice, frames, spend.

## Setup (once, on the Mac)
1. Python 3.9+ (the Mac's built-in python3 is fine) and ffmpeg (`brew install ffmpeg`). No other packages are needed.
2. Keys in `~/.cutaway/keys.env` (never in this repo):
   ```
   HF_KEY=keyid:secret       # Higgsfield: the whole value, two parts joined by a colon
   ELEVENLABS_API_KEY=...
   KIE_API_KEY=...           # optional, cheapest paid fallback for keyframes (~$0.09)
   GEMINI_API_KEY=...        # optional, second paid fallback for keyframes
   ```
   (`HF_API_KEY_ID=...` + `HF_API_KEY_SECRET=...` on two lines also works.)
3. Google Flow MCP connected in Claude (the same one Story Studio uses) for free keyframes.
4. Check: `cd cutaway-studio && python3 -m unittest discover -s tests` (offline, costs nothing),
   then `python3 -m cutaway check` (confirms ffmpeg and that every key is accepted; spends nothing).

## Commands
| Command | What it does | Costs |
|---|---|---|
| `python3 -m cutaway status <slug>` | Where the video is up to, spend, Flow allowance | free |
| `python3 -m cutaway lint <slug>` | Checks the script against the formula | free |
| `python3 -m cutaway voices` | Lists ElevenLabs voices | free |
| `python3 -m cutaway voice <slug> --voice-id ID` | Voiceover + exact word timings | ElevenLabs characters |
| `python3 -m cutaway timing <slug>` | Clip lengths from the voice + planning cost | free |
| `python3 -m cutaway frames prompts <slug>` | Prompts and reference files for Flow | free |
| `python3 -m cutaway frames import <slug> F01 file.png` | Adds a Flow image to the project | free (counts toward the daily limit) |
| `python3 -m cutaway frames kie <slug> F05 --approve-usd 0.09` | Paid fallback frame (Nano Banana Pro on kie.ai) | ~$0.09 |
| `python3 -m cutaway frames gemini <slug> F05 --approve-usd 0.15` | Second paid fallback frame | ~$0.15 (check pricing) |
| `python3 -m cutaway assemble <slug> --draft` | Whole video from stills (preview) | free |
| `python3 -m cutaway clips estimate <slug>` | Exact Higgsfield cost for the remaining clips | free |
| `python3 -m cutaway clips estimate <slug> --next 2` | Cost of just the next 2 clips | free |
| `python3 -m cutaway clips run <slug> --next 2 --approve-usd X` | Makes the next 2 clips, in order (refuses above X or the cap) | Higgsfield balance |
| `python3 -m cutaway assemble <slug>` | Final MP4 | free |
| `python3 -m cutaway quota [add N / limit-hit]` | Flow free-image counter | free |

## Video models (start + end frame), Higgsfield API, Nov 2026
| `--model` | Endpoint | Length | 480p | 720p |
|---|---|---|---|---|
| `kling-o3` | kling-video/o3/first-last-frame | 3-15 s | n/a | $0.068/s |
| `wan3` (default) | alibaba/wan-3.0/image-to-video | 2-30 s | $0.0375/s | $0.075/s |
| `seedance2` | bytedance/seedance-2.0/image-to-video | 4-15 s | $0.080/s | $0.174/s |
| `seedance25` | bytedance/seedance-2.5/image-to-video | 4-30 s | $0.118/s | $0.265/s |

A ~70 s video at 720p: ~$5 (Kling O3 / Wan 3.0), ~$12 (Seedance 2.0), ~$19 (Seedance 2.5).
`compare <slug>` tests all four at 480p on two clips for ~$2.40 before committing to one.
Higgsfield's `/estimate` now answers with a text price list; the client reads the rate for the
request's resolution and refuses to guess if it can't.

The `/estimate` endpoint is always used for the real number before anything is paid for.

## Money safety
- Paid commands need `--approve-usd` and stop if the estimate is higher or the video's
  `budget.cap_usd` ($7 per video including retries) would be passed. Clips are made two at a
  time after the free draft is approved, so a rejected clip never wastes the ones after it. Every estimate and spend is logged in
  `projects/<slug>/ledger.jsonl`.
- Re-running is safe: finished clips are skipped; idempotency keys prevent double charges.
- Failed and NSFW generations are not charged by Higgsfield.

## The formula (from 9 viral videos and both pages' stats)
- **Hook**: "If you [crude first build], you have a [thing]." First "But" within ~3.5 s. Their two
  biggest hits (9.7M, 3.8M) hit the first problem at 3.1 s and 3.5 s; the slowest flop at 16.7 s.
- **Chain**: 6-8 But/So pairs; each fix causes the next problem; every part is built before use.
- **Names + reveal**: "This is a flap gate." / "That's why the handle clicks when your tank is full."
- **Ending**: "Congratulations! You've built…" + share line. 290-315 words, ~75-85 s.
- **Visuals**: realistic 3D cutaway, one continuous build, "say it, see it": the thing named is on
  screen when its word is spoken; one-word captions.

Proven topics (outlier research, Aug-Nov 2026): landfill (6.2M + 3.5M), elevator brake (5M),
skyscraper water (959K at 1,700x the account's median), bunker under the house (4.6M), car vending
tower (1.3M + 414K), tunnel under a river or sea (5 separate hits), runaway truck ramp (4.8M),
buried tunnel-boring machines (2.1M + 1.3M).
