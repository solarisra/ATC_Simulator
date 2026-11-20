# ATC Simulator Business Plan

Status: working draft | Updated: 2026-11-16 | Currency: USD

Related: [Marketing strategy](MARKETING_STRATEGY.md) |
[Product strategy](PRODUCT_STRATEGY.md)

## 1. Executive summary

Build a sustainable independent desktop ATC simulation business, beginning with
a focused early-access product for hobby enthusiasts. Evaluate classroom and
professional supplemental-practice use through controlled pilots before making
training-effectiveness claims or expanding support obligations.

The business model is a one-time purchase with audience-based licensing,
educational volume/site licenses, and price increases for new purchasers at
major delivered milestones. Windows, Linux, and macOS are intended desktop
platforms; release support depends on testing each packaged build.

## 2. Decisions and assumptions

### Owner-stated direction

- Early access, with more locations and features planned.
- One-time purchases rather than mandatory subscriptions.
- Audience-based tiers and institutional volume/site licensing.
- Use both Patreon and Kickstarter: ongoing optional support through Patreon
  and a finite development campaign through Kickstarter.
- Keyboard, microphone, and speakers for the intended voice-enabled experience.
- Tutorial mode, instructional mode, real-time weather, traffic snapshots, and
  multiplayer are under consideration, not delivery commitments.

### Proposals requiring validation

- Start with hobby sales; recruit educators and instructors as design partners.
- Use a small paid pilot before offering a premium institutional product.
- Choose distribution, DRM, funding launch timing, company structure, and hiring only
  after cost, legal, technical, and demand checks.
- Do not treat earlier discussion's sales, follower, or crowdfunding figures as
  forecasts. No measured demand or market-size estimate is established here.

## 3. Customers and value proposition

| Segment | Need | Initial offer | Evidence needed |
|---|---|---|---|
| Hobby enthusiasts | Engaging radar control and voice interaction | Early-access game | Demo completion, purchases, repeat play |
| Educators | Repeatable exercises and manageable deployment | Limited classroom pilot | Instructor feedback, installation and lesson fit |
| ATC trainees/training providers | Focused supplemental practice | Evaluated pilot, not certified training | Subject-matter review and documented limitations |

Sell the current experience, not a promise of operational qualification.
Existing scenarios and aircraft performance are simplified. Do not market the
product as FAA-approved, certified, or fully 7110.65-compliant.

## 4. Pricing and licensing hypotheses

| Offer | Proposed early-access price | Conditions |
|---|---|---|
| Enthusiast | $24.99 per user | Test willingness to pay against the working demo |
| Professional | $99.99 per seat, deferred | Offer only once differentiated tools/support are delivered |
| Institution | Quoted volume/site license | Define users/devices, seats, term, updates, and support in writing |

These are test prices, not published offers. Do not charge a professional premium
for analytics, export, or instructor tools that do not yet exist.

For illustration only, five $99.99 seats total $499.95; a proposed 20% volume
discount would be $399.96 before applicable tax. Validate actual institutional
pricing through interviews and pilots rather than promising unlimited seats.

For existing buyers, proposed policy: retain their purchased entitlement with no
retroactive charge when the base price rises. Define included updates, optional
future paid expansions, device use, and support before taking payments. Avoid
unlimited lifetime support or customization promises.

## 5. Distribution and protection

- Evaluate one consumer storefront first; compare reach, integration work,
  current terms, refunds, and platform support before selecting it.
- Consider direct institutional sales once invoicing and deployment are ready.
- Prefer lightweight licensing and useful offline access over always-online DRM.
- Storefront distribution does not automatically implement application DRM.
  Evaluate SDK integration and compatibility with the actual packaged Python app.
- Direct sales still have processing, tax, fraud, support, and hosting costs.

## 6. Funding strategy: Patreon and Kickstarter

Both platforms are planned. Campaign timing, funding targets, tier prices, and
rewards remain to be costed and approved. One-time game purchases remain the
core sales model; Patreon is optional recurring support, not a required game
subscription.

| Route | Appropriate use | Gate before proceeding |
|---|---|---|
| Self-funded early access | Narrow release and customer learning | Affordable support and delivery scope |
| Patreon | Optional ongoing development/community support | Sustainable benefit schedule; clear cancellation and game-access terms |
| Kickstarter | Finite, costed development milestone | Playable demo, audience evidence, quotes, fulfillment budget, contingency |

