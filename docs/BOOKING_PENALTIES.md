# Monthly booking penalties

Confirmed short- and long-term bookings share the same policy for both roles:

- At least 24 hours before the agreed start: 0 points.
- Less than 24 hours before the agreed start: 1 point.
- At or after the agreed start: 2 points.
- Unaccepted posts and offers: 0 points.

The initiating account's monthly balance is capped at 3. At 3 points, posting,
proposals, new booking offers, and acceptance are blocked. Cancellation, chat,
and history remain available. Cancellation reasons and the charged amount are
saved on the existing booking. A safety reason receives the same points and
shows an advisory; it does not open an automatic report or waive a penalty.

`penalty_month` records the first day of the account's penalty month, using
Philippine time (`Asia/Manila`). All resets use
`refresh_monthly_penalties(user)` in `accounts/penalties.py`:

- When the stored month is older than the current month, reset
  `penalty_points` to 0, set `is_restricted` to false, and advance
  `penalty_month` to the current month.
- The booking guard refreshes the month before checking restrictions.
  Posting, proposals, booking offers, and direct or proposal acceptance all
  use that guard. Current-month balances of 3 or more block these actions.
- Repeated requests in the same month preserve that month's points.

Inactive accounts retain their stored values until their next request;
expired penalties are cleared before any booking action is checked. Resets
lock the user row and update these three fields together. Separate messaging
pauses, inactive status, and account suspensions remain unchanged.

No scheduled job, background process, or local PC is required. The same
request-based behavior applies to local development and cloud hosting.
