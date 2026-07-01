import type { ManualTransactionInput } from '../types/transaction'

// ── Unified sample dataset ───────────────────────────────────────────────────
// A SINGLE simulation that feeds every kind of activity the engine understands —
// legitimate background traffic, a cash-driven AML layering chain, and a circular
// fraud ring — all in one stream. There is intentionally no per-pattern scenario
// picker: the unified feed exercises fan-out, layering, structuring, cash
// in/out and cycle detection together, the way real traffic arrives mixed.
//
// `t(secondsFromBase)` lets callers anchor the timeline either to "now" (live
// empty-state generation) or to a fixed base (the editable left-panel default).
export function buildSampleTransactions(t: (s: number) => string): ManualTransactionInput[] {
  return [
    // ── Legitimate background traffic (low value, varied rails) ──────────────
    { from_account: 'ACC_1001', to_account: 'ACC_2001', amount: 15000, payment_rail: 'UPI',  timestamp: t(0) },
    { from_account: 'ACC_2001', to_account: 'ACC_3001', amount: 8500,  payment_rail: 'IMPS', timestamp: t(30) },
    { from_account: 'ACC_1001', to_account: 'ACC_4001', amount: 25000, payment_rail: 'RTGS', timestamp: t(55) },
    { from_account: 'ACC_3001', to_account: 'ACC_5001', amount: 7200,  payment_rail: 'NEFT', timestamp: t(80) },

    // ── Cash-driven AML layering (cash-in → layer → cash-out) ────────────────
    { from_account: 'CASH_SOURCE', to_account: 'ACC_L01', amount: 500000, payment_rail: 'CASH', timestamp: t(110) },
    { from_account: 'ACC_L01',     to_account: 'ACC_L02', amount: 300000, payment_rail: 'UPI',  timestamp: t(140) },
    { from_account: 'ACC_L01',     to_account: 'ACC_L03', amount: 195000, payment_rail: 'IMPS', timestamp: t(165) },
    { from_account: 'ACC_L02',     to_account: 'ACC_L04', amount: 290000, payment_rail: 'NEFT', timestamp: t(195) },
    { from_account: 'ACC_L03',     to_account: 'ACC_L04', amount: 188000, payment_rail: 'UPI',  timestamp: t(220) },
    { from_account: 'ACC_L04',     to_account: 'CASH_EXIT', amount: 460000, payment_rail: 'CASH', timestamp: t(255) },

    // ── Circular fraud ring (funds return to the originator) ─────────────────
    { from_account: 'ACC_ALPHA',   to_account: 'ACC_BETA',    amount: 100000, payment_rail: 'UPI', timestamp: t(290) },
    { from_account: 'ACC_BETA',    to_account: 'ACC_GAMMA',   amount: 100000, payment_rail: 'UPI', timestamp: t(315) },
    { from_account: 'ACC_GAMMA',   to_account: 'ACC_DELTA',   amount: 100000, payment_rail: 'UPI', timestamp: t(340) },
    { from_account: 'ACC_DELTA',   to_account: 'ACC_EPSILON', amount: 100000, payment_rail: 'UPI', timestamp: t(365) },
    { from_account: 'ACC_EPSILON', to_account: 'ACC_ALPHA',   amount: 100000, payment_rail: 'UPI', timestamp: t(390) },
  ]
}

// Static, editable default for the left-panel JSON editor (fixed timeline).
export const UNIFIED_SAMPLE_JSON = JSON.stringify(
  buildSampleTransactions(s => new Date(Date.parse('2026-05-15T08:00:00') + s * 1000).toISOString()),
  null,
  2,
)
