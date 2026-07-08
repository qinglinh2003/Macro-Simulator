"""Accounting as a structural primitive (spec §7.6, §8.2).

All money movement in the kernel goes through ``Ledger.transfer``. Agents get
NO direct write access to balances; they can only read via ``balance()``. As a
result the accounting invariants A1 (double entry) and M0 (money conservation)
cannot be violated *by construction* -- the per-tick ``assert_conserved`` check
(spec §7.2 hard gate) is a redundant safety net, not the primary defense.

Scope: the closed monetary kernel. The only financial instrument is money
(deposits), so the ledger tracks exactly one signed scalar per agent. The good
is a real (outside) item held as inventory -- it is NOT money and is NOT tracked
here (it is not conserved; production creates it, consumption destroys it).
"""

from __future__ import annotations

from typing import Dict, Hashable, Mapping


class OverdraftError(Exception):
    """Raised when an agent tries to spend money it does not have (A4).

    In the kernel there is no bank credit (M2 inactive), so every spend is hard
    capped by cash on hand. A would-be buyer with no money simply fails to
    transact -- this is where disequilibrium enters (spec §0-iii, A4).
    """


class ConservationError(Exception):
    """Raised when total money drifts from its genesis value M (M0 / A1).

    If this ever fires, the plumbing is broken: some transfer created or
    destroyed money. Per spec §7.5 this is the one thing that must never happen
    -- it is always a bug, never economics.
    """


