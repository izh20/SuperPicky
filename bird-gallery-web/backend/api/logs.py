"""日志查看 API — 通过 Web 远程查看 nginx / 后端日志"""

import os
import re
from collections import Counter
from fastapi import APIRouter, Depends, HTTPException, Query
from api.auth import require_admin

router = APIRouter(tags=["logs"])

LOG_FILES = {
    "nginx_access": "/tmp/superpicky_nginx_access.log",
    "nginx_error": "/tmp/superpicky_nginx_error.log",
    "backend": "/tmp/superpicky_backend.log",
    "frontend": "/tmp/superpicky_frontend.log",
    "gui": "/tmp/superpicky_gui.log",
}

# nginx access log 格式:
# 192.168.31.25 - [11/Apr/2026:21:29:20 +0800] "GET /api/photos HTTP/1.1" 200 456 "http://..." "Mozilla/..." 0.001
_NGINX_RE = re.compile(
    r'^(?P<ip>[\d.]+) - \[(?P<time>[^\]]+)\] "(?P<method>\w+) (?P<path>[^ ]+) [^"]*" '
    r'(?P<status>\d+) (?P<bytes>\d+) "(?P<referer>[^"]*)" "(?P<ua>[^"]*)" (?P<duration>[\d.]+)'
)

# 后端日志格式:
# 2026-04-11 19:57:19,672 [bird-gallery] INFO: Initializing database...
# INFO:     127.0.0.1:53164 - "GET /api/photos HTTP/1.1" 200 OK
_BACKEND_RE = re.compile(
    r'^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+) \[(?P<module>[^\]]+)\] (?P<level>\w+): (?P<msg>.*)'
)
_UVICORN_RE = re.compile(
    r'^(?P<level>\w+):\s+(?P<msg>.*)'
)


def _detect_device(ua: str) -> str:
    ua_lower = ua.lower()
    if 'iphone' in ua_lower:
        return 'iPhone'
    if 'ipad' in ua_lower:
        return 'iPad'
    if 'android' in ua_lower:
        return 'Android'
    if 'macintosh' in ua_lower or 'mac os' in ua_lower:
        return 'Mac'
    if 'windows' in ua_lower:
        return 'Windows'
    if 'linux' in ua_lower:
        return 'Linux'
    if 'curl' in ua_lower:
        return '命令行'
    if 'bot' in ua_lower or 'spider' in ua_lower:
        return '爬虫'
    return '未知'


def _describe_path(path: str) -> str:
    if path.startswith('/api/photos') and 'find-duplicates' in path:
        return '查找重复照片'
    if path.startswith('/api/photos') and '/original' in path:
        return '查看原图'
    if path.startswith('/api/photos') and '/thumbnail' in path:
        return '加载缩略图'
    if path.startswith('/api/photos'):
        return '浏览照片'
    if path.startswith('/api/auth/login'):
        return '登录'
    if path.startswith('/api/auth'):
        return '认证'
    if path.startswith('/api/admin/logs'):
        return '查看日志'
    if path.startswith('/api/admin'):
        return '系统管理'
    if path.startswith('/api/upload'):
        return '上传照片'
    if path.startswith('/api/birds'):
        return '浏览鸟种'
    if path.startswith('/api/videos'):
        return '浏览视频'
    if path.startswith('/api/tasks'):
        return '查看任务'
    if path.startswith('/api/library'):
        return '图库管理'
    if path.startswith('/api/stats'):
        return '查看统计'
    if path.startswith('/api/'):
        return 'API 请求'
    if path.startswith('/@vite') or path.startswith('/node_modules') or path.startswith('/src/'):
        return '加载前端资源'
    if path == '/' or path.startswith('/gallery') or path.startswith('/photos/'):
        return '浏览页面'
    if path.startswith('/duplicates'):
        return '查看重复照片'
    if path.startswith('/logs'):
        return '查看日志'
    if path.startswith('/settings'):
        return '系统设置'
    if any(path.endswith(ext) for ext in ('.js', '.css', '.ts', '.vue', '.svg', '.png', '.ico', '.woff', '.woff2')):
        return '加载前端资源'
    return '其他'


def _status_label(code: int) -> str:
    if code < 300:
        return '成功'
    if code < 400:
        return '跳转'
    if code == 401:
        return '未登录'
    if code == 403:
        return '无权限'
    if code == 404:
        return '未找到'
    if code < 500:
        return '请求错误'
    if code == 502:
        return '服务不可用'
    return '服务器错误'


def _parse_nginx_access(lines: list[str]) -> dict:
    """解析 nginx access log, 生成面向小白的分析结果。"""
    parsed = []
    ips = Counter()
    devices = Counter()
    pages = Counter()
    statuses = Counter()
    errors = []
    total_duration = 0.0
    slow_requests = []

    for line in lines:
        m = _NGINX_RE.match(line)
        if not m:
            continue
        d = m.groupdict()
        status = int(d['status'])
        duration = float(d['duration'])
        device = _detect_device(d['ua'])
        desc = _describe_path(d['path'])

        ips[d['ip']] += 1
        devices[device] += 1
        if desc not in ('加载前端资源',):
            pages[desc] += 1
        statuses[_status_label(status)] += 1
        total_duration += duration

        entry = {
            'time': d['time'].split('+')[0].strip(),
            'ip': d['ip'],
            'device': device,
            'action': desc,
            'path': d['path'],
            'status': status,
            'status_label': _status_label(status),
            'duration_ms': round(duration * 1000),
            'bytes': int(d['bytes']),
        }
        parsed.append(entry)

        if status >= 400:
            errors.append(entry)
        if duration > 1.0:
            slow_requests.append(entry)

    unique_visitors = len(ips)
    total = len(parsed)

    return {
        'summary': {
            'total_requests': total,
            'unique_visitors': unique_visitors,
            'error_count': len(errors),
            'avg_response_ms': round((total_duration / total) * 1000) if total else 0,
            'visitors': [{'ip': ip, 'count': c} for ip, c in ips.most_common(10)],
            'devices': [{'name': d, 'count': c} for d, c in devices.most_common()],
            'popular_actions': [{'name': p, 'count': c} for p, c in pages.most_common(10)],
            'status_overview': [{'label': s, 'count': c} for s, c in statuses.most_common()],
        },
        'recent': list(reversed(parsed[-50:])),
        'errors': list(reversed(errors[-20:])),
        'slow': list(reversed(slow_requests[-10:])),
    }


