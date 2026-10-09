const LIMIT = 1200;

function makeRole(id, name, responsibility, input, output, acceptance) {
  return { id, name, responsibility, input, output, acceptance, state: "proposed" };
}

function producerLabel(text, industry) {
  if (/(小红书|公众号|视频号|抖音|短视频|内容|文章|脚本|文案)/u.test(text)) return "内容策划与制作 Agent";
  if (/(软件|代码|程序|网站|应用|api|测试|bug)/iu.test(text)) return "软件开发 Agent";
  if (/(工程|施工|造价|建筑|市政|图纸|boq)/iu.test(text)) return "工程专业执行 Agent";
  if (/(数据|统计|指标|报表|经营分析)/u.test(text)) return "数据分析 Agent";
  if (/(设计|视觉|海报|品牌|创意)/u.test(text)) return "设计制作 Agent";
  const label = industry.replace(/[\s，,。；;：:]+/gu, " ").slice(0, 24).trim();
  return `${label || "专业工作"}执行 Agent`;
}

function requestedOutput(text) {
  if (/(小红书|公众号|视频号|抖音|短视频|文章|脚本|文案|内容)/u.test(text)
      && /(发布包|多平台|平台规范|逐平台|发布检查)/u.test(text)) {
    return "多平台适配发布包（标题、正文、标签与逐平台人工检查项）";
  }
  if (/(小红书|公众号|视频号|抖音|短视频|文章|脚本|文案)/u.test(text)) return "可供人工审核的平台内容初稿";
  if (/(软件|代码|程序|网站|应用|api|bug)/iu.test(text)) return "软件工作方案或代码成果说明（是否可执行取决于已连接能力）";
  if (/(工程|施工|造价|建筑|市政|图纸|boq)/iu.test(text)) return "工程分析或工作方案（是否可执行取决于已连接能力）";
  if (/(报表|统计|数据|指标)/u.test(text)) return "数据分析结果与依据";
  if (/(方案|规划|计划)/u.test(text)) return "结构化方案与执行步骤";
  if (/(报告|分析|评估|审查)/u.test(text)) return "分析报告与依据";
  return "用户描述的专业成果初稿";
}

export function generateWorkforceBlueprint(industry, workDescription = "") {
  if (typeof industry !== "string" || !industry.trim() || industry.length > LIMIT) {
    return { status: "invalid", roles: [] };
  }
  if (typeof workDescription !== "string" || workDescription.length > LIMIT) {
    return { status: "invalid", roles: [] };
  }

  const cleanIndustry = industry.trim();
  const brief = workDescription.trim();
  const text = `${cleanIndustry} ${brief}`;
  const roles = [];
  const asksForResearch = /(调研|研究|检索|收集|核实|对比|竞品|资料整理)/u.test(text);
  const asksForProduction = /(撰写|写作|制作|生成|开发|编写|设计|剪辑|搭建|交付|产出|方案|报告|内容|代码)/iu.test(text);

  if (asksForResearch && asksForProduction) {
    roles.push(makeRole(
      "blueprint.research",
      "业务研究与需求分析 Agent",
      "拆解目标、整理输入材料、标明来源与待核实事项，并交接可追溯的依据。",
      brief || cleanIndustry,
      "结构化需求、事实依据与待确认问题",
      "需求覆盖完整；事实、推断与待核实信息分开标记；来源可追溯。",
    ));
  }

  const primaryOutput = requestedOutput(text);
  roles.push(makeRole(
    "blueprint.producer",
    producerLabel(text, cleanIndustry),
    asksForProduction ? "依据需求和上一步可用材料完成指定专业交付，并保留产出依据。" : "把行业工作拆成明确任务，完成用户要求的核心交付。",
    asksForResearch && asksForProduction ? "已确认的需求与结构化研究依据" : (brief || cleanIndustry),
    primaryOutput,
    "覆盖用户明确要求；列出使用材料、假设和未完成项；不声称未连接能力已执行。",
  ));

  roles.push(makeRole(
    "blueprint.reviewer",
    "独立质量审核 Agent",
    "独立对照原始需求审核完整性、事实依据、风险和格式；不能审核自己生产的环节。",
    `${primaryOutput}；原始需求：${brief || cleanIndustry}`,
    "审核清单、问题与修改建议；通过后形成待人工确认的交付包",
    "逐项对照需求；关键事实有依据；问题闭合或显式标记；对外发布保留人工确认。",
  ));

  return {
    status: "generated",
    industry: cleanIndustry,
    workDescription: brief,
    roleCount: roles.length,
    state: "proposed",
    roles,
    notice: "这是本机生成的岗位流程方案。岗位尚未激活；陌生行业的专业执行能力需连接已登记技能后才能实际工作。",
  };
}
