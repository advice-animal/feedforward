class Generation(tuple):
    def increment(self):
        return self.__class__(self[:-1] + (self[-1] + 1,))

    def child(self):
        return self.__class__(self + (0,))
