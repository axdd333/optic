# Optic Privacy Rights Workflow

Effective date: May 4, 2026

This workflow operationalizes the rights language in the Privacy Policy.

## Intake

Accept requests at `hello@tryoptic.app` and through an in-product form when
available. Log request time, requester identity, account ID, jurisdiction,
request type, verification status, deadline, decision, and response date.

## Request Types

- access;
- correction;
- deletion;
- portability;
- restriction;
- objection;
- consent withdrawal;
- appeal;
- opt out of sale, sharing, targeted advertising, or qualifying profiling.

## Verification

Use account login for self-service requests. Use email confirmation for
account-linked requests. Request additional proof only when needed to reduce
fraud, unauthorized access, or improper deletion.

## Timing

Target a 30-day response window for GDPR, UK GDPR, and Swiss-style requests.
Target a 45-day response window for U.S. state privacy requests. Use
extensions only when legally permitted and explain the reason.

## Execution

For access and portability, export account data, submitted content, generated
reports, subscription status, privacy choices, and major inference records
where technically feasible and legally required.

For deletion, delete or deidentify account data and User Content unless
retention is required for legal, security, fraud-prevention, subscription,
tax, dispute, or backup reasons.

For correction, update account data and allow users to correct source
material where feasible. Generated inferences may be regenerated rather than
manually edited when source data changes.

For objection, restriction, or consent withdrawal, disable the relevant
processing where required and feasible. Preserve records needed to honor the
choice.

## Denials

Permitted denial reasons include inability to verify identity, legal
retention duties, security needs, fraud prevention, trade secret risk,
disproportionate burden where allowed, or requests affecting another
person's rights.

## Appeals

Allow appeals by reply email with "Privacy Appeal" in the subject. Have a
different reviewer evaluate the appeal when feasible. Record the final
decision and reason.

## Dead Letter Queue

If a deletion, export, or correction job fails, move it to a privacy dead
letter queue. Retry with exponential backoff. Alert an owner after repeated
failure. Do not silently close a request until all required systems are
completed or a lawful exception is recorded.

## Evidence

Keep an audit record for each request, including timestamps, systems touched,
exceptions, and the final response. Do not keep more proof-of-identity data
than needed.
