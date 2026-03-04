import io
import os
import sys
from dataclasses import asdict

from flask import Flask, request, jsonify, render_template_string

# 确保可以从项目根目录导入 app.py
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import (  # noqa: E402
    extract_text_from_pdf,
    extract_basic_info,
    extract_job_info,
    extract_background_info,
    compute_match_score,
)


app = Flask(__name__)


DEFAULT_JD_TEXT = """
岗位名称：全栈开发实习生
工作地点：远程/北京
实习周期：至少3个月，能稳定实习6个月者优先
工作时间：每周至少工作4天，每天保证8小时有效工作时间
实习薪资：150-200元/天

岗位职责：
1. 页面开发与实现：基于 React/Next.js 技术栈，配合 UI 设计稿完成前端页面的开发与优化，确保页面视觉一致性与交互畅性；熟练运用 Tailwind CSS 实现响应式布局，适配不同终端设备。
2. 组件封装与复用：参与前端公共组件库的设计与封装，提升组件复用性与开发效率；使用 TypeScript 规范代码类型，减少开发过程中类型错误，提升代码可维护性。
3. 交互逻辑实现：负责前端交互逻辑的开发，配合后端团队完成接口联调，确保数据交互的准确性与稳定性；处理页面加载、数据请求等场景的异常情况，优化用户体验。
4. 性能优化与调试：协助进行前端性能优化，包括页面加载速度、渲染性能等方面的调优；使用浏览器开发者工具等工具排查并解决常见前端 bug，保障系统稳定运行。
5. 团队协作与文档编写：参与团队技术讨论与需求评审，配合产品、设计及后端团队推进项目迭代；协助编写前端开发相关文档，包括组件使用说明、接口调用文档等。

任职要求：
1. 教育背景：计算机科学与技术、软件工程、电子信息工程等相关专业大三、大四本科生或研究生在读。
2. 技术基础：熟练掌握 React 框架核心原理与使用方法，了解 Next.js 框架特性及应用场景者优先；精通 Tailwind CSS 样式开发，能高效实现 UI 设计需求。
3. 语言与工具：熟练使用 TypeScript 进行开发，理解 TypeScript 类型系统核心概念；熟练掌握 HTML5、CSS3 等前端基础技术，了解前端工程化流程。
4. 协作能力：熟练使用 Git 版本控制工具，了解 GitFlow 等代码协作规范；具备良好的沟通能力，能清晰同步开发进度与问题。
5. 时间保障：能严格遵守每周至少4天、每天8小时的工作时间要求，确保稳定参与项目迭代，实习周期满3个月及以上。
6. 个人特质：具备强烈的学习意愿，能快速跟进前端新技术与框架更新；逻辑思维清晰，具备独立分析和解决问题的能力；责任心强，对代码质量有较高追求。

加分项：
- 有完整的 React/Next.js 项目开发经验（课程设计、个人项目、实习项目等），能提供 GitHub 仓库链接或项目演示地址者优先。
- 熟悉前端工程化工具，如 Webpack、Vite、ESLint 等，有项目构建与配置经验者优先。
- 了解前端性能优化常用方案，如懒加载、代码分割、缓存策略等，有实际优化案例者优先。
- 具备 AI 相关产品前端开发经验，或了解大语言模型应用场景，有数据可视化（如 ECharts、Recharts）开发经验者优先。
- 杭州/本地在校生，能接受线下办公或定期线下沟通；有技术博客撰写经验或开源项目贡献者优先。
"""


INDEX_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>模块三：简历评分与匹配</title>
</head>
<body>
  <h2>模块三：简历评分与匹配 Demo</h2>
  <p>上传 PDF 简历，并粘贴职位描述文本，查看匹配评分。</p>
  <form action="/score" method="post" enctype="multipart/form-data">
    <div>
      <label>简历 PDF 文件：</label>
      <input type="file" name="file" accept="application/pdf" required />
    </div>
    <div>
      <label>职位描述（JD）：</label><br />
      <textarea name="job_desc" rows="8" cols="80" placeholder="在这里粘贴招聘 JD 文本"></textarea>
    </div>
    <button type="submit">上传并评分</button>
  </form>
  {% if result %}
    <h3>评分结果：</h3>
    <pre style="white-space: pre-wrap; border: 1px solid #ccc; padding: 8px;">{{ result }}</pre>
  {% endif %}
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
  """提供一个简单页面，方便直接在浏览器测试模块三。"""
  return render_template_string(INDEX_HTML, result="")


@app.route("/score", methods=["POST"])
def score():
    """上传 PDF + 职位描述，返回解析结果与匹配评分（无缓存）。"""
    if "file" not in request.files:
        return jsonify({"error": "缺少文件参数 file"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "仅支持 PDF 简历文件"}), 400

    job_desc = request.form.get("job_desc", "")
    # 如果未提供 JD 文本，则默认使用“全栈开发实习生”岗位的 JD
    if not job_desc.strip():
        job_desc = DEFAULT_JD_TEXT

    try:
        text = extract_text_from_pdf(io.BytesIO(file.read()))
    except Exception as e:
        return jsonify({"error": f"PDF 解析失败: {e}"}), 500

    basic_info = extract_basic_info(text)
    job_info = extract_job_info(text)
    background_info = extract_background_info(text)
    match_result = compute_match_score(text, job_desc)

    # 如果是浏览器表单提交（非 JSON 调用），返回带评分信息的 HTML
    if request.content_type and "multipart/form-data" in request.content_type and not request.is_json:
        pretty = [
            f"综合评分：{match_result.get('overall_score', 0)}",
            f"技能匹配：{match_result.get('skill_score', 0)}",
            f"经验匹配：{match_result.get('experience_score', 0)}",
            f"学历匹配：{match_result.get('education_score', 0)}",
            "",
            f"姓名：{asdict(basic_info).get('name')}",
            f"电话：{asdict(basic_info).get('phone')}",
            f"邮箱：{asdict(basic_info).get('email')}",
        ]
        return render_template_string(INDEX_HTML, result="\n".join(pretty))

    # 默认仍然返回 JSON，方便接口调用
    return jsonify(
        {
            "raw_text": text,
            "basic_info": asdict(basic_info),
            "job_info": asdict(job_info),
            "background_info": asdict(background_info),
            "match": match_result,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5103, debug=True)

