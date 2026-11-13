"""Offline tests: no real API is called and nothing is paid for.

Run from the cutaway-studio folder:  python3 -m unittest discover -s tests -v
"""

import base64
import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

STUDIO = Path(__file__).resolve().parent.parent
os.environ["CUTAWAY_HOME"] = tempfile.mkdtemp(prefix="cutaway-home-")

from cutaway import (assemble, clips, elevenlabs, frames, higgsfield as hf, http,  # noqa: E402
                     ledger, lint, quota, timing)
from cutaway.project import Project, ProjectError, validate  # noqa: E402

ELEVATOR = json.loads((STUDIO / "projects" / "elevator" / "video.json").read_text())
HAS_FFMPEG = shutil.which("ffmpeg") is not None


def make_project(data=None):
    root = Path(tempfile.mkdtemp(prefix="cutaway-proj-"))
    p = Project("t", root=root)
    d = copy.deepcopy(data or ELEVATOR)
    d["slug"] = "t"
    p.save(d)
    return p, d


class LintTests(unittest.TestCase):
    def test_elevator_script_passes(self):
        report = lint.check(ELEVATOR)
        self.assertFalse(lint.has_errors(report), lint.format_report(report))

    def test_part_used_before_built_is_an_error(self):
        d = copy.deepcopy(ELEVATOR)
        # The original draft-1 mistake: the motor appears before anything builds it.
        d["lines"][3]["text"] = "But now the motor has to lift the whole box on every trip."
        report = lint.check(d)
        self.assertTrue(lint.has_errors(report))
        self.assertIn("before it is built", lint.format_report(report))

    def test_slow_hook_and_story_opening_are_errors(self):
        d = copy.deepcopy(ELEVATOR)
        d["lines"][0]["text"] = ("Someone keeps stealing parcels from the doorstep of a very old building "
                                 "every single morning before work, so the owner buys an elevator.")
        report = lint.format_report(lint.check(d))
        self.assertIn("must open with 'If you", report)
        self.assertIn("First 'But' comes after", report)

    def test_regional_word_warning(self):
        d = copy.deepcopy(ELEVATOR)
        d["lines"][2]["text"] = "So pour tarmac over it and take the lift instead."
        report = lint.format_report(lint.check(d))
        self.assertIn("tarmac", report)
        self.assertIn("the lift", report)


class ProjectTests(unittest.TestCase):
    def test_clips_must_cover_lines_in_order(self):
        d = copy.deepcopy(ELEVATOR)
        d["clips"][0]["lines"] = ["2"]
        with self.assertRaises(ProjectError):
            validate(d)

    def test_unknown_frame_reference(self):
        d = copy.deepcopy(ELEVATOR)
        d["clips"][0]["from"] = "F99"
        with self.assertRaises(ProjectError):
            validate(d)


class BudgetTests(unittest.TestCase):
    def test_guard_needs_approval_and_respects_cap(self):
        p, d = make_project()
        with self.assertRaises(ledger.BudgetError):
            ledger.guard(p, d, 3.0, None)                 # no approval
        with self.assertRaises(ledger.BudgetError):
            ledger.guard(p, d, 3.0, 2.0)                  # estimate above approval
        self.assertTrue(ledger.guard(p, d, 3.0, 3.0))
        ledger.append(p, "spend", "higgsfield", "C01", 11.0)
        with self.assertRaises(ledger.BudgetError):
            ledger.guard(p, d, 3.0, 5.0)                  # would pass the $12 cap
        self.assertEqual(ledger.spent(p), 11.0)


class QuotaTests(unittest.TestCase):
    def test_counter_learns_real_limit(self):
        start = quota.status()["used"]
        quota.add(3)
        self.assertEqual(quota.status()["used"], start + 3)
        quota.limit_hit()
        self.assertEqual(quota.status()["limit"], start + 3)
        self.assertEqual(quota.status()["left"], 0)