class Ledger:
    """Single source of truth for every agent's deposits and loan debt.

    Invariant: net worth ΣD − ΣL = M every tick (A5). Before any credit exists this
    is exactly M0 (ΣD = M). Three mutators, all atomic (both legs succeed or the call
    raises before touching state): ``transfer`` moves deposits (net worth invariant);
    ``create_loan`` / ``repay`` move deposits and loans together (net worth invariant,
    broad money endogenous). Each rejects the ways value could leak (negative amounts,
    overdrafts, over-repayment). Interest is an ordinary ``transfer``.
    """

    def __init__(self, initial_balances: Mapping[Hashable, float], *, rel_tol: float = 1e-9):
        """Seed the ledger with genesis endowments (spec §6.2).

        Args:
            initial_balances: agent id -> starting money. Total sets M, conserved
                forever (M0). All must be >= 0 (A4).
            rel_tol: relative tolerance for the conservation check. Float transfers
                (``a-amt`` and ``b+amt``) do not re-sum to ``a+b`` bit-exactly, so
                drift is compared against ``rel_tol * M`` rather than == 0.
        """
        for aid, bal in initial_balances.items():
            if bal < 0:
                raise ValueError(f"initial balance for {aid!r} is negative ({bal}); violates A4")
        self._bal: Dict[Hashable, float] = dict(initial_balances)
        # Loans (v3): debt owed by each agent (>= 0). Zero for everyone at genesis,
        # so A5 (ΣD − ΣL = M) reduces to M0 (ΣD = M) until the first loan is made.
        self._loans: Dict[Hashable, float] = {aid: 0.0 for aid in initial_balances}
        self._M: float = sum(initial_balances.values())   # base money (conserved net worth)
        # v12.3: Σ book value of bonds a BANK bought with reserves (money-creating: the Treasury is credited spendable
        # funds while the bank swaps reserves for a bond asset). Like a loan, this raises ΣD without a matching ΣL,
        # so the A5 gate becomes ΣD − ΣL − _bank_securities = M. 0 unless a bank buys a bond ⇒ bit-identical.
        self._bank_securities: float = 0.0
        # Accounts allowed to hold a NEGATIVE deposit balance (v4): the bank, whose equity
        # goes negative when bad-debt writeoffs exceed its capital = insolvency, a real
        # observed state, not an A4 violation. Populated by the economy.
        self._may_be_negative: set = set()
        # v11.4: the RESERVE overlay (None ⇒ off ⇒ every transfer behaves exactly as before, bit-identical).
        # When active, `transfer` settles reserves between the payer's and payee's settlement nodes (RTGS).
        # A pure second layer -- deposit accounting and the A5 gate above are untouched.
        self._reserves: Dict[Hashable, float] | None = None
        self._reserve_min: Dict[Hashable, float] | None = None   # per-tick intraday minima (peak overdrafts)
        self._resolver = None                 # account_id -> settlement node (bank / CLEARING / CB)
        self._reserve_M: float = 0.0          # conserved reserve total (base money)
        self._rel_tol = rel_tol
        # Absolute tolerance scaled to the money stock; floored so an all-zero or
        # tiny economy still has a sane epsilon.
        self._abs_tol = max(self._rel_tol * abs(self._M), 1e-9)

    # -- read-only access (the only window agents get) ----------------------

    def balance(self, agent_id: Hashable) -> float:
        """Current money (deposits) held by ``agent_id`` (read-only)."""
        return self._bal[agent_id]

    def has_account(self, agent_id: Hashable) -> bool:
        """Whether ``agent_id`` is a live ledger account (v4 removes bankrupt firms; their ids may linger in
        higher-level maps like the economy's bank assignment)."""
        return agent_id in self._bal

    def debt(self, agent_id: Hashable) -> float:
        """Current loan debt owed by ``agent_id`` (v3; 0 before any borrowing)."""
        return self._loans[agent_id]

    @property
    def total_money(self) -> float:
        """Live sum of deposits = broad money. Constant (=M) until credit exists;
        an *endogenous* series once loans are made (spec A5, §12)."""
        return sum(self._bal.values())

    @property
    def total_credit(self) -> float:
        """Live sum of loan debt = outstanding credit (v3)."""
        return sum(self._loans.values())

    @property
    def bank_securities(self) -> float:
        """v12.3: Σ book value of bank-held bonds bought via money creation (see `bank_buy_bond_with_reserves`)."""
        return self._bank_securities

    @property
    def net_worth(self) -> float:
        """System net financial worth = broad money − credit − bank securities. Must equal M (A5). The
        `_bank_securities` term is 0 until a bank buys a bond with reserves (money creation) ⇒ bit-identical."""
        return self.total_money - self.total_credit - self._bank_securities

    @property
    def genesis_money(self) -> float:
        """The conserved base money M fixed at construction (M0 / A5)."""
        return self._M

    def snapshot(self) -> Dict[Hashable, float]:
        """Copy of all balances, e.g. for logging the money distribution (§6.5)."""
        return dict(self._bal)

    # -- the one and only mutator ------------------------------------------

    def transfer(self, src: Hashable, dst: Hashable, amount: float) -> None:
        """Move ``amount`` of money from ``src`` to ``dst``, atomically.

        This is the single channel for all money movement (wages, purchases,
        dividends). Debits one account and credits another in one operation, so
        A1 holds by construction. Rejects the two leaks:
          * ``amount < 0`` -- would reverse the flow / create money (ValueError).
          * ``src`` cannot cover ``amount`` -- overdraft, no credit in the kernel
            (OverdraftError / A4).
        A zero transfer is a permitted no-op (a rationed-to-zero trade is normal).
        """
        if amount < 0:
            raise ValueError(f"transfer amount must be >= 0, got {amount} ({src!r} -> {dst!r})")
        if src not in self._bal:
            raise KeyError(f"unknown source account {src!r}")
        if dst not in self._bal:
            raise KeyError(f"unknown destination account {dst!r}")
        if amount == 0.0:
            return
        # A4: hard cash cap. Allow a hair of float slack so a spend of exactly the
        # full balance (computed via float arithmetic elsewhere) is not spuriously
        # rejected, but a genuine overdraft raises. Accounts flagged `allow_negative`
        # (the bank's equity; v9 the GOV account issuing outside money) are exempt --
        # a deficit-spending government drives its deposit negative (= government debt).
        if src not in self._may_be_negative and self._bal[src] - amount < -self._abs_tol:
            raise OverdraftError(
                f"{src!r} cannot transfer {amount}; balance is {self._bal[src]} (A4 / no credit in kernel)"
            )
        self._bal[src] -= amount
        self._bal[dst] += amount
        if self._reserves is not None:            # v11.4 RTGS overlay: settle reserves between the two nodes
            self._settle_reserves(src, dst, amount)

    # -- v11.4 reserve overlay (RTGS settlement) ---------------------------
    # A SECOND accounting layer for base money. Deposit accounting above is untouched (its A5 gate holds
    # exactly as before); reserves are settled node-to-node on every `transfer`, so they conserve by
    # construction (Σ reserves = M, the base-money total). `create_loan`/`repay`/`write_off` need NO settlement:
    # they move a deposit and a loan (or the bank's own capital) TOGETHER at the same bank, preserving the
    # per-bank identity R_k = capital_k + deposits_k − loans_k without any reserve movement.

    def enable_reserves(self, resolver, initial_reserves: Mapping[Hashable, float]) -> None:
        """Activate the reserve overlay. `resolver(account_id) -> node` maps each account to its settlement
        node (a bank, CLEARING, or the CB); `initial_reserves` seeds node -> reserves (Σ = base money M)."""
        self._resolver = resolver
        self._reserves = dict(initial_reserves)
        self._reserve_M = sum(initial_reserves.values())

    def _settle_reserves(self, src: Hashable, dst: Hashable, amount: float) -> None:
        ns, nd = self._resolver(src), self._resolver(dst)
        if ns == nd:                              # same bank ⇒ an internal book entry, no reserves move
            return
        rs = self._reserves.get(ns, 0.0) - amount
        self._reserves[ns] = rs
        self._reserves[nd] = self._reserves.get(nd, 0.0) + amount
        if self._reserve_min is not None and rs < self._reserve_min.get(ns, 0.0):
            self._reserve_min[ns] = rs            # v11.4: track each node's INTRADAY minimum (peak overdraft)

    def reset_intraday(self, nodes) -> None:
        """v11.4: start a new tick's intraday reserve tracking. `reserve_min(node)` then records the lowest
        reserve balance `node` touches during the tick -- the peak intraday overdraft that intraday funding
        (interbank / CB) must cover."""
        if self._reserves is None:
            return
        self._reserve_min = {n: self._reserves.get(n, 0.0) for n in nodes}

    def reserve_min(self, node: Hashable) -> float:
        return 0.0 if self._reserve_min is None else self._reserve_min.get(node, 0.0)

    def move_reserves(self, src_node: Hashable, dst_node: Hashable, amount: float) -> None:
        """v11.4: move `amount` reserves src→dst directly in the overlay -- NOT a deposit payment (no `transfer`),
        e.g. relocating a migrating customer's reserve backing when its bank fails, or an interbank reserve loan.
        `amount` may be negative (reverses direction). Conserves Σ reserves by construction."""
        if self._reserves is None or amount == 0.0:
            return
        self._reserves[src_node] = self._reserves.get(src_node, 0.0) - amount
        self._reserves[dst_node] = self._reserves.get(dst_node, 0.0) + amount

    def issue_reserves(self, node: Hashable, amount: float) -> None:
        """v12.4: the CENTRAL BANK CREATES base money -- credit `node`'s reserves AND raise the conserved total
        `_reserve_M` by the same amount, so the gate `Σ reserves = _reserve_M` stays exact BY CONSTRUCTION. The
        deposit ledger (ΣD − ΣL − _bank_securities = M) is untouched -- reserves are a separate overlay. This is
        the un-consolidated CB acting as the source/sink of base money (OMO / QE / LoLR). `amount` may be negative
        (= retire). Off (overlay disabled) ⇒ no-op ⇒ bit-identical."""
        if self._reserves is None or amount == 0.0:
            return
        self._reserves[node] = self._reserves.get(node, 0.0) + amount
        self._reserve_M += amount

    def retire_reserves(self, node: Hashable, amount: float) -> None:
        """v12.4: the CB DESTROYS base money -- the inverse of `issue_reserves` (drains `node`'s reserves and lowers
        the conserved total). Used by OMO to make reserves SCARCE ⇒ the latent interbank market binds."""
        self.issue_reserves(node, -amount)

    def reserves(self, node: Hashable) -> float:
        """Reserve balance of a settlement node (bank / CLEARING / CB). 0 if the overlay is off."""
        return 0.0 if self._reserves is None else self._reserves.get(node, 0.0)

    @property
    def total_reserves(self) -> float:
        return 0.0 if self._reserves is None else sum(self._reserves.values())

    def assert_reserves_conserved(self) -> None:
        """Halt if the reserve total drifts from its base-money value `_reserve_M` (a second hard gate; v11.4).
        Settlement moves reserves node-to-node (Σ invariant by construction); v12.4 issue/retire move Σreserves and
        `_reserve_M` together (also exact by construction). The residual is float-summation error, whose MAGNITUDE
        scales with the genesis reserve stock, NOT the current `_reserve_M` -- so the tolerance keys off the stable
        deposit base money `_M` (≈ genesis reserves), else OMO draining `_reserve_M` small would shrink the gate
        below normal float error and trip on a non-error (v12.4)."""
        if self._reserves is None:
            return
        scale = max(abs(self._reserve_M), abs(self._M), self.total_money, 1.0)
        tol = max(self._rel_tol * scale, 1e-9)
        drift = abs(self.total_reserves - self._reserve_M)
        if drift > tol:
            raise ConservationError(
                f"reserves not conserved (v11.4): Σreserves={self.total_reserves!r} vs M={self._reserve_M!r} "
                f"(drift={drift:.3e} > tol={tol:.3e})"
            )

    # -- money creation / destruction (v3, M2) -----------------------------
    # The ONLY paths that change the money stock. Each moves deposits and loans
    # TOGETHER, so ΣD − ΣL (net worth, A5) is invariant by construction -- exactly
    # as ``transfer`` keeps ΣD invariant. Interest is NOT here: it is an ordinary
    # ``transfer`` (redistributes deposits, net worth untouched).

    def create_loan(self, borrower: Hashable, amount: float) -> None:
        """Bank lends ``amount`` to ``borrower``: a matching deposit is CREATED (M2).

        No source account -- this is where broad money grows. Borrower's deposit and
        debt both rise by ``amount``, so ΣD − ΣL is unchanged (A5). The bank's
        offsetting loan-asset / deposit-liability entries need not be tracked here
        for the gate to hold (§12.2: reserves carry M; bank equity not load-bearing).
        """
        if amount < 0:
            raise ValueError(f"loan amount must be >= 0, got {amount} (borrower {borrower!r})")
        if borrower not in self._bal:
            raise KeyError(f"unknown borrower account {borrower!r}")
        if amount == 0.0:
            return
        self._bal[borrower] += amount
        self._loans[borrower] += amount

    def bank_buy_bond_with_reserves(self, bank_id: Hashable, fiscal_id: Hashable, amount: float) -> None:
        """v12.3: a BANK buys `amount` of newly-issued government bonds with RESERVES (the strong-sterilisation
        channel). Three legs, all A5-safe under the extended gate ΣD − ΣL − _bank_securities = M:
          (1) reserves drain bank → CB  (`move_reserves`): the bank ships base money to the CB ⇒ Σ bank reserves
              FALLS (this is the sterilisation the whole securities arc was built for);
          (2) the Treasury is CREDITED spendable funds  (`_bal[fiscal] += amount`): it financed `amount` of its
              deficit by selling the bond, raising ΣD with no matching ΣL (money creation, like a loan);
          (3) `_bank_securities += amount`  offsets (2) so the gate holds exactly.
        The bank's bond ASSET is tracked by the economy (`_bonds`); its `economic_capital = balance + bonds@market`
        is preserved at purchase. Over the debt STOCK this parks the deficit in bonds instead of letting it flood
        reserves ⇒ reserves stay near M₀ (scarce) ⇒ the interbank keystone can finally bind."""
        if amount <= 0.0:
            return
        self.move_reserves(bank_id, "CB", amount)     # (1) reserves bank → CB (sterilise)
        self._bal[fiscal_id] += amount                # (2) Treasury financed (money created)
        self._bank_securities += amount               # (3) offset ⇒ ΣD − ΣL − _bank_securities invariant

    def bank_redeem_bond(self, bank_id: Hashable, fiscal_id: Hashable, amount: float) -> None:
        """v12.3: a bank-held bond MATURES (or is sold back to the Treasury). Reverses
        `bank_buy_bond_with_reserves`: the Treasury pays face (`_bal[fiscal] -= amount`, deepening its debt if it
        has no cash -- outside money), the money is DESTROYED against the security (`_bank_securities -= amount`),
        and reserves flow CB → bank (`move_reserves` back). A5-safe (both ΣD and _bank_securities fall by amount)."""
        if amount <= 0.0:
            return
        self._bal[fiscal_id] -= amount
        self._bank_securities -= amount
        self.move_reserves("CB", bank_id, amount)     # reserves CB → bank (un-sterilise on redemption)

    def repay(self, borrower: Hashable, amount: float) -> None:
        """Borrower repays principal ``amount``: deposit and debt both fall (broad
        money shrinks). Guards: cannot repay more than owed, nor more than cash on
        hand (A4). Both money and debt destroyed together, so A5 holds."""
        if amount < 0:
            raise ValueError(f"repay amount must be >= 0, got {amount} (borrower {borrower!r})")
        if borrower not in self._bal:
            raise KeyError(f"unknown borrower account {borrower!r}")
        if amount == 0.0:
            return
        if amount > self._loans[borrower] + self._abs_tol:
            raise ValueError(
                f"{borrower!r} cannot repay {amount}; debt is {self._loans[borrower]}"
            )
        if self._bal[borrower] - amount < -self._abs_tol:
            raise OverdraftError(
                f"{borrower!r} cannot repay {amount} from deposits {self._bal[borrower]} (A4)"
            )
        self._bal[borrower] -= amount
        self._loans[borrower] -= amount

    def transfer_debt(self, src_borrower: Hashable, dst_borrower: Hashable, amount: float) -> None:
        """Move an existing loan obligation from one account to another.

        Demographic household splitting/merging moves people between household
        accounts.  Their person-level debt claim must move with them, while the
        system-wide loan stock stays unchanged.  This is a pure reassignment of
        the borrower account: ΣL is invariant, deposits are untouched, and A5 is
        therefore unchanged.
        """
        if amount < 0:
            raise ValueError(f"debt transfer amount must be >= 0, got {amount}")
        if src_borrower not in self._loans:
            raise KeyError(f"unknown source borrower {src_borrower!r}")
        if dst_borrower not in self._loans:
            raise KeyError(f"unknown destination borrower {dst_borrower!r}")
        if amount == 0.0:
            return
        if amount > self._loans[src_borrower] + self._abs_tol:
            raise ValueError(
                f"{src_borrower!r} cannot transfer {amount}; debt is {self._loans[src_borrower]}"
            )
        self._loans[src_borrower] -= amount
        self._loans[dst_borrower] += amount

    # -- bad-debt writeoff & agent lifecycle (v4, firm entry/exit) ----------

    def write_off(self, borrower: Hashable, bank: Hashable, amount: float) -> None:
        """Cancel uncollectable debt on a bankrupt borrower; the BANK's equity absorbs
        the loss (§13 / PLAN_v4). Conserves A5: loans[borrower]-=amount (net worth +amt)
        AND deposits[bank]-=amount (net worth -amt). The created money stays in circulation
        (broad money unchanged); the bank is poorer. The bank's deposits MAY go negative
        here (equity exhausted -> insolvency), which is allowed and observed."""
        if amount < 0:
            raise ValueError(f"writeoff amount must be >= 0, got {amount}")
        if borrower not in self._loans:
            raise KeyError(f"unknown borrower {borrower!r}")
        if bank not in self._bal:
            raise KeyError(f"unknown bank {bank!r}")
        if amount == 0.0:
            return
        if amount > self._loans[borrower] + self._abs_tol:
            raise ValueError(f"cannot write off {amount}; {borrower!r} debt is {self._loans[borrower]}")
        self._loans[borrower] -= amount
        self._bal[bank] -= amount      # bank equity absorbs; may go negative (insolvency)

    def add_account(self, agent_id: Hashable) -> None:
        """Register a new agent (v4 firm entry) with 0 deposits and 0 debt. Money must
        be funded via a subsequent ``transfer`` from an existing account (never created),
        so M is unchanged."""
        if agent_id in self._bal:
            raise ValueError(f"account {agent_id!r} already exists")
        self._bal[agent_id] = 0.0
        self._loans[agent_id] = 0.0

    def remove_account(self, agent_id: Hashable) -> None:
        """Remove a dead agent's account (v4 firm exit). Must be 0 deposits and 0 debt so
        removal changes no sum (A5 intact)."""
        if abs(self._bal.get(agent_id, 0.0)) > self._abs_tol:
            raise ValueError(f"cannot remove {agent_id!r}: nonzero deposits {self._bal[agent_id]}")
        if abs(self._loans.get(agent_id, 0.0)) > self._abs_tol:
            raise ValueError(f"cannot remove {agent_id!r}: nonzero debt {self._loans[agent_id]}")
        self._bal.pop(agent_id, None)
        self._loans.pop(agent_id, None)
        self._may_be_negative.discard(agent_id)

    def allow_negative(self, agent_id: Hashable) -> None:
        """Exempt an account (the bank) from the A4 non-negativity gate -- its equity may
        go negative (insolvency)."""
        self._may_be_negative.add(agent_id)

    # -- the redundant hard gate (spec §7.2, §6.3 Phase 5) ------------------

    def assert_conserved(self) -> None:
        """Halt the run if net financial worth has drifted from M (A5).

        The gate is ΣD − ΣL = M (§A5). With no credit (ΣL = 0) this is exactly M0
        (ΣD = M), so v1/v2 behavior is unchanged. Tolerance scales with the *larger*
        of M and broad money, since float error grows with balance magnitude once
        credit inflates ΣD. Raises ConservationError on drift.
        """
        tol = max(self._rel_tol * max(abs(self._M), self.total_money), 1e-9)
        drift = abs(self.net_worth - self._M)
        if drift > tol:
            raise ConservationError(
                f"net worth not conserved (A5): ΣD−ΣL={self.net_worth!r} vs M={self._M!r} "
                f"(broad money ΣD={self.total_money!r}, credit ΣL={self.total_credit!r}; "
                f"drift={drift:.3e} > tol={tol:.3e})"
            )

    def assert_non_negative(self) -> None:
        """Halt if any balance went negative (A4). Complements the overdraft guard.
        Accounts in ``_may_be_negative`` (the bank, whose equity may be wiped out by
        writeoffs) are exempt -- their negativity is insolvency, an observed state."""
        for aid, bal in self._bal.items():
            if aid in self._may_be_negative:
                continue
            if bal < -self._abs_tol:
                raise OverdraftError(f"{aid!r} has negative balance {bal} (A4 violated)")
