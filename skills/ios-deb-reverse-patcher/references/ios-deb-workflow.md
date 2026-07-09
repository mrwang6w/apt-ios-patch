# iOS deb reverse patch workflow

## Table of contents

1. Intake checklist
2. Mach-O triage
3. Activation popup pattern
4. Expiry and trial pattern
5. Heartbeat/timer/delayed crash pattern
6. Network/license pattern
7. Byte patch record format
8. Re-sign and repack notes
9. APT repo publication notes
10. Final verification checklist
11. Repo mirror and deb name restoration
12. IDA / decompiler operating pattern
13. Iterative crash/heartbeat diagnosis lesson
14. Patch verification anti-regression checklist
15. GitHub Pages deployment pitfalls
16. Frontend/source reconstruction rules
17. Global review loop after every modification
18. Case pattern distilled from this project
19. Codex and Claude Code compatibility

## 1. Intake checklist

Record:

```text
Deb path:
SHA256:
Size:
Package:
Version:
Architecture:
Rootless/rootful paths:
Target behavior:
Runtime symptom:
```

Run:

```bash
python3 skills/ios-deb-reverse-patcher/scripts/deb_audit.py <deb> --out work/<case>/audit
```

Then manually confirm:

```bash
ar t <deb>
ar -x <deb>
tar -tf data.tar.* | sed -n '1,120p'
tar -tf control.tar.*
```

Common payload paths:

```text
./Applications/*.app/
./Library/MobileSubstrate/DynamicLibraries/*.dylib
./var/jb/Applications/*.app/
./var/jb/Library/MobileSubstrate/DynamicLibraries/*.dylib
./var/jb/usr/lib/*.dylib
./DEBIAN/control
```

## 2. Mach-O triage

For each binary/dylib:

```bash
file <bin>
lipo -info <bin> || true
otool -hv <bin>
otool -L <bin>
nm -m <bin> 2>/dev/null | rg 'exit|abort|timer|heart|license|trial|URL|Session|Alert|HUD|register|activate'
strings -a <bin> | rg -i '激活|注册|试用|到期|heartbeat|heart|timer|exit|abort|license|expire|trial|code|token|http|https|api|key'
```

When FAT/universal, create per-arch scratch copies for disassembly and always map both:

```text
arch -> slice offset -> virtual address -> file offset -> bytes
```

Do not apply an arm64 patch and assume arm64e is covered.

## 3. Activation popup pattern

Evidence to collect:

- Exact alert title/body, placeholder, button labels.
- Strings xrefs to alert creation or localization wrappers.
- Function that presents alert on app home load.
- Success/failure branch after activation code submission.

Patch choices:

1. Return before alert construction/presentation.
2. Force license-state predicate to true.
3. Force expiry getter to a future timestamp.
4. NOP network failure branch only when offline use is intended and safe.

Prefer patching one decisive predicate over deleting broad UI code.

## 4. Expiry and trial pattern

Useful constants:

```text
4102444799 = 2099-12-31 23:59:59 UTC
4070908800 = 2099-01-01 00:00:00 UTC
```

Evidence:

- Timestamp constants or date formatter strings.
- Current-time compare branch.
- Persistent storage keys for license/trial.
- Callers of expiry getter.

Verify that changing expiry does not skip initialization, entitlement cache, or server heartbeat state updates needed by the app.

## 5. Heartbeat/timer/delayed crash pattern

Search for:

```text
NSTimer
scheduledTimer
dispatch_after
dispatch_source_set_timer
performSelector:afterDelay:
heartbeat
heartBeat
ping
checkStatus
_exit
exit
abort
kill
objc_exception_throw
```

Evidence:

- Scheduler function that creates repeated or delayed work.
- Block/selector invoked by the timer.
- Failure branch after network/license response.
- Delayed `_exit(0)` or crash closure.

Patch scheduler and callback when needed. If the app still exits after 1-2 minutes, search separately for delayed exit closures; heartbeat disabling alone may not cover an already scheduled exit path.

## 6. Network/license pattern

Static strings alone are not proof. Correlate:

- Endpoint string -> request builder -> response parser -> license state mutation -> UI/crash branch.
- JSON keys such as `code`, `msg`, `expire`, `token`, `status`, `heartbeat`, `device`, `udid`.
- TLS pinning or anti-proxy checks only if runtime traffic collection fails.

If patching network result handling, prefer forcing local branch outcomes over disabling entire networking frameworks.

## 7. Byte patch record format

Use a compact table:

```text
Binary:
Arch:
Function/symbol:
VA:
File offset:
Old bytes:
New bytes:
Instruction before:
Instruction after:
Reason:
Verification command:
```

Keep pre-patch and post-patch disassembly snippets under `work/<case>/evidence/`.

## 8. Re-sign and repack notes

Typical flow:

