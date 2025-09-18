class FakeWin32:
    def __init__(self):
        self.written: list[bytes] = []

    def GetDefaultPrinter(self):
        return "dummy"

    def OpenPrinter(self, name):
        return object()

    def StartDocPrinter(self, h, level, info):
        pass

    def StartPagePrinter(self, h):
        pass

    def WritePrinter(self, h, data):
        self.written.append(data)

    def EndPagePrinter(self, h):
        pass

    def EndDocPrinter(self, h):
        pass

    def ClosePrinter(self, h):
        pass


fake_win32 = FakeWin32()
