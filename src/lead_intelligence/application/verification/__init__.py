"""The Contact Verification Framework.

Public entry points: VerificationCoordinator (coordinator.py) and
VerificationProfile / default_profile (config.py). See README.md in this
folder for how the pieces fit together.

Version 1 scope only: this package implements the framework — provider
interface (application/ports/verification_provider_port.py), request/
result/report shapes, priority ordering, and coordination. It implements
no concrete provider (no NeverBounce, ZeroBounce, Kickbox, Bouncer,
Twilio Lookup, Numverify, or Abstract API integration) and no message
sending or AI — those are future tasks, each a new class implementing
EmailVerificationPort or PhoneVerificationPort.
"""
