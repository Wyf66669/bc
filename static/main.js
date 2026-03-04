const form = document.getElementById("analyze-form");
const statusEl = document.getElementById("status");
const jsonOutput = document.getElementById("json-output");
const keyInfoEl = document.getElementById("key-info");
const scorePanelEl = document.getElementById("score-panel");
const apiBaseEl = document.getElementById("api_base");
// 默认后端地址（你的阿里云 FC HTTP 触发 URL，去掉最后的斜杠）
const DEFAULT_API_BASE = "https://cv-service-bfaoagpcvd.cn-shenzhen.fcapp.run";

function setStatus(text, type = "") {
  statusEl.textContent = text;
  statusEl.className = `status${type ? " status--" + type : ""}`;
}

function renderKeyInfo(result) {
  const b = result.basic_info || {};
  const j = result.job_info || {};
  const bg = result.background_info || {};

  const rows = [
    ["姓名", b.name],
    ["电话", b.phone],
    ["邮箱", b.email],
    ["地址", b.address],
    ["求职意向", j.intention],
    ["期望薪资", j.expected_salary],
    ["工作年限", bg.years_of_experience],
    ["学历背景", bg.education],
  ];

  keyInfoEl.innerHTML = rows
    .map(
      ([label, value]) => `
      <div class="info-item">
        <div class="info-item-label">${label}</div>
        <div class="info-item-value ${
          value ? "" : "info-item-empty"
        }">${value || "未识别"}</div>
      </div>
    `
    )
    .join("");
}

function renderScore(result) {
  const m = result.match || {};
  if (!m || m.overall_score == null) {
    scorePanelEl.innerHTML = "<p>暂无匹配结果。</p>";
    return;
  }

  const scoreType =
    m.comment && String(m.comment).includes("简历质量分") ? "简历质量分" : "岗位匹配度";

  scorePanelEl.innerHTML = `
    <div class="score-type">${scoreType}</div>
    <div class="score-main">
      ${m.overall_score}<span class="score-main-unit">分 / 100</span>
    </div>
    <div class="score-sub">
      <span>技能匹配：${m.skill_score ?? 0} 分</span>
      <span>经验匹配：${m.experience_score ?? 0} 分</span>
      <span>学历匹配：${m.education_score ?? 0} 分</span>
    </div>
    ${m.comment ? `<p class="score-sub">${m.comment}</p>` : ""}
    ${
      Array.isArray(m.overlap_keywords) && m.overlap_keywords.length
        ? `<p class="score-sub">关键重叠词：${m.overlap_keywords
            .slice(0, 20)
            .join("、")}</p>`
        : ""
    }
  `;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById("file");
  if (!fileInput.files.length) {
    setStatus("请先选择 PDF 简历文件。", "error");
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  const jobDesc = (document.getElementById("job_desc").value || "").trim();
  formData.append("job_desc", jobDesc);

  setStatus("解析中，请稍候...", "loading");
  jsonOutput.textContent = "";
  keyInfoEl.innerHTML = "";
  scorePanelEl.innerHTML = "";

  try {
    const resp = await fetch("/api/analyze", {
      method: "POST",
      body: formData,
    });

    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.error || "请求失败");
    }

    const hint = jobDesc ? "（岗位匹配度）" : "（简历质量分）";
    setStatus(
      (data.from_cache ? "命中缓存，已返回历史结果。" : "解析完成。") + hint,
      "success"
    );
    jsonOutput.textContent = JSON.stringify(data, null, 2);
    renderKeyInfo(data);
    renderScore(data);
  } catch (err) {
    console.error(err);
    setStatus("解析失败：" + err.message, "error");
  }
});

