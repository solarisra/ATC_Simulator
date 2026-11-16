# ATC Simulator Product Strategy

Status: working draft | Updated: 2026-11-16

Related: [Business plan](BUSINESS_PLAN.md) |
[Marketing strategy](MARKETING_STRATEGY.md)

## 1. Product vision and boundaries

Deliver an approachable but challenging desktop radar-control game, with a path
to evaluated educational and supplemental-practice tools.

Early-access success means users can install, understand, play, and resume a
useful scenario reliably. It does not mean implementing every real ATC procedure.
Professional interest is not certification or proof of training effectiveness.

## 2. Current baseline and verification limits

This inventory is based on the repository and owner discussion, not a release
certification or exhaustive test run.

| Area | Current baseline / limitation |
|---|---|
| Radar and interaction | Desktop radar display, menus, keyboard/mouse interaction |
| Playable traffic | Yuma scenario generation with seed and traffic mix controls |
| Other locations | Cascade/Medford is documented as map-only, without traffic scenarios |
| Persistence | Yuma scenario save/load and operational-state restoration |
| Voice | Speech recognition and synthesized pilot replies; deployment/performance need verification |
| Separation | Generator attempts initial separation placement; not runtime prevention |
| Weather | Not simulated; documented assumed altimeter setting |
| Instruction/assessment | Tutorial and instructional modes are proposed, not shipped offers |
| Traffic snapshots / multiplayer | Future candidates, not current capabilities |
| Platforms | Windows, Linux, macOS intended; packaged release matrix not established here |

The README's NVIDIA-only voice requirements conflict with earlier discussion of
CPU fallback. Reconcile documentation with tested runtime behavior before
publishing requirements. Establish minimum CPU, RAM, graphics, storage, audio,
and first-run model-download needs by measurement, not inference.

## 3. Product principles

- Preserve the controller's responsibility: aircraft can lose separation during
  normal simulation; do not silently maneuver them to prevent mistakes.
- Keep initial aircraft placement distinct from optional runtime conflict alerts
  or instructional feedback.
- Prioritize repeatable scenarios and transparent simplifications.
- Make CPU voice use viable where measured performance permits; GPU acceleration
  must not be advertised as required or optional without verification.
- Favor offline core play after any explicitly documented setup/downloads.
- Minimize collection of audio and personal data; document any external services.
- Deliver a narrow feature completely before expanding scope.

## 4. Milestone roadmap

Milestones are ordered proposals with acceptance gates, not calendar promises.
Estimate effort and cost before attaching dates or crowdfunding rewards.

### M0: Commercial-readiness foundation

- Package and test installation, launch, voice setup, and uninstall on each
  advertised operating system.
- Reconcile setup instructions, dependency/model acquisition, CPU/GPU support,
  model/binary redistribution permissions, and troubleshooting.
- Test repeated scenario generation across seeds, volumes, and aircraft mixes.
  The current bounded placement loop can finish after an unchecked final position
  adjustment; do not promise guaranteed initial separation until corrected and
  tested. Explicitly distinguish ground departures from airborne traffic.
- Validate the separation tables, aircraft categories, units, and applicability
  against the cited FAA edition with subject-matter review.
- Complete rights, privacy, license, refund, and support-readiness review.

Exit evidence: successful external install/play/save/reload sessions on every
advertised platform, no unresolved release-blocking defects, documented known
issues, and rights review for redistributed content. Define measurable voice
latency/reliability thresholds before testing and publish measured requirements.

### M1: First-session experience and tutorial

- Teach radar orientation, aircraft selection, basic clearances, radio workflow,
  and pause/save/resume in a guided scenario.
- Add clear feedback for unsupported or ambiguous voice commands.
- Offer a documented keyboard path and accessible text feedback for the tutorial;
  do not imply every spoken interaction already has a keyboard equivalent.
- Observe new users without developer coaching and fix recurring blockers.

Exit evidence: testers complete the defined tutorial tasks independently;
record completion rate, time, and major points of confusion against targets
chosen before the pilot.

