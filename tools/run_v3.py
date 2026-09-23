"""正式入口，先分流PyInstaller辅助进程，再安装主程序日志和Qt。"""
def main():
    from doubao_typeless.runtime_diagnostics import run_application
    run_application()

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
