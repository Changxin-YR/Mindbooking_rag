# Sandbox Provider and Virtual Finance Policy

## Scope

This change makes the existing commercial loop deployable in local and staging
environments without production credentials. Payment, payout, contract, tax,
wallet, ledger, approval, and callback paths remain the same business paths.

## Decisions

- `SANDBOX_ALIPAY` and `SANDBOX_WECHAT` are payment adapter identities. They
  share the existing signed event contract and state machine, but persist their
  channel identity in checkout and callback events.
- `SANDBOX_BANK` is the payout adapter identity. `SANDBOX_PAYOUT` remains a
  compatibility alias for existing environments and tests.
- A contract created without an explicit policy uses the versioned virtual
  policy `SANDBOX_CN_2026_V1`: author share 7000 BPS, platform share 3000 BPS,
  withholding 1000 BPS, and a zero tax-free threshold. Values are integer cents
  and BPS only.
- Contract versions persist the policy snapshot. Revenue persists the applied
  withholding and net author amount. Settlements aggregate net author amounts
  and expose gross, tax, and net totals.
- This policy is a staging simulation, not a statement of Chinese tax law. The
  API and documentation label sandbox behavior explicitly.

## Data Flow

1. Settings select a named sandbox adapter.
2. Main application wires the adapter through the existing `PaymentProvider`
   and `PayoutProvider` ports.
3. Contract creation snapshots the virtual policy into its first version.
4. Revenue calculation reads the active contract version and applies the tax
   snapshot with integer arithmetic.
5. Settlement remains idempotent and records the resulting net amount.

## Verification

- Unit tests cover all named adapters, signatures, callback states, and alias
  compatibility.
- Finance tests cover policy snapshots, tax arithmetic, idempotent revenue and
  settlement behavior.
- Existing full regression, migration SQL generation, Compose smoke, and SQL
  commercial E2E remain release gates.

