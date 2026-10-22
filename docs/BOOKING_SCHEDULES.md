# Booking schedules

Public posts and private chat offers use the same schedule rules for Homeowners
and Kasambahay. All dates and times refer to Asia/Manila.

- Short-term: one service date, with Morning, Afternoon, Night or custom same-day
  working hours. End time must be later than start time.
- Long-term with an end date: the end date must be at least 30 calendar days
  after the start date. This is a SerbiSure listing rule, not a claim that
  RA 10361 imposes a universal minimum employment duration.
- Long-term without an end date: `end_time = null`, with daily start/end times
  and working days retained. No synthetic expiry, monthly renewal record or
  automatic completion is created.

The existing nullable `tbl_booking.end_time` represents ongoing work. No new
column or table is needed. Existing saved contracts are preserved. Pending
fixed-term listings below 30 days must be replaced with a valid schedule before
proposal or acceptance. Cancellation, starting and completion keep their
existing explicit actions.

The mobile duration picker, time selector, calendar helper and schedule errors
use the existing English/Tagalog/Bisaya localization settings. API timestamps
and enum values remain language independent.