class TimingTests(unittest.TestCase):
    def test_alignment_to_words(self):
        text = "If you pull"
        align = {"characters": list(text),
                 "character_start_times_seconds": [i * 0.1 for i in range(len(text))],
                 "character_end_times_seconds": [i * 0.1 + 0.08 for i in range(len(text))]}
        words = elevenlabs.words_from_alignment(align)
        self.assertEqual([w["w"] for w in words], ["If", "you", "pull"])
        self.assertAlmostEqual(words[1]["s"], 0.3)
        self.assertAlmostEqual(words[2]["e"], 1.08)

    def test_segments_cover_whole_voice(self):
        words = timing.estimated_words(ELEVATOR, 230)
        segs, total = timing.segments(ELEVATOR, words, 0.8)
        self.assertEqual(len(segs), len(ELEVATOR["clips"]))
        self.assertEqual(segs[0]["start"], 0.0)
        self.assertAlmostEqual(segs[-1]["end"], total)
        for a, b in zip(segs, segs[1:]):
            self.assertAlmostEqual(a["end"], b["start"])
        self.assertTrue(70 < total < 95, total)


def _tiny_mp4(color):
    out = Path(tempfile.mkdtemp()) / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=96x160:r=10:d=1",
                    "-pix_fmt", "yuv420p", str(out)], check=True)
    return out.read_bytes()


class FakeHiggsfield:
    """Stands in for the HTTP transport and records every call.
    Each generated clip is a real tiny video of a different colour, so chaining
    (start = previous clip's last frame) can be checked."""

    COLORS = ["red", "green", "blue", "yellow", "white", "purple"]

    def __init__(self, final_status="completed"):
        self.calls = []
        self.videos = {}
        self.final_status = final_status
        self.polls = {}

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body))
        js = lambda o: (200, {}, json.dumps(o).encode())  # noqa: E731
        if url.endswith("/files/generate-upload-url"):
            n = len([c for c in self.calls if c[1].endswith("generate-upload-url")])
            return js({"public_url": f"https://cdn.test/f{n}.png", "upload_url": f"https://s3.test/put{n}",
                       "upload_headers": {"Content-Type": "image/png"}})
        if url.startswith("https://s3.test/"):
            assert "Authorization" not in headers, "credentials must not go to presigned URL"
            return 200, {}, b""
        if "/estimate/" in url:
            return js({"usd": "0.20"})
        if url.startswith("https://api.higgsfield.ai/requests/"):
            rid = url.split("/")[-2]
            self.polls[rid] = self.polls.get(rid, 0) + 1
            if self.polls[rid] < 2:
                return js({"status": "in_progress", "request_id": rid})
            out = {"status": self.final_status, "request_id": rid}
            if self.final_status == "completed":
                out["video"] = {"url": f"https://out.test/{rid}.mp4"}
            return js(out)
        if url.startswith("https://out.test/"):
            rid = url.rsplit("/", 1)[-1].split(".")[0]
            if rid not in self.videos:
                self.videos[rid] = _tiny_mp4(self.COLORS[len(self.videos) % len(self.COLORS)])
            return 200, {}, self.videos[rid]
        if method == "POST" and url.startswith("https://api.higgsfield.ai/"):
            rid = f"r{len([c for c in self.calls if c[0] == 'POST' and 'estimate' not in c[1] and 'upload' not in c[1]])}"
            return js({"status": "queued", "request_id": rid,
                       "status_url": f"https://api.higgsfield.ai/requests/{rid}/status"})
        raise AssertionError(f"unexpected call {method} {url}")


def _png(path, color="0x3366aa"):
    if HAS_FFMPEG:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=576x1024",
                        "-frames:v", "1", str(path)], check=True)
    else:
        path.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="))


class ClipRunTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHiggsfield()
        self._old = http.transport
        http.transport = self.fake

    def tearDown(self):
        http.transport = self._old

    def test_estimate_guard_submit_poll_download(self):
        p, d = make_project()
        for fid in ("F01", "F02"):
            _png(p.path("frames", f"{fid}.png"))
        client = hf.Client("id", "secret", sleep=lambda s: None)
        with self.assertRaises(ledger.BudgetError):
            clips.run(p, d, client, approve_usd=None, only="C01,C02,C03", log=lambda *_: None)
        made = clips.run(p, d, client, approve_usd=0.60, only="C01,C02,C03", log=lambda *_: None)
        self.assertEqual(made, ["C01", "C02", "C03"])
        self.assertTrue(p.clip_file("C03").stat().st_size > 100)
        self.assertAlmostEqual(ledger.spent(p), 0.60)
        subs = [c for c in self.fake.calls
                if c[0] == "POST" and c[1].endswith("image-to-video") and "/estimate/" not in c[1]]
        self.assertEqual(len(subs), 3)
        body = json.loads(subs[2][3])
        self.assertIn("end_image_url", body)                  # C03 must end on F02
        self.assertFalse(body["generate_audio"])
        self.assertEqual(body["aspect_ratio"], "9:16")
        self.assertTrue(all("Idempotency-Key" in c[2] for c in subs))
        # Chain: C02 and C03 start from the previous clip's last frame, not the keyframe.
        st = p.load_state()["clips"]
        self.assertEqual(st["C02"]["start_source"], "end of C01")
        self.assertEqual(st["C03"]["start_source"], "end of C02")
        starts = [json.loads(c[3])["image_url"] for c in subs]
        self.assertEqual(len(set(starts)), 3)
        # Re-running makes nothing new and pays nothing more.
        again = clips.run(p, d, client, approve_usd=0.60, only="C01,C02,C03", log=lambda *_: None)
        self.assertEqual(again, [])
        self.assertAlmostEqual(ledger.spent(p), 0.60)

    def test_failed_clip_gets_a_new_idempotency_key_for_the_retry(self):
        p, d = make_project()
        for fid in ("F01", "F02"):
            _png(p.path("frames", f"{fid}.png"))
        client = hf.Client("id", "secret", sleep=lambda s: None)
        self.fake.final_status = "failed"
        self.assertEqual(clips.run(p, d, client, approve_usd=0.60, only="C01", log=lambda *_: None), [])
        self.assertAlmostEqual(ledger.spent(p), 0.0)
        self.fake.final_status = "completed"
        self.assertEqual(clips.run(p, d, client, approve_usd=0.60, only="C01", log=lambda *_: None), ["C01"])
        subs = [c for c in self.fake.calls
                if c[0] == "POST" and c[1].endswith("image-to-video") and "/estimate/" not in c[1]]
        keys = [c[2]["Idempotency-Key"] for c in subs]
        self.assertEqual(len(keys), 2)
        self.assertNotEqual(keys[0], keys[1])

    def test_remaking_a_clip_marks_later_chained_clips_out_of_date(self):
        p, d = make_project()
        for fid in ("F01", "F02"):
            _png(p.path("frames", f"{fid}.png"))
        client = hf.Client("id", "secret", sleep=lambda s: None)
        clips.run(p, d, client, approve_usd=0.60, only="C01,C02,C03", log=lambda *_: None)
        p.clip_file("C01").unlink()                            # viewer rejects C01
        todo, _ = clips.plan(p, d, only="C01,C02,C03")
        self.assertEqual([(t["clip"]["id"], t["why"]) for t in todo],
                         [("C01", "new"), ("C02", "out of date"), ("C03", "out of date")])

    def test_cut_clip_starts_from_its_keyframe(self):
        p, d = make_project()
        for fid in ("F01", "F02"):
            _png(p.path("frames", f"{fid}.png"))
        d["clips"][1]["cut"] = True
        client = hf.Client("id", "secret", sleep=lambda s: None)
        clips.run(p, d, client, approve_usd=0.60, only="C01,C02,C03", log=lambda *_: None)
        self.assertEqual(p.load_state()["clips"]["C02"]["start_source"], "keyframe F01")

    def test_rules_and_cue_go_into_the_prompt(self):
        d = copy.deepcopy(ELEVATOR)
        d["rules"] = ["The counterweight always moves opposite to the box."]
        clip = dict(d["clips"][1], cue="snaps")
        text = clips.clip_prompt(d, clip)
        self.assertTrue(text.startswith("The action starts immediately"))
        self.assertIn("opposite to the box", text)

    def test_failed_clip_is_not_recorded_as_spend(self):
        self.fake.final_status = "failed"
        p, d = make_project()
        _png(p.path("frames", "F01.png"))
        made = clips.run(p, d, hf.Client("id", "s", sleep=lambda s: None), approve_usd=1.0, only="C01", log=lambda *_: None)
        self.assertEqual(made, [])
        self.assertEqual(ledger.spent(p), 0.0)

    def test_missing_frame_stops_before_anything_is_called(self):
        p, d = make_project()
        with self.assertRaises(ValueError):
            clips.run(p, d, hf.Client("id", "s", sleep=lambda s: None), approve_usd=5, only="C03", log=lambda *_: None)
        self.assertEqual(self.fake.calls, [])




