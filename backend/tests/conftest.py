import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def smoke_dataset(tmp_path_factory):
    """Generate a small synthetic dataset once for the test session."""
    from tools.synthetic_data_generator import emitters
    from tools.synthetic_data_generator.activity import ActivityGenerator
    from tools.synthetic_data_generator.config import TIERS
    from tools.synthetic_data_generator.population import build_population

    out = tmp_path_factory.mktemp("smoke_ds")
    tier = TIERS["smoke"]
    people = build_population(tier.n_persons, seed=7)
    gen = ActivityGenerator(people, tier, seed=7).run()
    import random
    rng = random.Random(7)
    acct_mobile = {a.account_no: p.phones[0] for p in people for a in p.accounts}
    emitters.emit_bank(gen.bank_txns, str(out), rng, acct_mobile)
    emitters.emit_cdr(gen.cdr_rows, str(out), rng)
    emitters.emit_ipdr(gen.ipdr_rows, str(out), rng)
    emitters.emit_ground_truth(gen.ground_truth, str(out))
    return str(out)
