import os, time

LOG_BAR = "----------------------------------------------------"

class Logger:

    def __init__(self, directory, name, onPrint = None, printToConsole = True):

        self.onPrint = onPrint
        self.printToConsole = printToConsole
        self.file = open(os.path.join(directory, name + ".log"), "a", buffering = 1)

        self.LogLine()
        self.LogBar()
        self.LogLine()
        self.Log(f'[{time.strftime("%Y-%m-%d")}]')
        self.LogLine()
        self.LogTime("Log started")
        self.LogBar()

    def __del__(self):
        if not self.file.closed:
            self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.file.close()

    def _PrependTime(self, msg):
        return f"[{time.strftime('%H:%M:%S')}] - {msg}"

    def _Bar(self):
        return LOG_BAR

    def _Emit(self, msg):
        if self.onPrint:
            self.onPrint(msg)

    def _Print(self, msg):
        if self.printToConsole:
            print(msg)

    def Close(self):
        self.file.close()

    def Log(self, msg):
        self.file.write(msg + "\n")

    def LogTime(self, msg):
        self.file.write(self._PrependTime(msg) + "\n")

    def PrintLog(self, msg):
        self.file.write(msg + "\n")
        self._Print(msg)
        self._Emit(msg)

    def PrintTime(self, msg):
        msg = self._PrependTime(msg)
        self._Print(msg)
        self._Emit(msg)

    def PrintLogTime(self, msg):
        msg = self._PrependTime(msg)
        self.file.write(msg + "\n")
        self._Print(msg)
        self._Emit(msg)

    def PrintLine(self):
        self._Print("")
        self._Emit("")

    def LogLine(self):
        self.file.write("\n")

    def PrintLogLine(self):
        self._Print("")
        self.file.write("\n")
        self._Emit("")

    def PrintBar(self):
        bar = self._Bar()
        self._Print(bar)
        self._Emit(bar)

    def LogBar(self):
        self.file.write(self._Bar() + "\n")

    def PrintLogBar(self):
        bar = self._Bar()
        self._Print(bar)
        self.file.write(bar + "\n")
        self._Emit(bar)

    def LogError(self, err):
        self.LogLine()
        self.LogBar()
        self.file.write("|| ERROR:\t" + err + "\n")
        self.LogBar()

    def PrintLogError(self, err):
        self.LogError(err)
        self.PrintLine()
        self.PrintBar()
        msg = "|| ERROR:\t" + err
        self._Print(msg)
        self._Emit(msg)
        self.PrintBar()
        self.PrintLine()