class BodyTests(unittest.TestCase):
    def test_kling_uses_its_own_field_names(self):
        b = hf.clip_body("kling-o3", "https://a", "https://b", "move", 2.2)
        self.assertEqual(b["first_frame_url"], "https://a")
        self.assertEqual(b["last_frame_url"], "https://b")
        self.assertEqual(b["duration"], 3)                       # clamped to Kling's minimum
        self.assertNotIn("image_url", b)

    def test_duration_clamped_for_seedance(self):
        self.assertEqual(hf.clip_duration("seedance2", 2.4), 4)
        self.assertEqual(hf.clip_duration("seedance2", 40), 15)


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg not installed")
class AssembleTests(unittest.TestCase):
    def test_draft_and_final_render(self):
        p, d = make_project()
        # Short 3-clip version so the test is fast.
        d["lines"] = d["lines"][:3]
        d["clips"] = [{"id": "C01", "lines": ["1"], "from": "F01", "to": None, "motion": "x"},
                      {"id": "C02", "lines": ["2"], "from": "F01", "to": None, "motion": "x"},
                      {"id": "C03", "lines": ["3"], "from": "F01", "to": "F02", "motion": "x"}]
        d["settings"] = {"video_width": 360, "video_height": 640}
        p.save(d)
        _png(p.path("frames", "F01.png"))
        _png(p.path("frames", "F02.png"), "0xaa6633")
        # fake voice: a tone as long as the estimated words
        words = timing.estimated_words(d, 230)
        p.words_file().write_text(json.dumps(words))
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"sine=frequency=220:duration={words[-1]['e'] + 0.5}",
                        str(p.path("audio", "voice.mp3"))], check=True)
        # one real clip, two from stills
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=576x1024:r=24:d=5",
                        "-pix_fmt", "yuv420p", str(p.path("clips", "C02.mp4"))], check=True)
        rep = assemble.assemble(p, d)
        self.assertEqual(rep["clip"], 1)
        self.assertEqual(rep["still"], 2)
        out = Path(rep["file"])
        self.assertTrue(out.exists())
        self.assertAlmostEqual(assemble.probe_duration(out), rep["seconds"], delta=0.25)
        ass = (p.dir / "build" / "captions.ass").read_text()
        self.assertIn("Dialogue:", ass)
        self.assertIn(",IF", ass)

    def test_caption_words_are_cleaned(self):
        ass = assemble.captions_ass([{"w": "rope,", "s": 0, "e": 0.3}, {"w": "snaps?", "s": 0.3, "e": 0.6}],
                                    1080, 1920, "Arial", 96)
        self.assertIn(",ROPE\n", ass)
        self.assertIn(",SNAPS?", ass)


class FramesTests(unittest.TestCase):
    def test_plan_and_import_counts_flow_usage(self):
        p, d = make_project()
        plan = frames.plan(p, d)
        self.assertTrue(plan[0]["ready"])
        self.assertFalse(plan[1]["ready"])
        before = quota.status()["used"]
        src = Path(tempfile.mkdtemp()) / "download.png"
        _png(src)
        frames.import_frame(p, "F01", src)
        self.assertEqual(quota.status()["used"], before + 1)
        self.assertTrue(frames.plan(p, d)[1]["ready"])
        self.assertIn("Change ONLY the following", frames.plan(p, d)[1]["prompt"])


if __name__ == "__main__":
    unittest.main()


