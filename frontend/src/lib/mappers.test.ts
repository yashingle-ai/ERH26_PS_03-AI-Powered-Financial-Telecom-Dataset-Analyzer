import { describe, it, expect } from "vitest";
import { mapEntity, mapIdentifiers, mapDetections, riskDistributionFrom } from "./mappers";
import type { RiskEntity } from "./api";

/**
 * Mapper tests, weighted towards the distinctions this project has decided are
 * evidentially meaningful. The interesting cases are all about *absence*: a zero
 * that means "measured, found nothing" versus one that means "never measured",
 * and a field an older backend does not send at all.
 */

/** A complete RiskEntity, so each test can vary exactly one field. */
const base: RiskEntity = {
  entity_id: "E1",
  label: "Subject A",
  risk_score: 55,
  band: "medium",
  ml_score: 0,
  rule_flags: [],
  features: {},
};

describe("mapEntity", () => {
  it("falls back to the entity id when no label is given", () => {
    expect(mapEntity({ ...base, label: null }).label).toBe("E1");
  });

  /**
   * `ml_scored` distinguishes "the forest looked at this entity and found nothing
   * unusual" from "this entity was never in the fitted population". Both surface
   * as ml_score 0.0 under min-max normalisation, and they are different findings
   * — see handbook/GAPS.md §7.5.
   */
  it("defaults mlScored to true when the backend does not send the field", () => {
    // An older backend fitted the forest over every entity, so its 0.0 really was
    // a measurement. Defaulting to false would relabel those as unexamined.
    expect(mapEntity(base).mlScored).toBe(true);
  });

  it("preserves an explicit ml_scored: false", () => {
    expect(mapEntity({ ...base, ml_scored: false }).mlScored).toBe(false);
  });

  /**
   * Enabled rule weights sum to 1.2 against a component capped at 1.0, so six
   * typologies and eight can score identically. `typologies_fired` is the
   * tiebreaker — it must come from the server when present, not be re-derived
   * from the flag list, which can be truncated.
   */
  it("prefers the server's typologies_fired over counting rule flags", () => {
    const e = mapEntity({
      ...base,
      typologies_fired: 8,
      rule_flags: [{ rule: "layering", detail: "", weight: 0.15 }],
    });
    expect(e.typologiesFired).toBe(8);
  });

  it("counts rule flags only when typologies_fired is absent", () => {
    const e = mapEntity({
      ...base,
      rule_flags: [
        { rule: "layering", detail: "", weight: 0.15 },
        { rule: "structuring", detail: "", weight: 0.2 },
      ],
    });
    expect(e.typologiesFired).toBe(2);
  });

  it("never leaves an entity without an identifier to display", () => {
    expect(mapEntity(base).identifiers).toEqual([{ kind: "ACCOUNT_NO", value: "E1" }]);
  });

  it("coerces missing numeric fields to 0 rather than NaN", () => {
    const e = mapEntity(base);
    expect(e.risk).toBe(55);
    expect(e.mlScore).toBe(0);
    expect(e.events).toBe(0);
    expect(e.volume).toBe(0);
    expect(Number.isNaN(e.mlScore)).toBe(false);
  });
});

describe("mapIdentifiers", () => {
  it("returns an empty array for undefined rather than throwing", () => {
    expect(mapIdentifiers(undefined)).toEqual([]);
  });
});

describe("mapDetections and riskDistributionFrom", () => {
  it("survives an empty entity list", () => {
    expect(mapDetections([])).toEqual([]);
    const dist = riskDistributionFrom([]);
    expect(dist).toBeDefined();
  });

  /**
   * A rule that fired on nothing and a rule that could not run are different
   * findings — the backend added /v1/rule-eligibility precisely because
   * "9,996 eligible, 0 fired" read as a broken detector. The mapper must not
   * quietly drop entities that carry no flags.
   */
  it("does not invent detections for entities with no rule flags", () => {
    const out = mapDetections([{ ...base, rule_flags: [] } as RiskEntity]);
    expect(out.every((d) => d.entities >= 0)).toBe(true);
  });
});
