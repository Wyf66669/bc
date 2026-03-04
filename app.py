import hashlib
import io
import re
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

from flask import Flask, request, jsonify, send_from_directory
import pdfplumber


app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
)


@dataclass
class BasicInfo:
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    address_source: Optional[str] = None  # address | native_place | intention_city | inferred | None
    native_place: Optional[str] = None  # 籍贯/户籍/户口所在地


@dataclass
class JobInfo:
    intention: Optional[str] = None
    expected_salary: Optional[str] = None
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    salary_unit: Optional[str] = None  # month/year/day/other
    target_cities: Optional[str] = None
    work_type: Optional[str] = None  # 全职/实习/兼职/不限
    arrival_time: Optional[str] = None
    keywords: Optional[str] = None


@dataclass
class BackgroundInfo:
    years_of_experience: Optional[str] = None
    years_of_experience_num: Optional[float] = None
    education: Optional[str] = None
    highest_degree: Optional[str] = None
    school: Optional[str] = None
    major: Optional[str] = None
    graduation_time: Optional[str] = None
    work_experience: Optional[str] = None
    projects: Optional[str] = None
    skills: Optional[str] = None
    certificates: Optional[str] = None
    awards: Optional[str] = None
    self_evaluation: Optional[str] = None


def _extract_section(text: str, titles) -> Optional[str]:
    """按常见标题抽取段落摘要（不保证精准，但比纯关键字更稳定）。"""
    if not text.strip():
        return None
    # 统一换行，避免标题与内容粘连
    t = "\n" + text.strip() + "\n"
    # 标题集合转为正则
    title_pattern = "|".join(re.escape(x) for x in titles)
    # 找到任一标题出现的位置
    m = re.search(rf"\n\s*({title_pattern})\s*\n", t)
    if not m:
        # 有些简历标题后面直接跟内容（同一行）
        m = re.search(rf"\n\s*({title_pattern})\s*[:：]?\s*(.+)", t)
        if m:
            return (m.group(2) or "").strip()[:1500] or None
        return None
    start = m.end()
    # 结束位置：下一个常见标题
    next_title = re.search(
        r"\n\s*(基本信息|个人信息|求职意向|工作经历|工作经验|项目经验|项目经历|教育经历|教育背景|技能|专业技能|证书|资格证|获奖|荣誉|自我评价)\s*[:：]?\s*\n",
        t[start:],
    )
    end = start + next_title.start() if next_title else len(t)
    content = t[start:end].strip()
    return content[:1500] if content else None


def _parse_salary_range(s: str):
    """尽量解析薪资区间，返回 (min,max,unit)。无法解析则返回 (None,None,None)。"""
    if not s:
        return None, None, None
    raw = s.replace(" ", "").replace("／", "/")
    unit = None
    if any(x in raw for x in ["/月", "月", "月薪"]):
        unit = "month"
    elif any(x in raw for x in ["/年", "年薪", "年"]):
        unit = "year"
    elif any(x in raw for x in ["/天", "日薪", "天"]):
        unit = "day"
    # 为区间解析做规范化：去掉形如“8000/月-12000/月”中的“/月”等单位标记
    raw_for_range = raw
    for token in ["/月", "/年", "/天", "月薪", "年薪", "日薪", "元/月", "元/年", "元/天"]:
        raw_for_range = raw_for_range.replace(token, "")
    # 区间：8000-12000、8000/月-12000/月、8k-12k、8K~12K
    m = re.search(
        r"(\d+(?:\.\d+)?)(k|K|千|w|W|万)?\s*[-~—到至]\s*(\d+(?:\.\d+)?)(k|K|千|w|W|万)?",
        raw_for_range,
    )
    if not m:
        return None, None, unit

    def to_num(val, u):
        n = float(val)
        if u in ("k", "K", "千"):
            n *= 1000
        elif u in ("w", "W", "万"):
            n *= 10000
        return int(n)

    mn = to_num(m.group(1), m.group(2))
    mx = to_num(m.group(3), m.group(4))
    return mn, mx, unit or "other"


def extract_text_from_pdf(file_stream: io.BytesIO) -> str:
    """解析 PDF 文本，支持多页，并做简单清洗。"""
    texts = []
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            texts.append(page_text)
    full_text = "\n".join(texts)

    # 简单清洗：去掉重复空白和一些不可见字符
    full_text = re.sub(r"[ \t]+", " ", full_text)
    full_text = re.sub(r"\u200b|\ufeff", "", full_text)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)
    return full_text.strip()


