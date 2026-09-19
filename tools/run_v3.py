"""V3 正式构建入口：先安装本地运行取证，再导入应用。"""
from doubao_typeless.runtime_diagnostics import run_application as main

if __name__ == "__main__":
    main()
