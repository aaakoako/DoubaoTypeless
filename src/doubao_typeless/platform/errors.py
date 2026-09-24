class PlatformUnavailable(RuntimeError):
    def __init__(self, code):
        self.error_code = code
        super().__init__(code)