def extract_basic_info(text: str) -> BasicInfo:
    # 手机号（大陆常见 11 位）
    phone_match = re.search(r"(1[3-9]\d{9})", text)
    phone = phone_match.group(1) if phone_match else None

    # 邮箱
    email_match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text)
    email = email_match.group(1) if email_match else None

    # 姓名：优先在“姓名/个人信息/基本信息”附近找两个到四个非空白汉字
    name: Optional[str] = None
    name_patterns = [
        r"姓名[:：]\s*([^\s]{2,10})",  # 姓名：张三（允许更长，后面再裁剪）
        r"姓名\s+([^\s]{2,10})",  # 姓名  张三
        r"^([^\s]{2,10})[，, ]+(男|女)",  # 张三 男
    ]
    for pattern in name_patterns:
        m = re.search(pattern, text, re.MULTILINE)
        if m:
            candidate = m.group(1).strip()
            # 从候选里提取 2–4 个连续中文（允许中间有空格）
            m2 = re.search(r"([\u4e00-\u9fa5](?:\s*[\u4e00-\u9fa5]){1,3})", candidate)
            if m2:
                name = re.sub(r"\s+", "", m2.group(1))
            break

    # 兜底：更稳健地从关键信息附近挑选姓名候选
    if not name:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        stop_substrings = [
            "政治面貌",
            "民族",
            "性别",
            "出生",
            "年龄",
            "婚姻",
            "主修课程",
            "求职意向",
            "期望",
            "意向城市",
            "工作经验",
            "教育经历",
            "项目经历",
            "技能",
            "电话",
            "手机",
            "邮箱",
            "地址",
            "住址",
            "现居",
            "籍贯",
            "简历",
            "个人",
            "基本信息",
        ]

        # 1) 优先：如果某行包含“政治面貌”，且其前面有中文名，取其前的 2-4 个中文
        for ln in lines[:30]:
            if "政治面貌" in ln:
                m = re.search(r"([\u4e00-\u9fa5]{2,4})\s*.*政治面貌", ln)
                if m:
                    name = m.group(1)
                    break

        # 2) 找到手机号/邮箱所在行索引，附近窗口内挑最像姓名的 token
        key_idx = None
        for i, ln in enumerate(lines[:80]):
            if (phone and phone in ln) or (email and email in ln):
                key_idx = i
                break

        candidate_lines = []
        if key_idx is not None:
            start = max(0, key_idx - 6)
            end = min(len(lines), key_idx + 3)
            candidate_lines.extend(lines[start:end])
        candidate_lines.extend(lines[:15])

        best = None
        best_score = -10
        for ln in candidate_lines:
            if not ln or any(s in ln for s in stop_substrings):
                continue
            # 提取可能的人名（允许空格分隔）
            for m in re.finditer(r"([\u4e00-\u9fa5](?:\s*[\u4e00-\u9fa5]){1,3})", ln):
                token = re.sub(r"\s+", "", m.group(1))
                if len(token) < 2 or len(token) > 4:
                    continue
                if token in ["党员", "团员", "群众"]:
                    continue
                # 评分：越靠前越好、行越短越好
                score = 0
                score += 3 if ln in lines[:6] else 0
                score += max(0, 20 - len(ln)) / 10
                if key_idx is not None:
                    try:
                        dist = abs(lines.index(ln) - key_idx)
                        score += max(0, 6 - dist) / 2
                    except ValueError:
                        pass
                if score > best_score:
                    best_score = score
                    best = token
        name = name or best

    # 籍贯/户籍（单独抽取，供“地址缺失时用籍贯替代”）
    native_place = None
    # 形式一：籍    贯：江西省赣州市石城县（中间可能有空格）
    m = re.search(r"(?:籍\s*贯|户籍|户口所在地)\s*[:：]\s*([^\n]+)", text)
    if m:
        native_place = m.group(1).strip()
    # 形式二：整行里包含“籍 贯/户籍”等但符号较乱，用整行减去前缀
    if not native_place:
        for line in text.splitlines():
            norm = re.sub(r"\s+", "", line)
            if any(key in norm for key in ["籍贯", "户籍", "户口所在地"]):
                cleaned = line.strip()
                for k in ["籍", "贯", "户籍", "户口所在地", "：", ":", " "]:
                    cleaned = cleaned.replace(k, "")
                native_place = cleaned.strip() or None
                if native_place:
                    break

    # 地址：优先匹配包含“地址/住址/现居地/所在地/居住地”等关键词的行（支持“地 址”这种写法）
    address = None
    address_source: Optional[str] = None
    raw_lines = text.splitlines()
    for line in raw_lines:
        norm = re.sub(r"\s+", "", line)
        if any(k in norm for k in ["地址", "住址", "现居地", "现居", "所在城市", "居住地", "家庭住址"]):
            # 只截取标签后的地址部分，避免把后面其他字段一起带上
            m_addr = re.search(
                r"(?:地\s*址|地址|住址|现居地|现居|所在城市|居住地|家庭住址)\s*[:：]?\s*([^\s，,。;；]+)",
                line,
            )
            address = (m_addr.group(1).strip() if m_addr else line.strip())
            address_source = "address"
            break

    # 地址兜底：优先用“籍贯/户籍”等替代（按你的要求）
    if not address:
        if native_place:
            address = native_place
            address_source = "native_place"

    # 地址兜底：在手机号/邮箱附近找包含“省/市/区/县”的行
    if not address:
        key_index = None
        for idx, line in enumerate(raw_lines):
            if (phone and phone in line) or (email and email in line):
                key_index = idx
                break
        if key_index is not None:
            for offset in range(-3, 6):
                idx = key_index + offset
                if idx < 0 or idx >= len(raw_lines):
                    continue
                candidate = raw_lines[idx].strip()
                if candidate and re.search(r"[省市区县]", candidate):
                    address = candidate
                    address_source = "inferred"
                    break

    return BasicInfo(
        name=name,
        phone=phone,
        email=email,
        address=address,
        address_source=address_source,
        native_place=native_place,
    )


