"""固定入口；更新运行代码存于用户数据目录，安装目录保持不变。"""
from pathlib import Path
import subprocess
import sys
import updates


def main():
    if sys.argv[1:2] == ['updates']:
        return updates.main(sys.argv[2:])
    try:
        updates.auto_update()
        plugin = updates.active_plugin()
    except Exception:
        print('更新状态异常，使用捆绑版本；可运行 updates rollback。', file=sys.stderr)
        plugin = Path(__file__).resolve().parents[1]
    return subprocess.call([sys.executable, str(plugin / 'scripts' / 'bridge.py'), *sys.argv[1:]])


if __name__ == '__main__':
    raise SystemExit(main())
