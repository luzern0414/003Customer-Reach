"""识别公开读取返回的登录/验证入口；避免把限制页记为企业正文或可复用知识。"""
import re
from urllib.parse import urlparse


def access_issue(url: str, title: str, body: str) -> str:
    """url/title/body为实际页面元信息和正文，可为空；返回已明确限制码或空，不根据普通页脚登录链接猜限制。

    只识别登录路径/页面标题和短验证页；不会绕过限制，不返回或修改页面正文。
    """
    path=urlparse(url or '').path.lower()
    heading=(title or '').strip()
    if re.search(r'/(?:login|signin|sign-in|userlogin|memberlogin)(?:[./;]|$)',path):return 'site_login_required'
    if re.match(r'^(?:(?:用户|会员|企业|账号|账户)?(?:登录|登陆)|log\s*in|sign\s*in)(?:$|[-|_—–·：:\s])',heading,re.I):return 'site_login_required'
    if re.match(r'^(?:安全验证|访问验证|身份验证|验证码|security verification|access denied)(?:$|[-|_—–·：:\s])',heading,re.I):return 'site_verification_required'
    if len(body or '')<800 and re.search(r'请完成(?:安全|人机|身份)?验证|请验证您(?:的身份|不是机器人)|verify you are human|checking your browser',body or '',re.I):return 'site_verification_required'
    return ''
