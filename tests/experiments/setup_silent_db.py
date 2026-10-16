#!/usr/bin/env python3
"""
Campus-Agent - 本地数据库静默解密环境诊断与引导工具
---------------------------------------------------
"""

import sys
import subprocess
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.wechat_db import check_disk_access, find_wechat_accounts, WECHAT_CONTAINER

def check_codesign() -> bool:
    """检查微信是否已经完成本地重签名"""
    try:
        res = subprocess.run(
            ["codesign", "-d", "-vvv", "/Applications/WeChat.app"],
            capture_output=True,
            text=True
        )
        output = res.stderr + res.stdout
        # 如果是 ad-hoc 签名或带有 get-task-allow
        return "Signature=adhoc" in output or "flags=0x0(none)" in output
    except Exception:
        return False

def main():
    print("=" * 65)
    print("🛠️  Campus-Agent【本地数据库静默监听】环境体检与配置向导")
    print("=" * 65)

    # 1. 检测微信客户端
    wechat_app = Path("/Applications/WeChat.app")
    if wechat_app.exists():
        print("✅ 1. 发现微信客户端: /Applications/WeChat.app")
    else:
        print("❌ 1. 未在 /Applications 找到微信客户端！")
        return

    # 2. 检测完全磁盘访问权限
    has_disk_access = check_disk_access()
    if has_disk_access:
        print("✅ 2. 终端已具备【完全磁盘访问权限】！")
        accounts = find_wechat_accounts()
        print(f"   📂 发现已登录的本地微信账户数: {len(accounts)}")
        for acc in accounts:
            print(f"      • {acc.name}")
    else:
        print("⚠️  2. 终端尚未获得【完全磁盘访问权限】！")
        print("   👉 解决步骤：")
        print("      1. 打开 Mac【系统设置】->【隐私与安全性】->【完全磁盘访问权限】；")
        print("      2. 点击【+】或找到【终端 (Terminal)】，将开关拨至【开启】；")
        print("      3. 重启终端后再次运行此向导。")
        print("=" * 65)
        return

    # 3. 检查重签名状态
    is_signed = check_codesign()
    if is_signed:
        print("✅ 3. 微信已处于可调试重签名状态，具备内存密钥提取条件！")
    else:
        print("⚠️  3. 微信当前仍为官方原生签名，macOS 保护机制会阻止读取内存密钥。")
        print("   👉 若要开启静默解密，请退出微信后在终端执行以下重签名命令：")
        print("      sudo codesign --force --deep --sign - /Applications/WeChat.app")
        print("      (执行后重新打开微信登录即可)")

    print("=" * 65)
    print("🎯 体检完成！按照上述提示配置好后，后台即可开启 100% 真正的静默全自动监听！")

if __name__ == "__main__":
    main()
