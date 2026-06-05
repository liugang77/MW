"""行情同步：从公开数据源获取股票/基金的名称与最新价格。

数据源（公开、免费、无需密钥，仅供个人自用）：
- 股票/ETF/债券：新浪财经 https://hq.sinajs.cn/list=sh600000
- 开放式/货币基金、银行理财：天天基金 https://fundgz.1234567.com.cn/js/{code}.js

注意：以上接口为非官方接口，可能限频或变更，仅用于本地个人记账估值。
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# 走基金通道的分类 / 持仓类型
_FUND_CATEGORIES = {"open_fund", "money_fund", "bank_wealth"}
_FUND_TYPES = {"fund", "wealth", "money_fund", "open_fund"}


def _http_get(url: str, headers: dict | None = None, timeout: int = 8) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (受信任的固定域名)
        return resp.read()


# 合法的证券/基金代码：可选 sh/sz/bj 前缀 + 5~6 位数字（排除中文名称等）
_CODE_RE = re.compile(r"^(sh|sz|bj)?\d{5,6}$", re.IGNORECASE)


def is_valid_code(code: str) -> bool:
    """判断是否为可用于行情查询的代码（纯数字/带市场前缀），排除中文名称。"""
    return bool(_CODE_RE.match((code or "").strip()))


def _guess_market(code: str) -> str:
    """根据证券代码推断市场前缀：sh / sz / bj。"""
    if code[:2] in ("sh", "sz", "bj"):
        return code[:2]
    if code.startswith(("5", "6", "9", "11", "13", "20")):
        return "sh"
    if code.startswith(("0", "1", "2", "3")):
        return "sz"
    if code.startswith(("4", "8")) or code.startswith("92"):
        return "bj"
    return "sh"


def fetch_stock(code: str) -> dict | None:
    """新浪行情：返回 {code, name, price}。"""
    code = code.strip().lower()
    market = _guess_market(code)
    pure = code[2:] if code[:2] in ("sh", "sz", "bj") else code
    url = f"https://hq.sinajs.cn/list={market}{pure}"
    try:
        raw = _http_get(url, headers={"Referer": "https://finance.sina.com.cn"})
    except (urllib.error.URLError, TimeoutError):
        return None
    text = raw.decode("gbk", errors="ignore")
    m = re.search(r'"(.*)"', text)
    if not m or not m.group(1):
        return None
    parts = m.group(1).split(",")
    if len(parts) < 4:
        return None
    name = parts[0]
    # parts: 名称, 今开, 昨收, 当前价, 最高, 最低, ...
    price = parts[3]
    try:
        if float(price) == 0:
            price = parts[2]  # 未开盘/停牌时用昨收
    except ValueError:
        price = parts[2]
    if not name:
        return None
    return {"code": pure, "name": name, "price": price}


def fetch_fund(code: str) -> dict | None:
    """天天基金估值：返回 {code, name, price}（优先估算净值，回退单位净值）。

    货币基金等无估值的品种，回退到东方财富历史净值接口取最新单位净值。
    """
    code = code.strip()
    url = f"https://fundgz.1234567.com.cn/js/{code}.js"
    try:
        raw = _http_get(url, headers={"Referer": "https://fund.eastmoney.com/"})
        text = raw.decode("utf-8", errors="ignore")
        m = re.search(r"jsonpgz\((.*)\)", text)
        if m and m.group(1).strip():
            data = json.loads(m.group(1))
            name = data.get("name")
            price = data.get("gsz") or data.get("dwjz")  # 估算净值优先
            if name and price:
                return {"code": code, "name": name, "price": price}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass
    return _fetch_fund_nav(code)


def _fetch_fund_nav(code: str) -> dict | None:
    """东方财富历史净值：取最新一条单位净值（货币基金为每万份收益）。"""
    url = (
        "https://api.fund.eastmoney.com/f10/lsjz"
        f"?fundCode={code}&pageIndex=1&pageSize=1"
    )
    try:
        raw = _http_get(url, headers={"Referer": "https://fundf10.eastmoney.com/"})
        data = json.loads(raw.decode("utf-8", errors="ignore"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    rows = (data.get("Data") or {}).get("LSJZList") or []
    if not rows:
        return None
    price = rows[0].get("DWJZ")
    if not price:
        return None
    return {"code": code, "name": code, "price": price}


# 常见外汇币种中文名（用于补充新币种时的名称）
_FOREX_NAMES = {
    "USD": "美元", "EUR": "欧元", "HKD": "港币", "JPY": "日元",
    "GBP": "英镑", "AUD": "澳大利亚元", "CAD": "加拿大元", "CHF": "瑞士法郎",
    "SGD": "新加坡元", "KRW": "韩元", "THB": "泰铢", "MYR": "马来西亚林吉特",
    "RUB": "卢布", "NZD": "新西兰元", "TWD": "新台币", "MOP": "澳门元",
    "CNY": "人民币",
}


def forex_name(code: str) -> str:
    """外汇币种代码 → 中文名（无匹配时回退为代码本身）。"""
    return _FOREX_NAMES.get((code or "").strip().upper(), (code or "").strip().upper())


def fetch_forex_rate(code: str) -> dict | None:
    """新浪外汇：返回 {code, name, rate}，rate 为 1 单位该外币兑换的人民币。

    接口：https://hq.sinajs.cn/list=fx_susdcny（美元兑人民币）。
    代码规则：fx_s + 小写币种 + cny，本币 CNY 直接返回 1。
    """
    code = (code or "").strip().upper()
    if not code or code == "CNY":
        return {"code": "CNY", "name": "人民币", "rate": "1"}
    sym = f"fx_s{code.lower()}cny"
    url = f"https://hq.sinajs.cn/list={sym}"
    try:
        raw = _http_get(url, headers={"Referer": "https://finance.sina.com.cn"})
    except (urllib.error.URLError, TimeoutError):
        return None
    text = raw.decode("gbk", errors="ignore")
    m = re.search(r'="([^"]*)"', text)
    if not m or not m.group(1):
        return None
    parts = m.group(1).split(",")
    if len(parts) < 2:
        return None
    # parts[1..] 为各类牌价（买入/卖出/昨结等），取首个合理正数作为牌价
    rate = None
    for p in parts[1:6]:
        try:
            v = float(p)
        except ValueError:
            continue
        if v > 0:
            rate = v
            break
    if rate is None:
        return None
    # 名称通常在结尾（中文）
    name = None
    for p in reversed(parts):
        if re.search(r"[\u4e00-\u9fff]", p):
            name = p.strip()
            break
    return {"code": code, "name": name, "rate": f"{rate:.4f}"}


def kind_for_category(category: str | None) -> str:
    cat = category or ""
    if cat in ("metal", "metal_td"):
        return "metal"
    return "fund" if cat in _FUND_CATEGORIES else "stock"


def kind_for_holding_type(htype: str | None) -> str:
    ht = htype or ""
    if ht in ("metal", "metal_td"):
        return "metal"
    return "fund" if ht in _FUND_TYPES else "stock"


# ============ 贵金属（上海黄金交易所 SGE）行情 ============
# 预置常见品种：展示名 → 新浪 SGE 代码（hq.sinajs.cn/list=gds_XXX）
_METAL_PRODUCTS = [
    {"name": "Au(T+D)", "sina": "gds_AUTD"},
    {"name": "Ag(T+D)", "sina": "gds_AGTD"},
    {"name": "Au99.99", "sina": "gds_AU9999"},
    {"name": "Au100g", "sina": "gds_AU100G"},
    {"name": "Au(T+N2)", "sina": "gds_AUTN2"},
    {"name": "mAu(T+D)", "sina": "gds_MAUTD"},
    {"name": "Pt99.95", "sina": "gds_PT9995"},
    {"name": "iAu99.99", "sina": "gds_AU9999"},
]
_METAL_BY_NAME = {p["name"].strip().upper(): p["sina"] for p in _METAL_PRODUCTS}


def metal_catalog() -> list[dict]:
    """返回预置的贵金属品种目录（用于一键补充产品）。"""
    return [{"name": p["name"]} for p in _METAL_PRODUCTS]


def fetch_metal(name: str) -> dict | None:
    """新浪 SGE 贵金属行情：按品种展示名返回 {code, name, price}。

    接口：https://hq.sinajs.cn/list=gds_AUTD（黄金延期）等。
    返回字段以 , 分隔：[0]=最新价 … [13]=名称。
    """
    sina = _METAL_BY_NAME.get((name or "").strip().upper())
    if not sina:
        return None
    url = f"https://hq.sinajs.cn/list={sina}"
    try:
        raw = _http_get(url, headers={"Referer": "https://finance.sina.com.cn"})
    except (urllib.error.URLError, TimeoutError):
        return None
    text = raw.decode("gbk", errors="ignore")
    m = re.search(r'="([^"]*)"', text)
    if not m or not m.group(1):
        return None
    parts = m.group(1).split(",")
    if len(parts) < 2:
        return None
    try:
        price = float(parts[0])
    except ValueError:
        return None
    if price <= 0:
        return None
    return {"code": name, "name": name, "price": f"{price:.2f}"}


def lookup(kind: str, code: str) -> dict | None:
    """按通道查询行情：kind=metal 走贵金属，kind=fund 走基金，否则走股票。"""
    code = (code or "").strip()
    if kind == "metal":
        return fetch_metal(code)
    if not is_valid_code(code):
        return None
    if kind == "fund":
        return fetch_fund(code)
    return fetch_stock(code)


# ============ 全量产品目录同步 ============

def stock_subcategory(code: str) -> str:
    """按代码前缀推断上市证券类型（用于 instrument.subcategory）。"""
    code = (code or "").strip()
    if code.startswith(("688", "689")):
        return "科创板股票"
    if code.startswith("60"):
        return "沪市股票"
    if code.startswith("30"):
        return "创业板股票"
    if code.startswith(("000", "001", "002", "003", "004")):
        return "深市股票"
    if code.startswith(("8", "920", "43", "87")):
        return "北交所股票"
    if code.startswith(("51", "56", "58", "159", "15")):
        return "ETF基金"
    return "其它"


def _fetch_stock_catalog_sina() -> list[dict]:
    """新浪财经：分页拉取全部 A 股列表（自带市场前缀）。可能被限流(456)。"""
    page_size = 100
    base = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "Market_Center.getHQNodeData?page={pn}&num={num}&sort=symbol&asc=1&node=hs_a"
    )
    seen: set[str] = set()
    out: list[dict] = []
    page = 1
    empty_streak = 0
    while True:
        url = base.format(pn=page, num=page_size)
        rows = None
        for attempt in range(3):
            try:
                raw = _http_get(
                    url,
                    headers={"Referer": "https://vip.stock.finance.sina.com.cn/"},
                    timeout=15,
                )
                rows = json.loads(raw.decode("utf-8", errors="ignore"))
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
                time.sleep(0.5 * (attempt + 1))
        if not rows:
            empty_streak += 1
            if empty_streak >= 2:
                break
            page += 1
            continue
        empty_streak = 0
        for it in rows:
            code = str(it.get("code") or "").strip()
            name = str(it.get("name") or "").strip()
            if not code or not name or code in seen:
                continue
            seen.add(code)
            out.append({"code": code, "name": name, "subcategory": stock_subcategory(code)})
        if len(rows) < page_size:
            break
        page += 1
        if page > 120:  # 安全上限
            break
        time.sleep(0.15)
    return out


# 东方财富 A 股全集筛选条件（沪深京 A 股）
_EM_STOCK_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
_EM_HOSTS = ("82.push2.eastmoney.com", "80.push2.eastmoney.com", "1.push2.eastmoney.com", "push2.eastmoney.com")


def _fetch_stock_catalog_em() -> list[dict]:
    """东方财富 push2：小页(20)分页拉取全部 A 股列表，多域名轮询 + 重试。

    push2 对大页/高频较敏感，故用小页、轮换域名并重试，慢但稳定。
    """
    page_size = 20
    seen: set[str] = set()
    out: list[dict] = []
    host_idx = 0

    def _get(pn: int) -> tuple[int, list] | None:
        nonlocal host_idx
        for _ in range(len(_EM_HOSTS) * 2):
            host = _EM_HOSTS[host_idx % len(_EM_HOSTS)]
            host_idx += 1
            url = (
                f"https://{host}/api/qt/clist/get?pn={pn}&pz={page_size}&po=1&np=1"
                f"&fltt=2&invt=2&fid=f12&fs={_EM_STOCK_FS}&fields=f12,f14"
            )
            try:
                raw = _http_get(url, headers={"Referer": "https://quote.eastmoney.com/"}, timeout=12)
                d = json.loads(raw.decode("utf-8", errors="ignore"))
                data = d.get("data") or {}
                return int(data.get("total") or 0), (data.get("diff") or [])
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, json.JSONDecodeError):
                time.sleep(0.3)
        return None

    first = _get(1)
    if not first:
        return []
    total, rows = first
    for r in rows:
        out.append(r)
    total_pages = (total + page_size - 1) // page_size if total else 1
    for pn in range(2, min(total_pages, 400) + 1):  # 安全上限 400 页（约 8000 只）
        res = _get(pn)
        if not res:
            continue
        _, rows = res
        if not rows:
            break
        out.extend(rows)
        time.sleep(0.05)

    catalog: list[dict] = []
    for it in out:
        code = str(it.get("f12") or "").strip()
        name = str(it.get("f14") or "").strip()
        if not code or not name or code in seen:
            continue
        seen.add(code)
        catalog.append({"code": code, "name": name, "subcategory": stock_subcategory(code)})
    return catalog


def fetch_stock_catalog() -> list[dict]:
    """拉取全部 A 股列表，返回 [{code, name, subcategory}]。

    优先东方财富（稳定），失败时回退新浪。
    """
    rows = _fetch_stock_catalog_em()
    if rows:
        return rows
    return _fetch_stock_catalog_sina()


def fetch_fund_catalog() -> list[dict]:
    """东方财富：拉取全部公募基金列表，返回 [{code, name, is_money}]。"""
    url = "https://fund.eastmoney.com/js/fundcode_search.js"
    try:
        raw = _http_get(url, headers={"Referer": "https://fund.eastmoney.com/"}, timeout=20)
        text = raw.decode("utf-8", errors="ignore")
    except (urllib.error.URLError, TimeoutError):
        return []
    m = re.search(r"\[(.*)\]", text, re.S)
    if not m:
        return []
    try:
        rows = json.loads("[" + m.group(1) + "]")
    except json.JSONDecodeError:
        return []
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, list) or len(r) < 4:
            continue
        code = str(r[0]).strip()
        name = str(r[2]).strip()
        ftype = str(r[3])
        if not code or not name:
            continue
        out.append({"code": code, "name": name, "is_money": "货币" in ftype})
    return out