def extract_job_info(text: str) -> JobInfo:
    intention = None
    expected_salary = None
    target_cities = None
    work_type = None
    arrival_time = None
    keywords = None

    def _find_first_line(keys):
        for ln in text.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            if any(k in ln for k in keys):
                return ln
        return None

    # 求职意向：只取岗位本身，避免把“意向城市/到岗时间”等混在一起
    line = _find_first_line(["求职意向", "期望职位", "意向岗位", "目标岗位", "目标职位"])
    if line:
        m = re.search(r"(求职意向|期望职位|意向岗位|目标岗位|目标职位)[:：]\s*([^\n]+)", line)
        if m:
            payload = m.group(2).strip()
            # 截断到下一个字段开头
            payload = re.split(r"(意向城市|期望城市|工作地点|到岗时间|入职时间|期望薪资|薪资要求)[:：]", payload)[0].strip()
            intention = payload or None

    # 意向城市 / 期望城市 / 工作地点
    m = re.search(r"(?:意向城市|期望城市|工作地点)[:：]\s*([^\n]+)", text)
    if m:
        target_cities = m.group(1).strip()

    # 期望薪资
    salary_line = _find_first_line(["期望薪资", "期望工资", "薪资要求", "薪资范围"])
    if salary_line:
        m = re.search(r"(?:期望薪资|期望工资|薪资要求|薪资范围)[:：]\s*([^\n]+)", salary_line)
        if m:
            payload = m.group(1).strip()
            # 只保留薪资表达片段（避免把“入职时间”等带进来）
            m2 = re.search(
                r"(\d+(?:\.\d+)?(?:k|K|千|w|W|万)?\s*[-~—到至]\s*\d+(?:\.\d+)?(?:k|K|千|w|W|万)?\s*(?:/月|/年|/天|元/月|元/年|元/天|月|年|天)?)",
                payload.replace(" ", ""),
            )
            expected_salary = m2.group(1) if m2 else payload

    salary_min, salary_max, salary_unit = _parse_salary_range(expected_salary or "")

    # 工作性质
    m = re.search(r"(?:工作性质|求职类型|工作类型)[:：]\s*([^\n]+)", text)
    if m:
        work_type = m.group(1).strip()
    else:
        # 常见关键词兜底
        if re.search(r"(实习)", text):
            work_type = "实习"
        elif re.search(r"(兼职)", text):
            work_type = "兼职"
        elif re.search(r"(全职)", text):
            work_type = "全职"

    # 入职时间（优先从独立字段，其次从“期望薪资”同一行里捞）
    m = re.search(r"(?:入职时间|到岗时间|可到岗时间)[:：]\s*([^\n]+)", text)
    if m:
        arrival_time = m.group(1).strip()
    elif salary_line:
        m = re.search(r"(?:入职时间|到岗时间|可到岗时间)[:：]\s*([^\n]+)", salary_line)
        if m:
            arrival_time = m.group(1).strip()

    # 求职关键词：从“求职意向”这一行里抽取一些词作为关键词展示
    if intention:
        toks = re.split(r"[，,;；/| ]+", intention)
        toks = [t.strip() for t in toks if t.strip()]
        keywords = "、".join(toks[:8]) if toks else None

    return JobInfo(
        intention=intention,
        expected_salary=expected_salary,
        expected_salary_min=salary_min,
        expected_salary_max=salary_max,
        salary_unit=salary_unit,
        target_cities=target_cities,
        work_type=work_type,
        arrival_time=arrival_time,
        keywords=keywords,
    )