def _parse_backend_log(lines: list[str]) -> dict:
    """解析后端日志, 生成面向小白的分析结果。"""
    entries = []
    level_counts = Counter()
    modules = Counter()

    level_labels = {
        'INFO': '信息',
        'WARNING': '警告',
        'ERROR': '错误',
        'CRITICAL': '严重错误',
        'DEBUG': '调试',
    }
    level_icons = {
        'INFO': 'info',
        'WARNING': 'warning',
        'ERROR': 'error',
        'CRITICAL': 'error',
        'DEBUG': 'debug',
    }

    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = _BACKEND_RE.match(line)
        if m:
            d = m.groupdict()
            level = d['level'].upper()
            level_counts[level] += 1
            modules[d['module']] += 1
            entries.append({
                'time': d['time'],
                'level': level,
                'level_label': level_labels.get(level, level),
                'level_icon': level_icons.get(level, 'info'),
                'module': d['module'],
                'message': d['msg'],
            })
        else:
            m2 = _UVICORN_RE.match(line)
            if m2:
                level = m2.group('level').upper()
                level_counts[level] += 1
                entries.append({
                    'time': '',
                    'level': level,
                    'level_label': level_labels.get(level, level),
                    'level_icon': level_icons.get(level, 'info'),
                    'module': 'uvicorn',
                    'message': m2.group('msg'),
                })

    error_entries = [e for e in entries if e['level'] in ('ERROR', 'CRITICAL', 'WARNING')]

    return {
        'summary': {
            'total_entries': len(entries),
            'level_counts': [{'level': l, 'label': level_labels.get(l, l), 'count': c}
                             for l, c in level_counts.most_common()],
            'has_errors': any(e['level'] in ('ERROR', 'CRITICAL') for e in entries),
            'has_warnings': any(e['level'] == 'WARNING' for e in entries),
        },
        'recent': list(reversed(entries[-50:])),
        'issues': list(reversed(error_entries[-20:])),
    }


@router.get("/admin/logs")
async def list_logs(_=Depends(require_admin)):
    """列出所有可查看的日志文件及大小。"""
    result = []
    for name, path in LOG_FILES.items():
        exists = os.path.isfile(path)
        size = os.path.getsize(path) if exists else 0
        result.append({"name": name, "path": path, "exists": exists, "size_bytes": size})
    return result


@router.get("/admin/logs/{log_name}")
async def read_log(
    log_name: str,
    tail: int = Query(200, ge=1, le=5000, description="返回最后N行"),
    _=Depends(require_admin),
):
    """读取指定日志文件的最后 N 行。"""
    if log_name not in LOG_FILES:
        raise HTTPException(404, f"未知日志: {log_name}，可选: {list(LOG_FILES.keys())}")

    path = LOG_FILES[log_name]
    if not os.path.isfile(path):
        return {"name": log_name, "lines": [], "total_lines": 0, "message": "日志文件不存在"}

    with open(path, "r", errors="replace") as f:
        all_lines = f.readlines()

    selected = all_lines[-tail:]
    return {
        "name": log_name,
        "total_lines": len(all_lines),
        "returned_lines": len(selected),
        "lines": [line.rstrip("\n") for line in selected],
    }


@router.get("/admin/logs/{log_name}/analyze")
async def analyze_log(
    log_name: str,
    tail: int = Query(500, ge=1, le=5000, description="分析最后N行"),
    _=Depends(require_admin),
):
    """智能分析日志，返回结构化数据（面向普通用户）。"""
    if log_name not in LOG_FILES:
        raise HTTPException(404, f"未知日志: {log_name}")

    path = LOG_FILES[log_name]
    if not os.path.isfile(path):
        return {"name": log_name, "summary": {}, "recent": [], "errors": []}

    with open(path, "r", errors="replace") as f:
        all_lines = f.readlines()

    selected = [l.rstrip("\n") for l in all_lines[-tail:]]

    if log_name == 'nginx_access':
        result = _parse_nginx_access(selected)
    elif log_name in ('backend', 'gui'):
        result = _parse_backend_log(selected)
    else:
        # 对于 error log / frontend log, 返回简单格式
        result = {
            'summary': {'total_entries': len(selected)},
            'recent': [{'message': l, 'level': 'ERROR' if 'error' in l.lower() else 'INFO',
                        'level_label': '错误' if 'error' in l.lower() else '信息'}
                       for l in reversed(selected[-50:]) if l.strip()],
            'issues': [{'message': l, 'level_label': '错误'}
                       for l in reversed(selected[-20:]) if 'error' in l.lower()],
        }

    result['name'] = log_name
    result['total_lines'] = len(all_lines)
    result['analyzed_lines'] = len(selected)
    return result
