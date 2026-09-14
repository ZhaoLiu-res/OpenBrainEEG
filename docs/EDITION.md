# Standalone edition

OpenBrainEEG packages the Brainifly local workspace independently of the hosted
application. The public repository starts with a new Git history.

Included: EEG loaders and cleaning pipeline, report generation, localhost API,
React UI, file-based job/conversation/settings storage, optional model adapters,
automated tests and two attributed PhysioNet examples.

Excluded: cloud accounts, payments, subscriptions, cloud database and migration
modules, original repository history, credentials, user jobs, environments,
installed model weights and the GDF example with unresolved redistribution terms.

The runtime uses 127.0.0.1:8765 and is intended for a single local user. Default AI
is disabled; users configure their own local service or API key. Interface IP
locale detection performs a disclosed country-only lookup in auto mode and
falls back to browser language. See SYSTEM_SETTINGS.md and REPORT_ASSISTANT.md.

Public source preview only: see ../LICENSING.md for the pending code license.
