# Design: D5 auto-binding standard OFL lasers

## Scope
Draft a usable, safe binding from any OFL profile PyLZR can read, by capability type, so a new laser works with
existing scenes after minutes rather than an afternoon of JSON. Pattern-request fallbacks when a library has no
entry in the requested category. An on-screen coverage report: which attributes a fixture type supports, which it
lacks, which channels nobody drives. Out of scope: editing bindings in the GUI beyond "save this draft to my folder
and open it", 16-bit or matrix fixtures (still refused), learning mappings from hardware behaviour.

## Interfaces
```python
# src/pylzr/fixtures/autobind.py  (pure)
@dataclass(frozen=True)
class Coverage:
    mapped:    Mapping[str, tuple[str, ...]]     # attribute → channel keys it drives
    unmapped:  tuple[str, ...]                   # core attributes nothing drives
    undriven:  tuple[str, ...]                   # channels no mapping or base value touches
    notes:     tuple[str, ...]                   # why a channel was skipped ('Rotation Z: no proportional segment')

def draft_binding(profile: Profile, mode: str, name: str = '') -> tuple[Binding, Coverage]
    # Rules table (one row per OFL capability type → spec): BeamPosition(horizontal/vertical) → bipolar pos_x/pos_y;
    # Zoom → linear size or zoom; Rotation (angle) → linear rot_*; Rotation (speed, two directions) → direction spin_*;
    # ShutterStrobe(speed) → linear strobe with 'zero' on the NoFunction/open segment; ColorPreset → options color by
    # colour name; EffectSpeed → direction/linear by name ('scan', 'wave', 'gradient'); Maintenance → never; unknown →
    # a note. Layers: detect a repeated channel block (same capability layout at a constant offset) → layers a/b.
    # Patterns: channels of type Effect/WheelSlot with many steps → the pattern section with an empty library and
    # 'none' at the first NoFunction value if any.

def coverage(renderer: Renderer) -> Coverage      # for any binding, drafted or hand-written (the report)

# src/pylzr/fixtures/patterns.py
@dataclass(frozen=True)
class FallbackPolicy:
    related:   Mapping[str, tuple[str, ...]]     # category → categories to try next ('tunnel' → ('circle', 'abstract'))
    any_last:  bool = True                       # finally any entry, closest on the scales
class PatternLibrary:
    def match(self, request, policy: FallbackPolicy | None = None) -> PatternEntry | None

# src/pylzr/fixtures/library.py
def draft_type(self, profile_key: str, mode: str) -> tuple[str, Coverage]   # saves bindings/<profile_key>-<mode>.json
                                                                               # to your folder; returns the new key
```
Ownership: `autobind.py` only reads `Profile` and builds a `Binding` through the existing spec classes
(`specs.py`, `SPEC_TYPES`), so every draft goes through `Binding.resolve` and the same safety checks as a hand-written
file. The vocabulary owns the `related` table (starter list + yours). GUI: in Settings → DMX, a "Draft binding from a
profile…" button listing profiles without a binding; the coverage report in the Attributes tab header ("This laser:
18 of 26 attributes; no wave, no gradient").

## Threading / timing
All on the GUI thread at the user's request; a draft is one `resolve` (ms). Nothing in the real-time path changes.
The fallback policy runs inside `PatternMapping.chosen` at render time: bounded by the number of categories (≤ ~20),
no allocation beyond today's `min()`.

## Failure modes
| Failure | Safe state |
|---|---|
| Draft violates a safety rule (a heuristic picked a Maintenance-adjacent segment) | `resolve` raises → the draft is not saved; the message names the channel; the note goes in the report |
| Profile has a feature PyLZR refuses | refused as today at load; no draft offered |
| Draft maps nothing useful (unknown types everywhere) | saved only if ≥ 1 mapping; otherwise reported "nothing recognised" |
| A drafted layer offset is wrong | the existing layer check (same segments) rejects it; the draft falls back to one layer with a note |
| Fallback picks a visually wrong pattern | by design; the match line in the tester shows "fell back to circle" so it can be tagged |

## Migration (each step leaves the app working)
1. `coverage(renderer)` + the report line in the Attributes tab (reads `Renderer.supports/choices`, `renderer.py:157-163`).
   Useful on its own for the Gruolin.
2. `FallbackPolicy` in `patterns.py:182-190`; vocabulary gains `related`; the match line shows fallbacks.
3. `draft_binding` rules table, developed against `tests/data/ofl/laserworld/el-400rgb-mk2.json`
   (`tests/sample_fixture.py` is today's hand-written binding for it: the draft should reproduce its mappings or
   better) and the Gruolin profile (the draft should match the shipped binding's channels for every rule-covered
   attribute).
4. `FixtureLibrary.draft_type` + the Settings button.
5. docs/fixtures.md section; README.

## Tests
CI: rules table tests per capability type on synthetic channels; EL-400 and Gruolin drafts resolve and render; the
golden Gruolin renders through the *drafted* binding compared with the shipped one on the rule-covered attributes;
coverage of the shipped binding is exact; fallback order. Hardware: a second laser, when there is one.

## Dependencies
D2 complete (vocabulary, tester), D3 (scenes are what portability serves). Independent of D4/D6.

## Open questions
- **Q1.** Should drafts be saved immediately to the user's folder (then editable) or kept in memory until the user
  presses Save in a review dialog?
- **Q2.** Layer detection: attempt it (risky heuristics) or ask the user "does this laser have two pattern outputs,
  offset by N channels?" with a guess prefilled?
- **Q3.** The `related` category table: starter values, or empty until the user adds some?
- **Q4.** Is D5 still wanted before a second laser exists, or should it wait for one (as the roadmap now orders it)?
