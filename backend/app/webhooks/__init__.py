"""Outbound webhook subsystem: event publisher for admin-subscribed
`webhook_endpoints` (03-API-SPEC.md section 3) -- distinct from the
per-employee `notification_bindings` "webhook" channel in app/notify/, which
is a single URL bound by one employee to receive their own notifications.
"""
