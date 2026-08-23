# -*- coding: utf-8 -*-
"""系统信息工具 — get_system_info (+ 面板摘要)."""
import json
import os
import platform
import shutil


def get_system_info() -> str:
    """仅当用户明确询问系统信息时使用; 不要在其他任务中作为前置步骤主动调用。"""
    info = {
        'platform': platform.platform(),
        'python': platform.python_version(),
        'cpu_count': os.cpu_count(),
        'disk': str(shutil.disk_usage(os.path.expanduser('~'))),
        'memory': _get_memory(),
    }
    return json.dumps(info, ensure_ascii=False, indent=2)


def _get_memory():
    """物理内存 (Windows ctypes / /proc/meminfo 回退)."""
    if platform.system().lower() == 'windows':
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong),
                            ('dwMemoryLoad', ctypes.c_ulong),
                            ('ullTotalPhys', ctypes.c_ulonglong),
                            ('ullAvailPhys', ctypes.c_ulonglong),
                            ('ullTotalPageFile', ctypes.c_ulonglong),
                            ('ullAvailPageFile', ctypes.c_ulonglong),
                            ('ullTotalVirtual', ctypes.c_ulonglong),
                            ('ullAvailVirtual', ctypes.c_ulonglong),
                            ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]

            m = MEMORYSTATUSEX()
            m.dwLength = ctypes.sizeof(m)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return 'total %.1f GB, avail %.1f GB' % (
                m.ullTotalPhys / 2**30, m.ullAvailPhys / 2**30)
        except Exception as e:
            return 'unavailable: %s' % e
    try:
        with open('/proc/meminfo', 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    return line.strip()
    except OSError:
        pass
    return 'unavailable'


def _sysinfo_summary(result, args=None):
    """系统信息摘要, 如 'Windows-10-10.0.19045-SP0, 12 CPU'. 解析失败返回 None."""
    try:
        data = json.loads(result)
    except ValueError:
        return None
    platform_str = str(data.get('platform', ''))
    cpu = data.get('cpu_count')
    parts = [platform_str]
    if cpu:
        parts.append('%s CPU' % cpu)
    return ', '.join(parts) if parts else None


def register(reg):
    """把本模块工具注册进给定注册表 (幂等)."""
    reg.tool(summary=_sysinfo_summary)(get_system_info)