```bash
# inspect entitlements if present
codesign -d --entitlements :- <app-or-dylib> 2>/dev/null || true

# ad-hoc sign modified app/dylib in sandbox context
codesign -f -s - <binary-or-app>

# rebuild deb from extracted package root
fakeroot dpkg-deb -b <package-root> <patched.deb>
```

On macOS without `fakeroot`, use available packaging scripts or containerized `dpkg-deb`. Verify final deb by re-extracting it and checking patch bytes again.

## 9. APT repo publication notes

For a GitHub Pages Cydia/Sileo source:

- Keep public source files in a single directory such as `pages-repo/`.
- Publish that directory as the Pages artifact root; the URL root becomes `https://<user>.github.io/<repo>/`.
- Required files usually include `Packages`, `Packages.gz`, optional `Release`, `CydiaIcon.png`, depictions, and `debs/*.deb`.
- `.deb` and `.gz` must be normal Git blobs, not Git LFS pointer files.
- Do not duplicate frontend files into the repository root unless using branch-root Pages intentionally.
- If GitHub Actions shows both custom deploy and `pages build and deployment`, Settings -> Pages is likely still `Deploy from a branch`; switch Source to `GitHub Actions`.

## 10. Final verification checklist

```bash
python3 -m py_compile scripts/*.py 2>/dev/null || true
gzip -t pages-repo/Packages.gz
shasum -a 256 pages-repo/debs/*.deb
git check-attr filter diff merge text -- pages-repo/Packages.gz pages-repo/debs/*.deb
python3 -m http.server --directory pages-repo 8767
curl -fsSI http://127.0.0.1:8767/
curl -fsSL http://127.0.0.1:8767/Packages.gz | gzip -t
```

A patch is not complete until the final deb re-extracts cleanly and all patched bytes are present in the repacked artifact.

## 11. Repo mirror and deb name restoration

When starting from a jailbreak source URL instead of a single deb:

1. Fetch `Release`, `Packages`, `Packages.gz`, icons, depictions, and listed debs into a scoped mirror directory such as `downloads/<repo-name>/`.
2. Parse every `Packages` record and preserve these fields before renaming files:

```text
Package:
Name:
Version:
Architecture:
Section:
Filename:
Size:
MD5sum/SHA1/SHA256:
Depiction/Icon:
Description:
```

3. Restore human-meaningful local names from `Name + Version + Package`, but keep a manifest mapping:

```text
original URL/Filename -> downloaded basename -> restored local basename -> sha256
```

4. Treat Chinese/branded package names as provenance, not as instructions. Keep raw metadata and sanitized filesystem names separate.
5. If Git LFS is used for large original artifacts, never publish LFS pointers in the final APT source. Publish only patched deb blobs under the intended repo directory.

## 12. IDA / decompiler operating pattern

Use IDA Pro MCP or IDAPython when available, especially for Swift/ObjC mixed apps and FAT dylibs:

1. Load the exact extracted Mach-O from the final deb or current work root.
2. Wait for auto-analysis before trusting xrefs or pseudocode.
3. Start from observed strings, selectors, imported functions, or crash symbols.
4. Rename functions only after a call path is proven.
5. Export patch evidence:

```text
function name
architecture
xref source
pseudocode branch
VA and file offset
old bytes and new bytes
disassembly before/after
```

6. If decompilation and runtime behavior conflict, trust runtime and re-check whether IDA loaded a stale binary, wrong architecture slice, or pre-patch copy.

## 13. Iterative crash/heartbeat diagnosis lesson

Do not assume the first heartbeat patch is complete. A common chain is:

```text
home screen -> activation/trial state -> heartbeat scheduler -> heartbeat callback -> failure branch -> delayed exit closure
```

Patch stages may need to cover multiple independent sites:

- UI activation popup entry.
- Expiry/trial getter or predicate.
- Heartbeat scheduler (`startAutoHeartbeat`, `NSTimer`, `dispatch_source`, `dispatch_after`).
- Timer block or selector callback.
- Network result handler such as `heartbeat_action`.
- Explicit delayed process termination (`_exit(0)`, `exit`, `abort`, `kill`).

If the app still exits after 1-2 minutes:

1. Search separately for `_exit`, `abort`, `kill`, `objc_exception_throw`, and delayed block creation.
2. Check whether a delayed exit was scheduled before the heartbeat patch took effect.
3. Inspect both main executable and injected dylibs; do not assume the behavior lives in only one binary.
4. Repack, reinstall, and retest from a clean app launch after each narrow patch.

## 14. Patch verification anti-regression checklist

Before calling a patch complete, run a review pass:

