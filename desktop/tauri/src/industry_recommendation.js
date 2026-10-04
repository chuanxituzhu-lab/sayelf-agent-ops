const INDUSTRY_PACKS = [
  {
    id: "media",
    name: "内容与媒体",
    aliases: [
      "自媒体", "媒体公司", "内容与媒体", "内容公司", "内容创作", "内容行业",
      "新媒体", "短视频", "公众号运营", "视频号运营", "小红书运营", "抖音运营",
      "传媒", "mcn", "media", "content creator", "content company",
    ],
  },
  {
    id: "engineering",
    name: "工程与项目",
    aliases: [
      "工程与项目", "工程项目", "建筑工程", "建筑公司", "市政工程", "施工项目",
      "造价", "工程", "建筑", "市政", "施工", "engineering", "construction",
    ],
  },
];

function normalize(value) {
  return value.trim().toLocaleLowerCase().replace(/\s+/gu, "");
}

export function recommendIndustryRoles(industry, activePack, registeredRoles) {
  if (typeof industry !== "string" || industry.trim().length === 0 || industry.length > 120) {
    return { status: "invalid", roles: [] };
  }

  const query = normalize(industry);
  const matches = INDUSTRY_PACKS.filter((pack) =>
    pack.aliases.some((alias) => query.includes(normalize(alias))));

  if (matches.length === 0) return { status: "unknown", roles: [] };
  if (matches.length > 1) {
    return { status: "ambiguous", packs: matches.map(({ id, name }) => ({ id, name })), roles: [] };
  }

  const [pack] = matches;
  if (pack.id !== activePack) {
    return { status: "pack-mismatch", pack: { id: pack.id, name: pack.name }, roles: [] };
  }

  const roles = Array.isArray(registeredRoles)
    ? registeredRoles.filter((role) => typeof role?.id === "string" && role.id.startsWith(`${pack.id}.`))
    : [];
  if (roles.length === 0) {
    return { status: "empty", pack: { id: pack.id, name: pack.name }, roles: [] };
  }

  return { status: "recommended", pack: { id: pack.id, name: pack.name }, roles };
}