class CheckTests(unittest.TestCase):
    def test_check_reports_key_status_without_spending(self):
        from cutaway.__main__ import run_checks
        calls = []

        def fake(method, url, headers, body, timeout):
            calls.append((method, url))
            if "higgsfield" in url:
                return 404, {}, b'{"detail": "Request not found"}'
            if "elevenlabs" in url:
                return 200, {}, json.dumps({"tier": "starter", "character_limit": 30000,
                                            "character_count": 1000}).encode()
            return 200, {}, b"{}"

        old, http.transport = http.transport, fake
        env = {"HF_API_KEY_ID": "a", "HF_API_KEY_SECRET": "b", "ELEVENLABS_API_KEY": "c"}
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        out = []
        try:
            good = run_checks(log=out.append)
        finally:
            http.transport = old
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        text = "\n".join(out)
        self.assertIn("Higgsfield: key accepted", text)
        self.assertIn("29,000 characters left", text)
        self.assertTrue(all(m == "GET" for m, _ in calls))   # only free reads
        self.assertEqual(good, HAS_FFMPEG)

    def test_combined_hf_key(self):
        os.environ["HF_KEY"] = "abc123:s3cr3t:with-colon"
        try:
            self.assertEqual(hf.credentials(), ("abc123", "s3cr3t:with-colon"))
            os.environ["HF_KEY"] = "nocolonhere"
            with self.assertRaises(Exception) as ctx:
                hf.credentials()
            self.assertIn("secret part is missing", str(ctx.exception))
        finally:
            os.environ.pop("HF_KEY", None)


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg not installed")
class SlimFfmpegTests(unittest.TestCase):
    """Homebrew's slim ffmpeg has no libass; make sure we still produce a video."""

    def _render(self, caps):
        p, d = make_project()
        d["lines"] = d["lines"][:2]
        d["clips"] = [{"id": "C01", "lines": ["1"], "from": "F01", "to": None, "motion": "x"},
                      {"id": "C02", "lines": ["2"], "from": "F01", "to": None, "motion": "x"}]
        d["settings"] = {"video_width": 360, "video_height": 640, "caption_size": 32}
        p.save(d)
        _png(p.path("frames", "F01.png"))
        real = dict(assemble.ffmpeg_caps())
        assemble._CAPS.clear()
        assemble._CAPS.update({**real, **caps})
        try:
            rep = assemble.assemble(p, d, log=lambda *_: None)
        finally:
            assemble._CAPS.clear()
        self.assertTrue(Path(rep["file"]).exists())
        self.assertTrue(Path(rep["srt"]).read_text().startswith("1\n00:00:00,000 --> "))
        return rep

    def test_drawtext_fallback(self):
        rep = self._render({"subtitles": False, "drawtext": True})
        self.assertEqual(rep["captions"], "drawtext")

    def test_no_text_at_all_still_makes_video_and_srt(self):
        rep = self._render({"subtitles": False, "drawtext": False})
        self.assertEqual(rep["captions"], "none (see .srt)")

    def test_encoder_fallback_without_libx264(self):
        rep = self._render({"subtitles": False, "drawtext": False, "libx264": False, "videotoolbox": False})
        self.assertTrue(Path(rep["file"]).stat().st_size > 1000)


V2 = json.loads((STUDIO / "projects" / "elevator-v2" / "video.json").read_text())


class V2PlanTests(unittest.TestCase):
    def test_v2_script_passes(self):
        self.assertFalse(lint.has_errors(lint.check(V2)), lint.format_report(lint.check(V2)))

    def test_first_frame_forbids_parts_not_built_yet(self):
        f01 = next(f for f in V2["frames"] if f["id"] == "F01")
        prompt = frames.prompt_for(V2, f01)
        for thing in ("guide rails", "electric motor", "counterweight", "governor", "elevator doors"):
            self.assertIn(thing, prompt.split("NOT BUILT YET")[1])

    def test_close_frame_skips_the_wide_building_style(self):
        f05c = next(f for f in V2["frames"] if f["id"] == "F05c")
        prompt = frames.prompt_for(V2, f05c)
        self.assertTrue(prompt.startswith(frames.CLOSE_STYLE))
        self.assertNotIn(V2["style"], prompt)
        self.assertNotIn("same camera position", prompt)
        self.assertIn("NOT BUILT YET", prompt)
        f04 = next(f for f in V2["frames"] if f["id"] == "F04")
        self.assertTrue(frames.prompt_for(V2, f04).startswith(V2["style"]))

    def test_later_frame_lists_built_parts_and_forbids_only_later_ones(self):
        f05 = next(f for f in V2["frames"] if f["id"] == "F05")
        built, missing = frames.build_state(V2, f05)
        self.assertTrue(any("guide rails" in b for b in built))
        self.assertTrue(any("governor" in m for m in missing))
        self.assertFalse(any("guide rails" in m for m in missing))

    def test_cue_moves_the_cut_onto_the_word(self):
        words = timing.estimated_words(V2, 230)
        segs, _ = timing.segments(V2, words, 0.8)
        seg = {s["clip"]: s for s in segs}
        lt = timing.line_times(V2, words)
        snaps = next(w for w in lt["2"]["words"] if w["w"].startswith("snaps"))
        self.assertAlmostEqual(seg["C02"]["start"], snaps["s"] - 0.15, places=2)
        self.assertGreater(seg["C02"]["start"], lt["2"]["start"])
        self.assertAlmostEqual(seg["C01"]["end"], seg["C02"]["start"])

    def test_bad_cue_word_is_reported(self):
        d = copy.deepcopy(V2)
        d["clips"][1]["cue"] = "explodes"
        with self.assertRaises(ValueError):
            timing.segments(d, timing.estimated_words(d, 230), 0.8)


