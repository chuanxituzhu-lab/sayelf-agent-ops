import assert from "node:assert/strict";
import test from "node:test";

import { generateWorkforceBlueprint } from "./workforce_blueprint.js";

test("arbitrary industry receives a local two-role producer and independent review loop", () => {
  const result = generateWorkforceBlueprint("宠物医疗连锁", "整理预约接诊流程");
  assert.equal(result.status, "generated");
  assert.equal(result.roleCount, 2);
  assert.match(result.roles[0].name, /宠物医疗连锁执行 Agent/u);
  assert.match(result.roles[1].name, /独立质量审核/u);
  assert.ok(result.roles.every((role) => role.input && role.output && role.acceptance));
  assert.equal(result.state, "proposed");
  assert.match(result.notice, /尚未激活/u);
});

test("separate research and production requests add only the necessary research role", () => {
  const result = generateWorkforceBlueprint("餐饮连锁", "调研新品卖点，制作小红书内容与多平台适配发布包");
  assert.equal(result.roleCount, 3);
  assert.equal(result.roles[0].id, "blueprint.research");
  assert.match(result.roles[1].name, /内容策划与制作 Agent/u);
  assert.equal(result.roles[2].id, "blueprint.reviewer");
  assert.match(result.roles[1].output, /多平台适配发布包/u);
  assert.match(result.roles[0].acceptance, /来源可追溯/u);
  assert.match(result.roles[2].acceptance, /人工确认/u);
});

test("registered industry examples can refine role labels without changing the local-only contract", () => {
  const result = generateWorkforceBlueprint("软件开发公司", "修复用户登录 bug");
  assert.equal(result.roleCount, 2);
  assert.match(result.roles[0].name, /软件开发 Agent/u);
  assert.match(result.roles[0].output, /是否可执行取决于已连接能力/u);
  assert.match(result.notice, /本机生成/u);
});

test("empty and over-limit profiles fail closed", () => {
  assert.deepEqual(generateWorkforceBlueprint("  ").roles, []);
  assert.equal(generateWorkforceBlueprint("x".repeat(1201)).status, "invalid");
  assert.equal(generateWorkforceBlueprint("餐饮", "y".repeat(1201)).status, "invalid");
});
