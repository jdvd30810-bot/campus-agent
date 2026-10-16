import subprocess

def probe_all_windows():
    print("=" * 60)
    print("🔍 深度排查：正在扫描微信的所有窗口与深层 UI 结构...")
    print("=" * 60)
    
    script = '''
    tell application "System Events"
        if not (exists process "WeChat") then
            return "ERROR: 微信未启动"
        end if
        tell process "WeChat"
            set frontmost to true
            delay 0.3
            
            set winInfo to ""
            set allWins to every window
            set winCount to count of allWins
            set winInfo to winInfo & "【微信总窗口数】: " & winCount & "\\n"
            
            repeat with i from 1 to winCount
                set currWin to item i of allWins
                set wName to (name of currWin as string)
                set winInfo to winInfo & "--- 窗口 " & i & ": [" & wName & "] ---\\n"
                
                -- 如果是主窗口（通常名字叫 "微信" 或包含群名）
                try
                    set subEls to UI elements of currWin
                    set elSummary to ""
                    repeat with el in subEls
                        set elClass to class of el as string
                        set elName to name of el as string
                        set elDesc to description of el as string
                        set elSummary to elSummary & "  • " & elClass & " (name: " & elName & ", desc: " & elDesc & ")\\n"
                    end repeat
                    set winInfo to winInfo & elSummary
                on error err
                    set winInfo to winInfo & "  读取元素失败: " & err & "\\n"
                end try
            end repeat
            
            return winInfo
        end tell
    end tell
    '''
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    print(res.stdout)
    if res.stderr:
        print("错误信息：", res.stderr)

if __name__ == "__main__":
    probe_all_windows()
