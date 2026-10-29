# Changelog

All notable changes, newest first.

## Unreleased

### Fixed
- **Sensors stayed unavailable after a reconnect** (2026-10-29): `online` was
  sent only once at startup, so after a dropped connection the broker's
  retained last will (`offline`) stuck while the exporter kept running.
  Discovery and `online` are now sent on every (re)connect.
- **Current Sprout Track databases** (2026-10-29): timestamps are read as
  epoch milliseconds *or* ISO 8601 strings (Sprout Track switched to ISO in
  October 2026; before, every poll failed). The *today* counters compare
  against local midnight in the DB's ISO format.
- **Crash at startup** (2026-10-29): `publish_discovery()` was called with an
  argument it doesn't take.
- **First values could be lost** (2026-10-29): the exporter now waits for the
  broker connection before publishing, and `--once` disconnects cleanly so
  its messages go out before it exits.

### Changed
- **Same Home Assistant device and entities as the original single-file
  exporter** (2026-10-29): device `Sprout Track` with identifier
  `sprouttrack_<BABY_ID>`, no `object_id`, so an existing installation keeps
  its device, entity IDs and history when it moves to this package.
  `baby_slug` in `config.yaml` is optional and no longer used.

### Under the hood
- Tested against a copy of a live database and a private broker: the package
  publishes the same discovery configs and states as the single-file
  exporter, and comes back `online` after its connection is cut.
