import assert from "node:assert/strict";
import test from "node:test";

import { recommendIndustryRoles } from "./industry_recommendation.js";

const roles = [
  { id: "media.content-planner", name: "内容策划" },
  { id: "media.creative-producer", name: "内容制作" },
  { id: "media.growth-operator", name: "运营增长" },
  { id: "engineering.commercial", name: "商务造价" },
];

test("media industry aliases return only registered media roles", () => {
  const result = recommendIndustryRoles("自媒体公司", "media", roles);
  assert.equal(result.status, "recommended");
  assert.equal(result.pack.name, "内容与媒体");
  assert.deepEqual(result.roles.map((role) => role.id), [
    "media.content-planner", "media.creative-producer", "media.growth-operator",
  ]);
});

test("matching an unselected industry never borrows its roles", () => {
  const result = recommendIndustryRoles("工程项目", "media", roles);
  assert.equal(result.status, "pack-mismatch");
  assert.deepEqual(result.roles, []);
});

test("engineering industry returns its own registered roles when selected", () => {
  const result = recommendIndustryRoles("工程项目", "engineering", roles);
  assert.equal(result.status, "recommended");
  assert.deepEqual(result.roles.map((role) => role.id), ["engineering.commercial"]);
});

test("ambiguous and unsupported industries are reported without guessing", () => {
  assert.equal(recommendIndustryRoles("工程自媒体", "media", roles).status, "ambiguous");
  assert.equal(recommendIndustryRoles("餐饮零售", "media", roles).status, "unknown");
});

test("empty registry and invalid input fail closed", () => {
  assert.equal(recommendIndustryRoles("MCN", "media", []).status, "empty");
  assert.equal(recommendIndustryRoles("  ", "media", roles).status, "invalid");
  assert.equal(recommendIndustryRoles("x".repeat(121), "media", roles).status, "invalid");
});