V3 = json.loads((STUDIO / "projects" / "elevator-v3" / "video.json").read_text())


class V3PlanTests(unittest.TestCase):
    def test_v3_passes_and_has_no_cuts(self):
        self.assertFalse(lint.has_errors(lint.check(V3)), lint.format_report(lint.check(V3)))
        self.assertFalse(any(c.get("cut") for c in V3["clips"]))     # one continuous scene
        self.assertEqual(V3["budget"]["cap_usd"], 7.0)
        self.assertTrue(any("physically possible" in r for r in V3["rules"]))

    def test_now_result_lines_follow_key_fixes(self):
        roles = [l["role"] for l in V3["lines"]]
        self.assertGreaterEqual(roles.count("RESULT"), 2)

    def test_next_step_mode_limits_the_batch(self):
        fake = FakeHiggsfield()
        old, http.transport = http.transport, fake
        try:
            p, d = make_project(V3)
            _png(p.path("frames", "F01.png"))
            _png(p.path("frames", "F02.png"))
            client = hf.Client("id", "secret", sleep=lambda s: None)
            made = clips.run(p, d, client, approve_usd=1.0, next_n=2, log=lambda *_: None)
            self.assertEqual(made, ["C01", "C02"])
            todo, _ = clips.plan(p, d, next_n=2)
            self.assertEqual([t["clip"]["id"] for t in todo], ["C03", "C04"])
        finally:
            http.transport = old


class FakeKie:
    def __init__(self, broke=False, fail=False):
        self.calls, self.polls, self.broke, self.fail = [], 0, broke, fail
        self.png = Path(tempfile.mkdtemp()) / "out.png"
        _png(self.png, "0x22aa55")

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body))
        js = lambda o: (200, {}, json.dumps(o).encode())  # noqa: E731
        if url.endswith("/file-base64-upload"):
            return js({"success": True, "code": 200, "data": {"downloadUrl": "https://tmp.kie.test/ref.png"}})
        if url.endswith("/jobs/createTask"):
            if self.broke:
                return js({"code": 402, "msg": "Insufficient credits"})
            return js({"code": 200, "data": {"taskId": "t1"}})
        if "/jobs/recordInfo" in url:
            self.polls += 1
            if self.polls < 2:
                return js({"code": 200, "data": {"state": "generating"}})
            if self.fail:
                return js({"code": 200, "data": {"state": "fail", "failMsg": "content policy", "creditsConsumed": 0}})
            return js({"code": 200, "data": {"state": "success", "creditsConsumed": 18,
                                             "resultJson": json.dumps({"resultUrls": ["https://tmp.kie.test/out.png"]})}})
        if url == "https://tmp.kie.test/out.png":
            assert "Authorization" not in headers, "kie key must not go to the image download host"
            return 200, {}, self.png.read_bytes()
        if url.endswith("/chat/credit"):
            return js({"code": 200, "data": 1000})
        raise AssertionError(f"unexpected {method} {url}")


