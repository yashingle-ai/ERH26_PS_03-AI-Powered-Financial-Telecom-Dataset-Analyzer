"""Entity-first population backbone for synthetic data (research/12 §8.1).

We create real-world *people* first, each owning phones, accounts, UPI IDs, and a
device (IMEI/IMSI). Because all three datasets are generated from this shared identity
backbone, the fusion bridge (shared phone numbers, time coincidence) is real — not
bolted on afterward.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from faker import Faker

BANKS = [
    ("HDFC Bank", "HDFC"),
    ("State Bank of India", "SBIN"),
    ("ICICI Bank", "ICIC"),
    ("Axis Bank", "UTIB"),
    ("Punjab National Bank", "PUNB"),
]


@dataclass
class Account:
    account_no: str
    bank_name: str
    ifsc: str
    upi_id: str


@dataclass
class Person:
    person_id: str
    name: str
    phones: list[str]
    accounts: list[Account]
    imei: str
    imsi: str
    home_ip_pool: list[str]
    role: str = "normal"          # normal | mule | launderer | organizer
    fraud_ring: int | None = None
    labels: list[str] = field(default_factory=list)


def _indian_msisdn(rng: random.Random) -> str:
    """+91 followed by a valid-looking 10-digit mobile (starts 6-9)."""
    return "+91" + str(rng.choice([6, 7, 8, 9])) + "".join(str(rng.randint(0, 9)) for _ in range(9))


def _imei(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(15))


def _imsi(rng: random.Random) -> str:
    return "40" + "".join(str(rng.randint(0, 9)) for _ in range(13))  # 404/405 = India MCC-ish


def _account_no(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(rng.choice([11, 12, 14])))


def _ip(rng: random.Random) -> str:
    # Realistic-looking public IPv4 (avoids reserved ranges for realism)
    return f"{rng.randint(14, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def _upi_id(name: str, bank_handle: str, rng: random.Random) -> str:
    handle = name.lower().split()[0] + str(rng.randint(1, 999))
    return f"{handle}@{bank_handle.lower()}"


def build_population(n_persons: int, seed: int = 42) -> list[Person]:
    rng = random.Random(seed)
    fake = Faker("en_IN")
    Faker.seed(seed)

    people: list[Person] = []
    for i in range(n_persons):
        name = fake.name()
        n_phones = rng.choice([1, 1, 1, 2])          # most have one, some two
        phones = [_indian_msisdn(rng) for _ in range(n_phones)]

        n_accounts = rng.choice([1, 1, 2])
        accounts = []
        for _ in range(n_accounts):
            bank_name, handle = rng.choice(BANKS)
            accounts.append(
                Account(
                    account_no=_account_no(rng),
                    bank_name=bank_name,
                    ifsc=f"{handle}0{rng.randint(100000, 999999)}",
                    upi_id=_upi_id(name, handle, rng),
                )
            )

        people.append(
            Person(
                person_id=f"P{i:04d}",
                name=name,
                phones=phones,
                accounts=accounts,
                imei=_imei(rng),
                imsi=_imsi(rng),
                home_ip_pool=[_ip(rng) for _ in range(rng.choice([1, 2]))],
            )
        )
    return people
