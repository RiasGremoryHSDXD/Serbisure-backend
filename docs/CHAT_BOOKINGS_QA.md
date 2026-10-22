# Chat bookings: local QA

No commits or remote deployment were made. Restart Django and reload the mobile app after applying the new booking and chat migrations together.

## Two authoritative paths

- **New offer in a conversation:** Either homeowner or kasambahay opens the calendar button, enters services, work setup, region/address, start/end dates, working hours/days and compensation, then sends. `POST /api/v1/booking/chat-offers/` saves a private pending booking and its linked chat message in one transaction. Retrying the same draft reuses a persisted request key. Only the addressed recipient can accept, through `PATCH /api/v1/booking/<booking_id>/accept/`.
- **Proposal on an existing post:** Apply / Offer to Hire creates a proposal against the original booking. That proposal also appears as a linked chat card. The poster responds using `PATCH /api/v1/booking/proposals/<proposal_id>/respond/`. Acceptance assigns the proposer, persists the negotiated rate and rejects competing pending proposals for that original booking.

New private conversation offers are separate engagements; they do not silently rewrite another public post or close unrelated listings. Their terms are excluded from public feeds, profile posts and recommendations. Both participants can find them under Pending/Active bookings; private terms cannot be forwarded to unrelated users through a booking-linked message.

## Manual test sequence

1. With verified local accounts, send a future **short-term** offer from homeowner to kasambahay. Use explicit work days/hours, services, location and amount. The sender sees a pending card after the save succeeds; the recipient sees Accept / Decline. Accept as the recipient, reload both conversations, then inspect both users' Active bookings. Confirm one assignment and matching stored terms.
2. Repeat in the opposite direction with a **long-term** offer initiated by kasambahay. Homeowner can accept identically. The agreed amount is monthly, and the DOLE form/signing notice remains available in booking history.
3. Create two applications against an existing public post. Accept one from its chat card as the poster. Check that the other proposal becomes rejected and cannot reopen or replace the engagement.
4. Try below-floor terms, a restricted participant, an expired schedule and a fourth same-pair short-term booking for one Philippine calendar month. Confirmation must fail with the backend explanation; the card stays unconfirmed. Try to accept the sender's own offer or another recipient's private offer; these must fail.
5. Simulate a connection failure while sending. The form remains open and the same draft can be retried without duplicate bookings/messages. On an acceptance response failure, refresh to read the database's actual status rather than inferring success from chat text.
6. Decline a private offer, reload, and verify Cancelled status. Decline a proposal and verify Rejected status. Neither can be accepted afterward.
7. Open a conversation containing old raw-string offers or confirmation phrases. They remain ordinary historic messages; the app does not invent structured terms or retroactively formalize them. Send a new structured offer if needed.
8. With empty data, check Home, Explore, Saved/Applied, every bookings tab and a new chat. Distinguish genuine empty results from loading and network errors. Booking API failures must show Retry rather than “No bookings.”
9. Tap Message on a job without submitting a proposal. This must not increment Applied. Submit an actual application through the profile/post proposal action, then refresh Applied. The list and count come from persisted pending/accepted proposals and survive reload. Saved/Applied failures show Retry and retain existing data; signing out invalidates any outstanding account-specific requests.

## Data and limits

Rates, categories, setup, schedules, location and work days/times are stored on `tbl_booking`; `tbl_booking_assignment` records the accepted partner. Chat cards read `booking_offer` snapshots from the server. Polling reads state only; it never accepts an engagement or interprets ordinary text as confirmation. All new chat timestamps are validated in Philippine time.

Stock face/household photos and invented prices, locations, dates, schedules, verification badges and five-star review fallbacks were removed from the affected mobile booking/feed views. Missing details are shown as unavailable or unrated. Category options and UI picker suggestions remain valid selectable options, not saved evidence.

Acceptance confirms an engagement in the database. It does not digitally sign a legal contract or complete Barangay registration. Those steps remain outside the automated scope.