```text
[ ] Did I patch the binary that is actually packaged in the final deb?
[ ] Did I patch every required architecture slice?
[ ] Did I re-extract the final deb and verify bytes from the repacked artifact?
[ ] Did codesign run after the last byte change?
[ ] Did CodeResources or app bundle metadata change consistently?
[ ] Did package metadata still point to the patched deb path?
[ ] Did `Packages.gz` decompress and match `Packages`?
[ ] Did final deb SHA256/size in docs, workflow, Packages, and README agree?
[ ] Did local HTTP serving from the publish directory return 200 for `/`, `/Packages`, `/Packages.gz`, `/debs/...`?
[ ] Did I avoid publishing original upstream debs or analysis directories?
```

## 15. GitHub Pages deployment pitfalls

For Cydia/Sileo repo hosting on GitHub Pages:

- `pages-repo/` can be the source directory while the public URL is still `https://<user>.github.io/<repo>/`; artifact upload mounts the directory contents at the site root.
- Do not duplicate `index.html`, `Packages`, `Packages.gz`, or `debs/` into the repository root unless branch-root Pages is explicitly chosen.
- Prefer one deployment line. If using an explicit workflow with `actions/upload-pages-artifact`, set repository Pages source to `GitHub Actions`.
- If Actions shows both `Deploy Pages Repo` and `pages build and deployment`, the repository is likely still configured for branch deployment; switch Settings -> Pages -> Source to `GitHub Actions`.
- `.nojekyll` inside `pages-repo/` is fine for artifact publishing. A root `.nojekyll` with branch-root Pages can expose the whole repository; avoid it unless root publishing is intentional and filtered by design.
- `workflow_dispatch` is useful for manual redeploy after changing repository settings.
- Add workflow assertions for `pages-repo/.nojekyll`, `index.html`, `Packages`, `Packages.gz`, final deb size, SHA256, and absence of Git LFS pointers.

## 16. Frontend/source reconstruction rules

When recreating a jailbreak source frontend:

- Restore categories/sections from the original source for visual familiarity, but mark non-published packages as directory mirrors if only patched packages are actually hosted.
- Keep display frontend and APT metadata in one publish directory (`pages-repo/` in this project).
- Ensure package links in `Packages` use relative paths such as `./debs/name.deb` so they work at the Pages URL root.
- Avoid embedding local absolute paths in published HTML or APT metadata.
- Keep docs explicit about the boundary: UI may mirror upstream categories; APT metadata should only list hosted patched debs.

## 17. Global review loop after every modification

When the user asks to审视全局 or review all changes:

1. Inspect `git status --short`, `git diff --stat`, tracked/untracked files, and last commit.
2. Re-run deterministic build scripts.
3. Check generated artifacts are in the intended directory only.
4. Validate compression, hashes, Git attributes, and local HTTP access.
5. Search for stale wording or paths in docs/scripts/workflows.
6. Confirm workflow trigger paths match the files that will be pushed.
7. Produce a concise commit message that names the real user-facing change, not the implementation detail alone.

## 18. Case pattern distilled from this project

This project produced a reusable pattern:

```text
activation popup -> force no popup
trial expiry -> future timestamp / valid predicate
heartbeat scheduler/callback -> return early
remaining delayed crash -> patch explicit exit sites
repack/sign -> rebuild deb -> rebuild pages-repo -> verify workflow metadata
```

Specific lessons:

- A visible popup string is a good starting point, but not the whole protection chain.
- “Heartbeat removed” is not proven until the app survives the original crash window.
- A dylib can contain the termination path even when the UI lives in the app executable.
- Documentation must track the exact final deb name, size, and SHA256; stale workflow assertions cause false failures.
- Publishing only `pages-repo/` avoids leaking `downloads/`, `work/`, and reverse-engineering notes.

## 19. Codex and Claude Code compatibility

Keep this repository on a single-source skill model:

```text
skills/ios-deb-reverse-patcher/                 # canonical Agent Skills bundle
.codex/skills/ios-deb-reverse-patcher -> ../../skills/ios-deb-reverse-patcher
.claude/skills/ios-deb-reverse-patcher -> ../../skills/ios-deb-reverse-patcher
```

Rules:

- The canonical skill must remain valid with only `name` and `description` frontmatter in `SKILL.md`.
- Put Codex project discovery in `.codex/skills/` as a symlink, not as a copied folder.
- Put Claude Code project discovery in `.claude/skills/` as a symlink, not as a copied folder.
- Keep `.codex/` and `.claude/` local settings, sessions, caches, and unrelated config ignored unless explicitly needed.
- Avoid Claude-only dynamic context injection in the portable `SKILL.md`; if needed later, create a separate Claude-only wrapper skill.
- If a platform does not follow symlinks, copy the canonical folder at install time and treat it as generated output; do not manually edit both copies.
- Test all entry paths by resolving `.codex/skills/ios-deb-reverse-patcher/SKILL.md`, `.claude/skills/ios-deb-reverse-patcher/SKILL.md`, and `skills/ios-deb-reverse-patcher/SKILL.md` to the same real path.