def extract_background_info(text: str) -> BackgroundInfo:
    years = None
    years_num: Optional[float] = None
    education = None
    highest_degree = None
    school = None
    major = None
    graduation_time = None
    work_experience = None
    projects = None
    skills = None
    certificates = None
    awards = None
    self_evaluation = None

    # 工作年限
    years_patterns = [
        r"(?:工作年限|工作经验)[:：]\s*([^\n]+)",
        r"(\d+年)工作经验",
    ]
    for pattern in years_patterns:
        m = re.search(pattern, text)
        if m:
            years = m.group(1).strip()
            break

    if years:
        m = re.search(r"(\d+(?:\.\d+)?)\s*年", years)
        if m:
            years_num = float(m.group(1))

    # 学历背景：搜索本科/硕士/博士等关键词所在行
    edu_keywords = ["博士", "硕士", "研究生", "本科", "大专"]
    for line in text.splitlines():
        if any(k in line for k in edu_keywords):
            education = line.strip()
            break

    # 最高学历
    if re.search(r"博士", text):
        highest_degree = "博士"
    elif re.search(r"硕士|研究生", text):
        highest_degree = "硕士/研究生"
    elif re.search(r"本科", text):
        highest_degree = "本科"
    elif re.search(r"大专", text):
        highest_degree = "大专"

    # 学校/专业/毕业时间（尽量从教育经历段落里抽）
    edu_section = _extract_section(text, ["教育经历", "教育背景"])
    if edu_section:
        # 学校：以“大学/学院/学校”结尾的短语
        m = re.search(r"([\u4e00-\u9fa5]{2,30}(?:大学|学院|学校))", edu_section)
        if m:
            school = m.group(1)
        # 专业：包含“专业/学院/计算机科学与技术”等
        m = re.search(r"(?:专业|方向)[:：]?\s*([^\n，,]{2,30})", edu_section)
        if m:
            major = m.group(1).strip()
        else:
            m = re.search(r"(计算机科学与技术|软件工程|网络工程|信息管理|电子信息|自动化|数学|统计学|人工智能|数据科学)", edu_section)
            if m:
                major = m.group(1)
        # 时间：2020.09-2024.06 / 2020-2024
        m = re.search(r"(\d{4}[./-]\d{1,2}\s*[-~—到至]\s*\d{4}[./-]\d{1,2})", edu_section)
        if m:
            graduation_time = m.group(1).strip()

    # 工作经历 / 工作经验段落摘要
    work_experience = _extract_section(text, ["工作经历", "工作经验", "实习经历"])

    # 项目经历：截取“项目经验/项目经历”段落
    projects = _extract_section(text, ["项目经验", "项目经历"])

    # 技能、证书、获奖、自我评价
    skills = _extract_section(text, ["技能", "专业技能", "技能特长"])
    certificates = _extract_section(text, ["证书", "资格证", "资格证书"])
    awards = _extract_section(text, ["获奖", "荣誉", "奖项"])
    self_evaluation = _extract_section(text, ["自我评价", "自我介绍", "个人总结"])

    return BackgroundInfo(
        years_of_experience=years,
        years_of_experience_num=years_num,
        education=education,
        highest_degree=highest_degree,
        school=school,
        major=major,
        graduation_time=graduation_time,
        work_experience=work_experience,
        projects=projects,
        skills=skills,
        certificates=certificates,
        awards=awards,
        self_evaluation=self_evaluation,
    )


def tokenize(text: str) -> set:
    # 简单中文+英文分词：按非字母数字和非中文字符拆分
    tokens = re.split(r"[^\w\u4e00-\u9fff]+", text)
    return {t for t in tokens if t}


