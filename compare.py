"""Capture the upstream SwiftUI views on an actual iOS Simulator, not a mockup."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT / "upstream"
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)
SOURCE = "Sources/Extensions/Widgets/LiveActivity/HACompactTrailingView.swift"
TEST = UPSTREAM / "Tests/Widgets/HADynamicIslandSnapshot.test.swift"
SNAPSHOTS = UPSTREAM / "Tests/Widgets/__Snapshots__/HADynamicIslandSnapshot.test"
REVISION = "2bca3df909a966686b14c5c552242a03fa28d064"


def run(args, log=None, env=None, allow_failure=False):
    print("Running: " + " ".join(map(str, args)), flush=True)
    if log:
        with (RESULTS / log).open("w") as output:
            result = subprocess.run(args, cwd=UPSTREAM, env=env, stdout=output, stderr=subprocess.STDOUT)
    else:
        result = subprocess.run(args, cwd=UPSTREAM, env=env, capture_output=True, text=True)
    if result.returncode and not allow_failure:
        if log:
            print("\n".join((RESULTS / log).read_text(errors="replace").splitlines()[-90:]))
        else:
            print(result.stderr)
        raise RuntimeError("Command failed: " + str(result.returncode))
    return result


assert run(["git", "rev-parse", "HEAD"]).stdout.strip() == REVISION
devices = json.loads(run(["xcrun", "simctl", "list", "devices", "available", "--json"]).stdout)
matches = [(runtime, device) for runtime, group in devices["devices"].items()
           for device in group if runtime.endswith("iOS-27-0") and device["name"] == "iPhone 17"]
if len(matches) != 1:
    (RESULTS / "available-simulators.json").write_text(json.dumps(devices, indent=2))
    raise RuntimeError("Expected exactly one iPhone 17 / iOS 27.0 simulator")
runtime, device = matches[0]
metadata = {"upstream_revision": REVISION, "device": device["name"], "runtime": runtime,
            "xcode": run(["xcodebuild", "-version"]).stdout.strip(),
            "rendering": "Native SwiftUI component snapshots on iOS Simulator",
            "physical_device_test": False, "full_dynamic_island_system_test": False}
(RESULTS / "environment.json").write_text(json.dumps(metadata, indent=2))

# Use the existing upstream snapshot test and production views. Only the samples
# and recording switch are test instrumentation; both variants use identical data.
text = TEST.read_text()
assert text.count("named: sample.name") == 2
text = text.replace("named: sample.name", "named: sample.name,\n                record: ProcessInfo.processInfo.environment[\"TIMER_UI_RECORD\"] == \"1\"")
marker = "        return [\n"
position = text.index(marker, text.index("private static func makeSamples")) + len(marker)
samples = []
for seconds, name in [(251, "timer4m11s"), (600, "timer10m00s"), (599, "timer9m59s"), (9, "timer0m09s")]:
    samples.append('''            (
                "%s",
                .init(message: "Timer UI validation", chronometer: true,
                      countdownEnd: timerStart.addingTimeInterval(%d),
                      chronometerStart: timerStart, icon: "mdi:bus-clock", color: "#EF5350")
            ),
''' % (name, seconds))
text = text[:position] + "".join(samples) + text[position:]
TEST.write_text(text)
run(["bundle", "exec", "fastlane", "autocorrect"], "autocorrect.log")
# Formatting may touch other files; restore everything except this test's instrumentation.
for path in run(["git", "diff", "--name-only"]).stdout.splitlines():
    if path != str(TEST.relative_to(UPSTREAM)).replace(os.sep, "/"):
        run(["git", "restore", "--", path])
(RESULTS / "test-instrumentation.patch").write_text(run(["git", "diff", "--", str(TEST.relative_to(UPSTREAM))]).stdout)
run(["xcodebuild", "-resolvePackageDependencies", "-project", "HomeAssistant.xcodeproj", "-scheme", "Tests-Unit"], "resolve.log")

command = ["xcodebuild", "test", "-project", "HomeAssistant.xcodeproj", "-scheme", "Tests-Unit",
           "-destination", "platform=iOS Simulator,id=" + device["udid"],
           "-derivedDataPath", str(ROOT / "DerivedData"), "-disableAutomaticPackageResolution",
           "-only-testing:Tests-App/HADynamicIslandSnapshotTests",
           "-parallel-testing-enabled", "NO", "-enableCodeCoverage", "NO",
           "COMPILER_INDEX_STORE_ENABLE=NO", "CODE_SIGNING_ALLOWED=NO"]
summary = {}
for variant in ("before", "after"):
    if variant == "after":
        run(["git", "apply", "--check", str(ROOT / "alignment.patch")])
        run(["git", "apply", str(ROOT / "alignment.patch")])
    env = dict(os.environ, TEST_RUNNER_TIMER_UI_RECORD="1")
    # SnapshotTesting intentionally reports failures when recording references.
    # A second pass must then succeed, so build/crash failures cannot be mistaken for captures.
    recording = run(command, variant + "-record.log", env=env, allow_failure=True)
    env["TEST_RUNNER_TIMER_UI_RECORD"] = "0"
    run(command, variant + "-verify.log", env=env)
    images = sorted(SNAPSHOTS.glob("*.png"))
    expected = ["timer4m11s", "timer10m00s", "timer9m59s", "timer0m09s"]
    for name in expected:
        assert any(name in image.name for image in images), "Missing native capture: " + name
    destination = RESULTS / variant
    destination.mkdir()
    for image in images:
        shutil.copy2(image, destination / image.name)
    summary[variant] = {"recording_exit_code": recording.returncode, "verification": "passed",
                        "images": {image.name: hashlib.sha256(image.read_bytes()).hexdigest() for image in images}}
    (RESULTS / "capture-status.json").write_text(json.dumps(summary, indent=2))

# Critical text, progress and the expanded layout must remain unchanged.
before = summary["before"]["images"]
after = summary["after"]["images"]
changed = [name for name in before if before[name] != after[name]]
unexpected = [name for name in changed if not name.startswith("compactTrailingSnapshots.")
              or name.endswith(("criticalText.png", "progress.png"))]
assert not unexpected, "Unexpected visual changes: " + repr(unexpected)
assert any("timer4m11s" in name for name in changed), "The proposed fix did not change the 4:11 native capture"
summary["changed_images"] = changed
summary["unchanged_controls"] = "critical text, progress and expanded snapshots"
summary["needs_human_visual_review"] = True
(RESULTS / "capture-status.json").write_text(json.dumps(summary, indent=2))
(RESULTS / "production-change.patch").write_text(run(["git", "diff", "--", SOURCE]).stdout)
print(json.dumps(summary, indent=2))