class KieTests(unittest.TestCase):
    def setUp(self):
        os.environ["KIE_API_KEY"] = "test-key"
        self._old = http.transport

    def tearDown(self):
        http.transport = self._old
        os.environ.pop("KIE_API_KEY", None)

    def test_frame_via_kie_logs_real_charge_and_sends_refs(self):
        fake = FakeKie()
        http.transport = fake
        p, d = make_project(V3)
        _png(p.path("frames", "F01.png"))
        with self.assertRaises(ledger.BudgetError):
            frames.make_with_kie(p, d, "F02", approve_usd=None, sleep=lambda s: None)
        dest = frames.make_with_kie(p, d, "F02", approve_usd=0.09, sleep=lambda s: None)
        self.assertTrue(dest.exists())
        self.assertAlmostEqual(ledger.spent(p), 0.09)                    # 18 credits x $0.005
        task = json.loads(next(c[3] for c in fake.calls if c[1].endswith("/jobs/createTask")))
        self.assertEqual(task["model"], "nano-banana-pro")
        self.assertEqual(task["input"]["aspect_ratio"], "9:16")
        self.assertEqual(task["input"]["image_input"], ["https://tmp.kie.test/ref.png"])
        self.assertIn("NOT BUILT YET", task["input"]["prompt"])
        self.assertEqual(p.load_state()["frames"]["F02"]["source"], "kie:nano-banana-pro")

    def test_insufficient_credits_in_body_is_an_error(self):
        http.transport = FakeKie(broke=True)
        from cutaway import kie
        p, d = make_project(V3)
        with self.assertRaises(kie.KieError) as ctx:
            frames.make_with_kie(p, d, "F01", approve_usd=0.09, sleep=lambda s: None)
        self.assertIn("Insufficient credits", str(ctx.exception))
        self.assertEqual(ledger.spent(p), 0.0)

    def test_failed_image_is_not_charged(self):
        http.transport = FakeKie(fail=True)
        from cutaway import kie
        p, d = make_project(V3)
        with self.assertRaises(kie.KieError):
            frames.make_with_kie(p, d, "F01", approve_usd=0.09, sleep=lambda s: None)
        self.assertEqual(ledger.spent(p), 0.0)

    def test_credit_balance(self):
        http.transport = FakeKie()
        from cutaway import kie
        self.assertEqual(kie.credits(), 1000.0)


class LedgerBreakdownTests(unittest.TestCase):
    def test_breakdown_separates_remakes(self):
        p, d = make_project()
        ledger.append(p, "spend", "higgsfield", "C01", 0.30)
        ledger.append(p, "spend", "higgsfield", "C02", 0.45)
        ledger.append(p, "spend", "higgsfield", "C02", 0.45)    # remade once
        st = p.load_state()
        st["clips"]["C02"] = {"model": "wan3", "body": {"duration": 6}}
        p.save_state(st)
        out = ledger.breakdown(p)
        self.assertIn("C02      2x  $ 0.900", out)
        self.assertIn("0.0750", out)                              # $/sec for C02
        self.assertIn("$0.75 first attempts + $0.45 remakes", out)


DT = json.loads((STUDIO / "projects" / "drain-test" / "video.json").read_text())


class ShotCheckTests(unittest.TestCase):
    def test_drain_test_shots_pass(self):
        rep = lint.check_shots(DT)
        self.assertFalse(any(l == "error" for l, _ in rep), rep)

    def test_big_zoom_and_missing_move_are_errors(self):
        d = copy.deepcopy(DT)
        d["frames"][3]["zoom"] = 5
        d["clips"][1].pop("move")
        msgs = " ".join(m for l, m in lint.check_shots(d) if l == "error")
        self.assertIn("zooms 5.0x", msgs)
        self.assertIn("has no 'move'", msgs)

    def test_moved_frame_prompt_says_camera_moved(self):
        d04 = next(f for f in DT["frames"] if f["id"] == "D04")
        p = frames.prompt_for(DT, d04)
        self.assertIn("the camera has moved", p)
        self.assertNotIn("same camera position", p)


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg not installed")
class CompareTests(unittest.TestCase):
    def test_two_models_side_by_side_with_own_chains(self):
        from cutaway import compare
        fake = FakeHiggsfield()
        old, http.transport = http.transport, fake
        try:
            p, d = make_project(DT)
            for fid in ("D02", "D03", "D04"):
                _png(p.path("frames", f"{fid}.png"))
            client = hf.Client("id", "secret", sleep=lambda s: None)
            rows, total = compare.estimate(p, d, client, ["wan3", "seedance2"])
            self.assertEqual(len(rows), 4)
            with self.assertRaises(ledger.BudgetError):
                compare.run(p, d, client, ["wan3", "seedance2"], approve_usd=None)
            out = compare.run(p, d, client, ["wan3", "seedance2"], approve_usd=total, log=lambda *_: None)
            self.assertTrue(out.exists())
            self.assertTrue((p.dir / "compare" / "seedance2" / "T2.mp4").exists())
            self.assertTrue((p.dir / "compare" / "wan3" / "T2_start.png").exists())   # chained per model
            self.assertAlmostEqual(ledger.spent(p), total)
        finally:
            http.transport = old