def compute_match_score(resume_text: str, job_desc: str) -> Dict[str, Any]:
    """基于关键词重叠 / 简历质量的简易评分（0-100 分）。

    - 若给定职位描述 job_desc，则计算“岗位匹配度”；
    - 若 job_desc 为空，则仅根据简历本身给出一个“简历质量分”。
    """
    resume_tokens = tokenize(resume_text)

    # 1. 没有职位描述：给出“简历质量分”（不依赖 job_desc）
    if not job_desc.strip():
        # 粗略技能得分：统计常见技术关键词是否出现
        skill_keywords = [
            "Python",
            "Java",
            "C++",
            "C语言",
            "JavaScript",
            "前端",
            "后端",
            "全栈",
            "Django",
            "Flask",
            "Spring",
            "MySQL",
            "Redis",
            "Linux",
            "算法",
            "数据结构",
            "机器学习",
            "深度学习",
            "NLP",
            "Pandas",
            "NumPy",
            "Docker",
            "Kubernetes",
        ]
        sk_present = 0
        for kw in skill_keywords:
            if kw.lower() in resume_text.lower():
                sk_present += 1
        # 0~1 区间
        skill_score = min(sk_present / 6.0, 1.0)

        # 经验和教育得分仍然沿用下面的启发式
        experience_score = 1.0 if re.search(r"(3年以上|5年以上|主管|负责人|经理)", resume_text) else 0.5
        education_score = 0.6
        if re.search(r"(博士)", resume_text):
            education_score = 1.0
        elif re.search(r"(硕士|研究生)", resume_text):
            education_score = 0.9
        elif re.search(r"(本科)", resume_text):
            education_score = 0.8
        elif re.search(r"(大专)", resume_text):
            education_score = 0.6

        overall = 100 * (0.6 * skill_score + 0.25 * experience_score + 0.15 * education_score)
        return {
            "overall_score": round(overall, 2),
            "skill_score": round(skill_score * 100, 1),
            "experience_score": round(experience_score * 100, 1),
            "education_score": round(education_score * 100, 1),
            "overlap_keywords": [],  # 没有岗位描述，不存在重叠关键词
            "comment": "未提供职位描述，当前评分为基于简历内容的“简历质量分”，仅供参考。",
        }

    # 2. 提供了职位描述：按“岗位匹配度”算法打分
    job_tokens = tokenize(job_desc)

    if not job_tokens:
        return {
            "overall_score": 0,
            "skill_score": 0,
            "experience_score": 0,
            "education_score": 0,
            "comment": "职位描述过短或无法识别有效关键词。",
        }

    overlap = resume_tokens & job_tokens
    skill_score = len(overlap) / len(job_tokens)
    skill_score = min(skill_score, 1.0)

    # 经验和教育打分：仅做非常粗略的启发式
    experience_score = 1.0 if re.search(r"(3年以上|5年以上|主管|负责人|经理)", resume_text) else 0.5
    education_score = 0.6
    if re.search(r"(博士|硕士|研究生)", resume_text):
        education_score = 1.0
    elif re.search(r"(本科)", resume_text):
        education_score = 0.8
    elif re.search(r"(大专)", resume_text):
        education_score = 0.6

    overall = 100 * (0.6 * skill_score + 0.25 * experience_score + 0.15 * education_score)

    return {
        "overall_score": round(overall, 2),
        "skill_score": round(skill_score * 100, 1),
        "experience_score": round(experience_score * 100, 1),
        "education_score": round(education_score * 100, 1),
        "overlap_keywords": list(overlap)[:30],
    }


_CACHE: Dict[str, Dict[str, Any]] = {}


def make_cache_key(file_bytes: bytes, job_desc: str) -> str:
    h = hashlib.sha256()
    h.update(file_bytes)
    h.update(job_desc.encode("utf-8", errors="ignore"))
    return h.hexdigest()


@app.route("/", methods=["GET"])
def index() -> Any:
    # 前端单页
    return send_from_directory("static", "index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze() -> Any:
    """综合接口：上传 PDF + 职位描述，一次性返回解析结果和匹配评分。"""
    if "file" not in request.files:
        return jsonify({"error": "缺少文件参数 file"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "仅支持 PDF 简历文件"}), 400

    job_desc = request.form.get("job_desc", "")

    file_bytes = file.read()
    cache_key = make_cache_key(file_bytes, job_desc)
    if cache_key in _CACHE:
        cached = _CACHE[cache_key]
        cached["from_cache"] = True
        return jsonify(cached)

    try:
        text = extract_text_from_pdf(io.BytesIO(file_bytes))
    except Exception as e:
        return jsonify({"error": f"PDF 解析失败: {e}"}), 500

    basic_info = extract_basic_info(text)
    job_info = extract_job_info(text)
    background_info = extract_background_info(text)
    match_result = compute_match_score(text, job_desc)

    result = {
        "raw_text": text,
        "basic_info": asdict(basic_info),
        "job_info": asdict(job_info),
        "background_info": asdict(background_info),
        "match": match_result,
        "from_cache": False,
    }

    _CACHE[cache_key] = result

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

