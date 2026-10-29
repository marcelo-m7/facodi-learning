# FACODI Curriculum Connector — least-privilege rollout

## Security contract

The `facodi-curriculum` Edge Function calls the Odoo 19 JSON-2 API with an
API key stored exclusively in Supabase secrets. A technical principal must
never be an eLearning Manager, a system administrator or an administrator
of Sales, Accounting, Projects or any other business app.

This module defines `facodi_learning.group_facodi_curriculum_api_reader`
and model/record ACLs for exactly the data classes used by the connector:

| Odoo model | Model ACL | Record rule |
| --- | --- | --- |
| `facodi.learning.curriculum.reference` | read only | validated and website-published |
| `facodi.learning.curriculum.unit` | read only | belongs to validated and website-published reference |
| `facodi.learning.curriculum.coverage` | read only | approved and linked to a published curriculum and course |
| `slide.channel` | read only | active, published and website-published |

The group intentionally implies no editor, officer, manager or admin group.
Do not interpret an Odoo model ACL as a global deny policy: access in Odoo
is additive across groups, and an internal-user baseline may grant unrelated
rights. Therefore the integration principal must not carry any additional
business, editor or administrator groups. The published-data rules are a
defence-in-depth layer for the API projection, not a substitute for its
explicit `search_read` domains.

## Production migration — *not performed by this change*

1. Obtain a current, auditable snapshot of the principal's assigned roles
   and integrations using its API key. Check whether any non-curricular
   workflows rely on this principal; move those to separate named service
   accounts before changing its groups.
2. Install and test this addon revision in a **non-production Odoo 19
   database**, including the `TestCurriculumApiReader` suite. Confirm a
   user having only `base.group_user` plus this reader group can query
   the four models via JSON-2, but cannot create/write/delete or read
   unpublished/unedited information.
3. In staging, provision a **new dedicated read-only principal** with this
   group and only the minimal user-type group required by Odoo. Never reuse
   an admin API key for read-only access. Generate a new API key and add it
   to a temporary/staging function secret without placing it in GitHub,
   local env files or frontend variables.
4. Validate `facodi-curriculum` with a real authenticated Supabase JWT:
   HTTP 200, correct counts, correct `X-Request-Id`, no unpublished or
   proposed coverage in the response and no Odoo access-denied events.
   Verify 401 without JWT; 403/denial on write attempts must be tested
   only against **staging**, never production.
5. Following staging approval, install the module via the normal
   `facodi-deploy` pin and migration process. Provision a separate
   read-only production API key and update only the Edge Function's
   `ODOO_SECRET` secret in an orchestrated cutover. Check all consumers
   before disabling the previous credential.
6. Confirm HTTP 200 in the authenticated Atlas for all published references,
   then revoke/rotate any key that was exposed or is no longer in use.
   Restrict and audit administrative accounts separately.

**Rollback:** retain the currently functioning Odoo integration only while
the migration is assessed; if read access fails, restore the previous
approved connector configuration through secrets management and audit the
difference. Do not grant the new reader user manager/admin rights as a
workaround. The addon itself does not create, update or reassign a real
`res.users` record.

No service account credentials or account-identifying details belong in
a public GitHub issue, commit, fixture or logs.
