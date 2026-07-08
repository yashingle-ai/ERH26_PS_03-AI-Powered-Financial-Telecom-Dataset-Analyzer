"""Benign + planted-fraud activity generation (research/12 §8.1, step 2-3).

Produces three raw streams (bank transactions, CDR rows, IPDR rows) plus a
ground-truth manifest of the planted suspicious scenarios. Because every fraud
scenario is planted deliberately, the ground truth gives us *free labels* to
measure true-vs-false positives later (NFR-3).

Planted scenarios (research/06 §11, config/scoring_rules.yaml):
- structuring            : many transfers just below the reporting threshold
- rapid_in_out           : credit followed by near-total debit within minutes
- layering               : funds hop across several accounts quickly
- circular_flow          : A -> B -> C -> A money loop
- mule_account           : high fan-in then rapid forwarding
- call_transfer_coincidence : call + IP session + transfer within window W (the
                              signature fusion evidence, FR-9)
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .config import Tier
from .population import Person

IST = timezone(timedelta(hours=5, minutes=30))
BASE = datetime(2026, 6, 1, 0, 0, tzinfo=IST)

CELL_TOWERS = [
    ("Andheri-E, Mumbai", "404-20-1122-3344"),
    ("Koramangala, Bengaluru", "404-45-2233-4455"),
    ("Connaught Place, Delhi", "404-10-3344-5566"),
    ("Salt Lake, Kolkata", "404-31-4455-6677"),
    ("T Nagar, Chennai", "404-40-5566-7788"),
]
MODES = ["UPI", "IMPS", "NEFT", "RTGS"]
REPORTING_THRESHOLD = 1_000_000  # INR 10 lakh (mirrors config/scoring_rules.yaml)


class ActivityGenerator:
    def __init__(self, people: list[Person], tier: Tier, seed: int = 42):
        self.people = people
        self.tier = tier
        self.rng = random.Random(seed + 7)
        self.bank_txns: list[dict] = []
        self.cdr_rows: list[dict] = []
        self.ipdr_rows: list[dict] = []
        self.ground_truth: list[dict] = []
        self._utr = 100000000000

    # ---- helpers -------------------------------------------------------------
    def _rand_dt(self) -> datetime:
        secs = self.rng.randint(0, self.tier.days * 86400 - 1)
        return BASE + timedelta(seconds=secs)

    def _next_utr(self) -> str:
        self._utr += self.rng.randint(1, 97)
        return str(self._utr)

    def _tower(self):
        return self.rng.choice(CELL_TOWERS)

    @staticmethod
    def _ids(persons):
        """Participant identifiers for ground-truth evaluation."""
        accounts, phones = [], []
        for p in persons:
            accounts += [a.account_no for a in p.accounts]
            phones += list(p.phones)
        return {"accounts": accounts, "phones": phones}

    def _add_txn(self, account, holder, dt, amount, direction, counterparty_label,
                 mode, upi_id=None, ref=None):
        ref = ref or self._next_utr()
        if mode == "UPI" and upi_id:
            narration = f"UPI/{upi_id}/{counterparty_label}/{ref}"
        else:
            narration = f"{mode}/{counterparty_label}/{ref}"
        self.bank_txns.append({
            "account_no": account.account_no,
            "bank_name": account.bank_name,
            "ifsc": account.ifsc,
            "account_holder": holder,
            "txn_dt": dt,
            "narration": narration,
            "debit": amount if direction == "DEBIT" else None,
            "credit": amount if direction == "CREDIT" else None,
            "ref_no": ref,
            "mode": mode,
        })
        return ref

    def _add_transfer(self, payer: Person, payee: Person, amount, dt, mode=None):
        """Double-entry transfer between two people (DEBIT payer, CREDIT payee)."""
        mode = mode or self.rng.choice(MODES)
        payer_acc = self.rng.choice(payer.accounts)
        payee_acc = self.rng.choice(payee.accounts)
        ref = self._add_txn(payer_acc, payer.name, dt, amount, "DEBIT",
                            payee.name, mode, payee_acc.upi_id)
        self._add_txn(payee_acc, payee.name, dt, amount, "CREDIT",
                      payer.name, mode, payer_acc.upi_id, ref=ref)
        return ref

    def _add_call(self, caller: Person, caller_phone, callee_phone, dt, duration, ctype="MOC"):
        loc, cell = self._tower()
        self.cdr_rows.append({
            "calling_number": caller_phone,
            "called_number": callee_phone,
            "call_dt": dt,
            "duration_sec": duration,
            "call_type": ctype,
            "imei": caller.imei,
            "imsi": caller.imsi,
            "cell_id": cell,
            "tower_location": loc,
        })

    def _rand_ipv4(self, first_lo=14, first_hi=223):
        r = self.rng
        return f"{r.randint(first_lo, first_hi)}.{r.randint(0,255)}.{r.randint(0,255)}.{r.randint(1,254)}"

    def _add_session(self, person: Person, phone, start, end):
        ip = self.rng.choice(person.home_ip_pool)
        self.ipdr_rows.append({
            "subscriber_msisdn": phone,
            "private_ip": f"10.{self.rng.randint(0,255)}.{self.rng.randint(0,255)}.{self.rng.randint(1,254)}",
            "public_ip": ip,
            "source_port": self.rng.randint(1024, 65535),
            "session_start": start,
            "session_end": end,
            "bytes_up": self.rng.randint(1_000, 5_000_000),
            "bytes_down": self.rng.randint(10_000, 50_000_000),
            "dest_ip": self._rand_ipv4(),
            "imei": person.imei,
        })
        return ip

    # ---- benign activity -----------------------------------------------------
    def generate_benign(self):
        for p in self.people:
            others = [q for q in self.people if q is not p]
            for phone in p.phones:
                for _ in range(self.tier.calls_per_phone):
                    q = self.rng.choice(others)
                    self._add_call(p, phone, self.rng.choice(q.phones), self._rand_dt(),
                                   self.rng.randint(20, 900),
                                   self.rng.choice(["MOC", "MOC", "MTC", "SMS-O"]))
                for _ in range(self.tier.sessions_per_phone):
                    start = self._rand_dt()
                    self._add_session(p, phone, start, start + timedelta(minutes=self.rng.randint(1, 120)))
            for acc in p.accounts:
                for _ in range(self.tier.txns_per_account):
                    q = self.rng.choice(others)
                    amt = round(self.rng.uniform(100, 50_000), 2)
                    direction = self.rng.choice(["DEBIT", "CREDIT"])
                    self._add_txn(acc, p.name, self._rand_dt(), amt, direction,
                                  q.name, self.rng.choice(MODES),
                                  self.rng.choice(q.accounts).upi_id)

    # ---- planted fraud -------------------------------------------------------
    def generate_fraud(self):
        idx = 0
        pool = list(self.people)
        self.rng.shuffle(pool)
        for ring in range(self.tier.n_fraud_rings):
            members = pool[idx: idx + 5]
            idx += 5
            if len(members) < 5:
                break
            organizer, launderer, mule1, mule2, mule3 = members
            for person, role in [(organizer, "organizer"), (launderer, "launderer"),
                                 (mule1, "mule"), (mule2, "mule"), (mule3, "mule")]:
                person.role = role
                person.fraud_ring = ring
            t0 = self._rand_dt()

            self._plant_call_transfer_coincidence(ring, organizer, launderer, t0)
            self._plant_structuring(ring, mule1, t0 + timedelta(hours=2))
            self._plant_rapid_in_out(ring, launderer, mule2, t0 + timedelta(hours=5))
            self._plant_layering(ring, [organizer, launderer, mule1, mule2, mule3],
                                 t0 + timedelta(hours=8))
            self._plant_circular_flow(ring, [mule1, mule2, mule3], t0 + timedelta(hours=12))

    def _plant_call_transfer_coincidence(self, ring, organizer, launderer, t):
        """Signature evidence: call + online(IP) + transfer within window W (FR-9)."""
        caller_phone = organizer.phones[0]
        callee_phone = launderer.phones[0]
        self._add_call(organizer, caller_phone, callee_phone, t, self.rng.randint(60, 300), "MOC")
        sess_start = t - timedelta(minutes=3)
        ip = self._add_session(launderer, callee_phone, sess_start, t + timedelta(minutes=15))
        transfer_t = t + timedelta(minutes=self.rng.randint(2, 8))
        amount = round(self.rng.uniform(200_000, 900_000), 2)
        ref = self._add_transfer(launderer, organizer, amount, transfer_t, "IMPS")
        self.ground_truth.append({
            "type": "call_transfer_coincidence", "ring": ring,
            "participants": [organizer.person_id, launderer.person_id],
            "identifiers": {"caller": caller_phone, "callee": callee_phone, "ip": ip,
                            **self._ids([organizer, launderer])},
            "evidence": {"call_time": t.isoformat(), "transfer_time": transfer_t.isoformat(),
                         "transfer_ref": ref, "amount": amount},
            "description": "Call from organizer to launderer; launderer online from IP; "
                           "transfer within window W.",
        })

    def _plant_structuring(self, ring, mule, t):
        refs = []
        n = self.rng.randint(4, 7)
        for i in range(n):
            amt = round(REPORTING_THRESHOLD * self.rng.uniform(0.90, 0.99), 2)
            payer = self.rng.choice([p for p in self.people if p is not mule])
            refs.append(self._add_transfer(payer, mule, amt, t + timedelta(minutes=20 * i), "NEFT"))
        self.ground_truth.append({
            "type": "structuring", "ring": ring, "participants": [mule.person_id],
            "identifiers": {"account": mule.accounts[0].account_no, **self._ids([mule])},
            "evidence": {"refs": refs, "count": n, "band": "just below reporting threshold"},
            "description": f"{n} transfers just below INR {REPORTING_THRESHOLD} into one account.",
        })

    def _plant_rapid_in_out(self, ring, launderer, mule, t):
        amt = round(self.rng.uniform(300_000, 800_000), 2)
        in_ref = self._add_transfer(launderer, mule, amt, t, "IMPS")
        out_ref = self._add_transfer(mule, launderer, round(amt * 0.95, 2),
                                     t + timedelta(minutes=self.rng.randint(5, 40)), "IMPS")
        self.ground_truth.append({
            "type": "rapid_in_out", "ring": ring, "participants": [mule.person_id],
            "identifiers": {"account": mule.accounts[0].account_no, **self._ids([mule])},
            "evidence": {"in_ref": in_ref, "out_ref": out_ref, "amount": amt},
            "description": "Funds credited then ~95% forwarded within minutes (pass-through).",
        })

    def _plant_layering(self, ring, chain, t):
        amt = round(self.rng.uniform(500_000, 900_000), 2)
        refs = []
        for i in range(len(chain) - 1):
            ref = self._add_transfer(chain[i], chain[i + 1], round(amt * (0.97 ** i), 2),
                                     t + timedelta(minutes=15 * i), "RTGS")
            refs.append(ref)
        self.ground_truth.append({
            "type": "layering", "ring": ring,
            "participants": [p.person_id for p in chain],
            "identifiers": self._ids(chain),
            "evidence": {"refs": refs, "hops": len(refs)},
            "description": f"Funds layered across {len(chain)} accounts in quick succession.",
        })

    def _plant_circular_flow(self, ring, cycle, t):
        amt = round(self.rng.uniform(200_000, 600_000), 2)
        refs = []
        n = len(cycle)
        for i in range(n):
            a, b = cycle[i], cycle[(i + 1) % n]
            refs.append(self._add_transfer(a, b, amt, t + timedelta(minutes=20 * i), "IMPS"))
        self.ground_truth.append({
            "type": "circular_flow", "ring": ring,
            "participants": [p.person_id for p in cycle],
            "identifiers": self._ids(cycle),
            "evidence": {"refs": refs, "cycle_length": n},
            "description": f"Money loops A->...->A across {n} accounts.",
        })

    def run(self):
        self.generate_benign()
        self.generate_fraud()
        return self