LF = json.loads((STUDIO / "projects" / "landfill" / "video.json").read_text())


class LandfillPlanTests(unittest.TestCase):
    def test_landfill_passes_every_check(self):
        rep = lint.check(LF)
        self.assertFalse(lint.has_errors(rep), lint.format_report(rep))
        self.assertFalse([m for l, m in rep if l == "warn"], lint.format_report(rep))

    def test_beats_are_short_like_theirs(self):
        segs, total = timing.segments(LF, timing.estimated_words(LF, 230), 0.8)
        self.assertTrue(all(2.0 <= s["seconds"] <= 7.5 for s in segs), segs)
        self.assertGreater(total, 61)

class EstimateParsingTest(unittest.TestCase):
    TEXT = {"type": "description", "pricing_description":
            "Standard self-serve rates in USD per video second: 480p: $0.0375; 720p: $0.0750; "
            "1080p: $0.1500. Total price = selected rate \u00d7 output duration in seconds."}

    def test_numeric_reply(self):
        from cutaway import higgsfield as hf
        self.assertEqual(hf.price_from_estimate({"usd": "0.20"}, {}), 0.2)

    def test_text_reply_uses_resolution_and_duration(self):
        from cutaway import higgsfield as hf
        self.assertAlmostEqual(hf.price_from_estimate(self.TEXT, {"duration": 4, "resolution": "720p"}), 0.3)
        self.assertAlmostEqual(hf.price_from_estimate(self.TEXT, {"duration": 4, "resolution": "1080p"}), 0.6)

    def test_text_reply_without_resolution_means_720p(self):
        from cutaway import higgsfield as hf
        self.assertAlmostEqual(hf.price_from_estimate(self.TEXT, {"duration": 5}), 0.375)

    def test_unreadable_reply_is_refused(self):
        from cutaway import higgsfield as hf
        with self.assertRaises(hf.EstimateUnreadable):
            hf.price_from_estimate({"type": "description", "pricing_description": "Ask sales"}, {"duration": 4})
        with self.assertRaises(hf.EstimateUnreadable):
            hf.price_from_estimate(self.TEXT, {"duration": 4, "resolution": "4k"})
        with self.assertRaises(hf.EstimateUnreadable):
            hf.price_from_estimate(self.TEXT, {"prompt": "image, no duration"})

    def test_planning_cost_is_resolution_aware(self):
        from cutaway import higgsfield as hf
        self.assertGreater(hf.planning_cost("wan3", 4, "720p"), hf.planning_cost("wan3", 4, "480p"))
        self.assertIsNone(hf.planning_cost("kling-o3", 4, "480p"))


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg not installed")
class SeedanceSafetyTests(unittest.TestCase):
    def test_start_frame_is_resized_to_match_end_frame(self):
        tmp = Path(tempfile.mkdtemp())
        start, end = tmp / "start.png", tmp / "end.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=480x854",
                        "-frames:v", "1", str(start)], check=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=768x1376",
                        "-frames:v", "1", str(end)], check=True)
        fixed = clips.match_size(start, end)
        self.assertEqual(clips._size(fixed), (768, 1376))
        self.assertEqual(clips.match_size(end, end), end)          # same size: untouched

    def test_estimate_text_without_the_word_video(self):
        res = {"type": "description", "pricing_description": "USD per second: 480p: $0.0804; 720p: $0.1735."}
        self.assertAlmostEqual(hf.price_from_estimate(res, {"duration": 4, "resolution": "480p"}), 0.3216)

    def test_compare_records_the_failure_reason(self):
        from cutaway import compare
        fake = FakeHiggsfield(final_status="failed")
        old, http.transport = http.transport, fake
        try:
            p, d = make_project(DT)
            for fid in ("D02", "D03", "D04"):
                _png(p.path("frames", f"{fid}.png"))
            client = hf.Client("id", "secret", sleep=lambda s: None)
            logs = []
            compare.run(p, d, client, ["seedance2"], approve_usd=1.0, log=logs.append)
            self.assertTrue(any("not charged" in l for l in logs))
            self.assertTrue((p.dir / "compare" / "seedance2" / "T1.error.json").exists())
            self.assertEqual(ledger.spent(p), 0.0)
        finally:
            http.transport = old