### M2: Content depth and instructional pilot

- Add a complete second playable location before promising a large location count.
- Prototype instructor scenario setup and objective-based debriefing.
- Evaluate event logging/export and replay needs before selling those features.
- Separate optional conflict reporting from aircraft movement/prevention.
- Work with educators/instructors on a limited pilot with explicit limitations.

Exit evidence: reviewed location data, repeatable exercises, tested saves,
and pilot feedback supporting the proposed professional value proposition.
Instructor tools and assessment criteria require their own validation; their
presence alone does not make the game an approved training device.

### M3: Weather and traffic-snapshot feasibility

- Evaluate weather-provider terms, caching, attribution, costs, and availability.
- Distinguish displaying a current observation from actually modeling wind,
  visibility, or other effects on simulation behavior.
- Treat traffic snapshots as timestamped initial conditions, not a live operational
  feed. Label data age and source.
- Resolve missing data, on-ground states, incomplete routes, density, and
  conflicting snapshot positions; disclose adjustments needed for valid starts.
- Preserve synthetic scenarios and manual weather options when services fail.
  Surface stale/unavailable data instead of labeling fallback data as live.

Exit evidence: commercial data rights, affordable operating costs, explicit
freshness/failure behavior, and measured performance on supported hardware.

### M4: Multiplayer discovery, then a separate go/no-go

Prototype a small shared scenario before announcing a supported player count.
Scope authoritative simulation state, ownership/handoff rules, pause/time
control, reconnection, version compatibility, voice routing, and hosting.

Exit evidence: realistic network testing, consistent state, bounded hosting and
support costs, and a sustainable service policy for a one-time-purchase product.
Prefer a separately costed commitment over promising indefinite hosted service.

## 5. Editions and entitlement policy

| Edition | Product boundary |
|---|---|
| Enthusiast | Core playable simulation and documented included updates |
| Professional, deferred | Delivered instructional/debrief/export tools with a defined support scope |
| Institution | Explicit seat/site rights, deployment arrangements, and support terms |

All editions must receive applicable fixes within the published support policy;
do not make basic reliability a premium feature. Decide upgrade credit, future
expansion pricing, offline activation, shared classroom machines, and device
limits before selling each edition. Prefer buyer-friendly licensing; DRM is
not a substitute for product value and cannot guarantee piracy prevention.

## 6. Release and quality process

1. Define feature scope, acceptance criteria, and regressions to check.
2. Implement with targeted automated tests and maintainable documentation.
3. Exercise packaged builds on the supported OS/hardware matrix.
4. Test audio-device errors, model-download failure, save compatibility, and
   invalid scenario inputs with visible, actionable errors.
5. Run external playtesting and review known issues.
6. Publish release notes, supported requirements, and recovery/rollback guidance.

Use a stable build for buyers and an opt-in preview for experiments. Treat saved
scenarios as user data: version formats and provide migration or clear
compatibility warnings. Security/privacy fixes remain part of release planning.

## 7. Prioritization and capacity

Rank work by user impact, frequency, risk reduction, implementation cost, and
ongoing support burden. Stabilization and onboarding take precedence over
marketing-friendly but uncosted features.

The owner initially controls roadmap and architecture. Use bounded specialist
contracts for packaging/QA, UX, or voice bottlenecks. Networked multiplayer is a
separate specialist workstream only after funding and scope approval.

## 8. Success measures and non-goals

Track installation success, time to first useful session, tutorial completion,
voice-command acceptance/latency on representative hardware, save/load
reliability, repeat play, support hours, refunds, and instructor pilot findings.
Set thresholds before each evaluation; do not invent baseline results.

Near-term non-goals:

- Operational ATC use or certification claims.
- Guaranteed training outcomes or fully modeled FAA procedures.
- Runtime automatic separation prevention.
- Mobile/web ports, broad location counts, or unlimited institutional support.
- Committing all proposed live-data and multiplayer features in early-access
  purchase terms before feasibility and costs are established.