No route guarantees demand. Crowdfunding receipts are not pure profit: account
for platform/payment charges, taxes, refunds or failed payments, rewards,
development, and support. Verify current platform terms before publishing.
Coordinate both programs with one roadmap and a reward/entitlement ledger.
Budget Kickstarter against its promised deliverables without assuming future
Patreon income; budget ongoing work against actual net receipts rather than
pledges or projected membership. Do not imply Kickstarter purchases automatically confer ongoing
Patreon membership; any cross-program benefit needs explicit terms and delivery.

- Patreon: propose development updates, community discussion, and clearly defined
  preview access where feasible. Specify whether any tier includes a permanent
  game license and what access remains after cancellation before launch.
- Kickstarter: publish a bounded scope, delivery estimate, risks, reward costs,
  and game-license fulfillment method. Keep speculative features out of the
  funded commitment until scoped and budgeted.
- Cross-promotion: explain each platform's distinct purpose, make recurring
  billing explicit, and never require backers to join Patreon to receive their
  promised Kickstarter rewards.

## 7. Illustrative economics, not a forecast

Assume a $24.99 sale and a hypothetical 30% storefront deduction:

- Proceeds after that deduction: $17.493 per sale, approximately $17.49.
- Recovering a $10,000 fixed development budget takes at least 572 such sales.
- This excludes discounts, refunds, taxes, withholding, and per-customer support;
  actual required sales would be higher.

Illustrative contractor work package:

| Item | Planning allowance |
|---|---:|
| Engineering: 100 hours at $60/hour | $6,000 |
| QA: 40 hours at $35/hour | $1,400 |
| Packaging, legal/accounting, and release materials | $2,600 |
| Subtotal | $10,000 |
| 25% contingency | $2,500 |
| Total cash envelope | $12,500 |

Rates and allowances are placeholders, not market quotes. This budget excludes
owner compensation, employee payroll/benefits, and ongoing operations.
Maintain a monthly cash forecast separating cash on hand, tax/refund reserves,
committed work, owner pay, and support costs. Do not hire against an unfunded
campaign or remove contingency to make a budget appear affordable.

## 8. Staffing and operations

The owner retains product direction and core development initially. Buy bounded
help for demonstrated bottlenecks: cross-platform packaging/QA, UX/onboarding,
or specialist voice work. Defer a multiplayer hire until that feature is scoped.

Use a small paid trial with acceptance criteria, capped budget, repository
handoff, tests, and documentation. Have appropriate agreements cover IP
assignment, pre-existing materials, third-party licenses, confidentiality,
payment, and termination. Contractor classification depends on actual working
arrangements and jurisdiction, not merely the contract label.

Employees require a fully loaded payroll/compliance budget. Add continuing roles
only when cash runway can cover both employment and release obligations.

## 9. Legal, rights, and risk gates

- Discuss an LLC or other entity with a local attorney/CPA before contracts or
  fundraising. An LLC is not automatic tax savings or complete liability immunity.
- Keep business banking/bookkeeping separate and document any transfer or license
  of the owner's existing IP to the entity.
- Review EULA, refunds, privacy, taxes on digital sales, insurance, and hiring
  requirements in applicable jurisdictions.
- Audit direct/transitive libraries, bundled binaries, speech models/voices,
  and every redistributed dataset or publication.
- Treat [software attribution](ATTRIBUTION.md) and
  [data attribution](DATA_ATTRIBUTION.md) as starting inventories, not legal
  clearance. Verify original sources and terms, preserve required notices/license
  texts, and resolve unsupported public-domain assertions before distribution.
- Confirm commercial caching/redistribution rights and recurring costs for any
  future weather or traffic provider.

## 10. Next 90 days: proposed work, not delivery promises

1. First 30 days: cost release blockers, interview target users, prepare a demo,
   verify rights, and establish a cash budget.
2. Days 31-60: run external installation/play tests, validate pricing, and recruit
   a small educator/instructor pilot group.
3. Days 61-90: review demand, reliability, support workload, and available cash;
   assess readiness for the planned Patreon and Kickstarter launches and for
   paid early access. Launch dates depend on the respective readiness gates.

Review monthly: net receipts, refunds, cash runway, support hours, repeat usage,
and milestone completion. Expand only when both demand and delivery capacity
justify it.
